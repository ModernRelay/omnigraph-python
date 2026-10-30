"""Live tests against `omnigraph-server` 0.14.0.

Set `OMNIGRAPH_TEST_SERVER=1` and `OMNIGRAPH_BIN_DIR` to a directory holding
the release's `omnigraph` and `omnigraph-server`. The fixture bootstraps a
one-graph cluster on a local `file://` root and boots the server with a bearer
token and a policy that grants the test actor the data-plane actions.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from omnigraph import (
    ConflictError,
    NotFoundError,
    Omnigraph,
    PayloadTooLargeError,
    PreconditionFailedError,
    UnauthorizedError,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("OMNIGRAPH_TEST_SERVER") != "1",
    reason="set OMNIGRAPH_TEST_SERVER=1 and OMNIGRAPH_BIN_DIR",
)

ACTOR = "act-sdk"
SCHEMA = """\
node Person {
  name: String @key
  city: String?
}

node Company {
  name: String @key
}

edge WorksAt: Person -> Company {
  role: String?
}
"""
POLICY = f"""\
version: 1
groups:
  sdk: [{ACTOR}]
rules:
  - id: rw
    allow:
      actors: {{ group: sdk }}
      actions: [read, change]
      branch_scope: any
  - id: branches
    allow:
      actors: {{ group: sdk }}
      actions: [branch_create, branch_delete, branch_merge, commit_publish, commit_drop]
      target_branch_scope: any
"""
CLUSTER = """\
version: 1
graphs:
  g:
    schema: g.pg
policies:
  graph-access:
    file: graph.policy.yaml
    applies_to: [g]
"""


@dataclass
class Server:
    base_url: str
    token: str


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    bin_dir = Path(os.environ["OMNIGRAPH_BIN_DIR"])
    work = tmp_path_factory.mktemp("og")
    bundle, root = work / "bundle", work / "root"
    bundle.mkdir()
    root.mkdir()
    (bundle / "cluster.yaml").write_text(CLUSTER)
    (bundle / "g.pg").write_text(SCHEMA)
    (bundle / "graph.policy.yaml").write_text(POLICY)
    env = {**os.environ, "OMNIGRAPH_HOME": str(work / "home")}
    r = subprocess.run(
        [str(bin_dir / "omnigraph"), "cluster", "apply", "--target", f"file://{root}",
         "--config", str(bundle), "--as", ACTOR, "--json"],
        capture_output=True, text=True, env=env, check=True,
    )  # fmt: skip
    lock = re.search(r"Admission lock: (\S+);", r.stderr)
    assert lock, r.stderr
    subprocess.run(
        [str(bin_dir / "omnigraph"), "--target", f"file://{root}", "cluster",
         "force-unlock", lock.group(1)],
        capture_output=True, env=env, check=True,
    )  # fmt: skip
    token = os.urandom(12).hex()
    port = _free_port()
    proc = subprocess.Popen(
        [str(bin_dir / "omnigraph-server"), "--cluster", f"file://{root}",
         "--bind", f"127.0.0.1:{port}"],
        stdout=(work / "server.log").open("wb"), stderr=subprocess.STDOUT,
        env={**env, "OMNIGRAPH_SERVER_BEARER_TOKENS_JSON": json.dumps({ACTOR: token})},
    )  # fmt: skip
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while True:
        try:
            with urllib.request.urlopen(f"{base}/readyz", timeout=1) as resp:
                if json.loads(resp.read()).get("ready"):
                    break
        except OSError:
            pass
        assert time.monotonic() < deadline and proc.poll() is None, (
            "server did not start"
        )
        time.sleep(0.1)
    yield Server(base, token)
    proc.terminate()
    proc.wait(timeout=30)


@pytest.fixture
async def og(server: Server) -> AsyncIterator[Omnigraph]:
    async with Omnigraph(server.base_url, graph_id="g", token=server.token) as client:
        yield client


INSERT_PERSON = (
    "query a($n: String, $c: String?) { insert Person { name: $n, city: $c } }"
)
COUNT = "query c() { match { $p: Person } return { count($p) as n } }"


async def test_probes(og: Omnigraph) -> None:
    assert (await og.health())["version"] == "0.14.0"
    assert (await og.readiness())["ready"] is True


async def test_schema_and_access(og: Omnigraph) -> None:
    assert (await og.schema.get())["schema_source"] == SCHEMA
    access = await og.access()
    assert "change" in access["graph_wide"]


async def test_mutate_and_query_round_trip(og: Omnigraph) -> None:
    out = await og.mutate(INSERT_PERSON, params={"n": "ada", "c": None})
    assert out["affected_nodes"] == 1
    assert out["commit"] is not None and out["commit"]["published"] is True
    read = await og.query(
        "query q($n: String) { match { $p: Person { name: $n } } return { $p.name, $p.city } }",
        params={"n": "ada"},
    )
    assert read["rows"] == [{"p.name": "ada"}]  # null fields are omitted
    assert read["graph_commit_id"] == out["commit"]["graph_commit_id"]


async def test_branch_lifecycle_and_merge_with_delete(og: Omnigraph) -> None:
    await og.branches.create("sdk_scratch")
    assert "sdk_scratch" in await og.branches.list()
    await og.mutate(
        INSERT_PERSON, params={"n": "grace", "c": None}, branch="sdk_scratch"
    )
    await og.mutate(
        'query d() { delete Person where name = "ada" }', branch="sdk_scratch"
    )
    merged = await og.branches.merge("sdk_scratch", delete_branch=True)
    assert merged["outcome"] in ("fast_forward", "merged")
    assert merged["branch_deleted"] is True
    assert await og.branches.list() == ["main"]


async def test_merge_conflict(og: Omnigraph) -> None:
    await og.mutate(INSERT_PERSON, params={"n": "conf", "c": "base"})
    await og.branches.create("sdk_c")
    await og.mutate(
        'query u() { update Person set { city: "b" } where name = "conf" }',
        branch="sdk_c",
    )
    await og.mutate('query u() { update Person set { city: "m" } where name = "conf" }')
    with pytest.raises(ConflictError) as info:
        await og.branches.merge("sdk_c")
    assert info.value.merge_conflicts[0]["kind"] == "divergent_update"
    assert info.value.outcome_unknown is False
    await og.branches.delete("sdk_c")


async def test_conditional_mutation(og: Omnigraph) -> None:
    head = (await og.query(COUNT))["graph_commit_id"]
    assert head is not None
    await og.mutate(
        INSERT_PERSON, params={"n": "cas1", "c": None}, if_graph_commit=head
    )
    with pytest.raises(PreconditionFailedError) as info:
        await og.mutate(
            INSERT_PERSON, params={"n": "cas2", "c": None}, if_graph_commit=head
        )
    failure = info.value.precondition_failure
    assert failure is not None and failure["expected"] == head


async def test_merge_as_commit_then_publish(og: Omnigraph) -> None:
    await og.branches.create("sdk_p")
    await og.mutate(INSERT_PERSON, params={"n": "pub", "c": None}, branch="sdk_p")
    merged = await og.branches.merge("sdk_p", as_commit=True)
    assert merged["commit"] is not None and merged["commit"]["kind"] == "unpublished"
    published = await og.commits.publish(merged["commit"]["graph_commit_id"])
    assert published["published"] is True
    await og.branches.delete("sdk_p")


async def test_unpublished_commit_drop(og: Omnigraph) -> None:
    out = await og.mutate('query p() as commit { insert Person { name: "draft" } }')
    assert out["commit"] is not None
    await og.commits.drop(out["commit"]["graph_commit_id"])
    listed = await og.commits.list(branch="main", listing="unpublished")
    assert listed["commits"] == []


async def test_entity_cap(og: Omnigraph) -> None:
    stmts = " ".join(f'insert Company {{ name: "cap{i}" }}' for i in range(8193))
    with pytest.raises(PayloadTooLargeError) as info:
        await og.mutate(f"query big() {{ {stmts} }}")
    limit = info.value.resource_limit
    assert limit is not None and limit["limit"] == 8192
    assert info.value.outcome_unknown is False


async def test_unknown_graph_and_bad_token(server: Server, og: Omnigraph) -> None:
    with pytest.raises(NotFoundError):
        await og.graph("nope").schema.get()
    async with Omnigraph(server.base_url, graph_id="g", token="wrong") as bad:
        with pytest.raises(UnauthorizedError):
            await bad.schema.get()

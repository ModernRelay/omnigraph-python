"""Live tests against the pinned `omnigraph-server` release (`SERVER_VERSION`).

Set `OMNIGRAPH_TEST_SERVER=1` and `OMNIGRAPH_BIN_DIR` to a directory holding
the release's `omnigraph` and `omnigraph-server`. The fixture bootstraps a
one-graph cluster on a local `file://` root and boots the server with a bearer
token and a policy that grants the test actor the data-plane actions and
`maintain`, with the recorded-operation routes enabled.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from omnigraph import (
    SERVER_VERSION,
    BadRequestError,
    ConflictError,
    NotFoundError,
    Omnigraph,
    PayloadTooLargeError,
    PreconditionFailedError,
    UnauthorizedError,
    is_terminal,
    new_operation_id,
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

node Doc {
  slug: String @key
  body: Blob?
}

edge WorksAt: Person -> Company {
  role: String?
}

node Spot {
  slug: String @key
  at: Vector(2)
}

node Counter {
  name: String @key
  n: U64
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
      actions: [read, change, export, maintain]
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
    subprocess.run(
        [str(bin_dir / "omnigraph"), "cluster", "apply", "--target", f"file://{root}",
         "--config", str(bundle), "--as", ACTOR, "--json"],
        capture_output=True, text=True, env=env, check=True,
    )  # fmt: skip
    # 0.16 releases the lock after a converged direct apply; an older CLI
    # leaves it held. Unlock only what `cluster status` still reports.
    status = subprocess.run(
        [str(bin_dir / "omnigraph"), "cluster", "status", "--target", f"file://{root}",
         "--json"],
        capture_output=True, text=True, env=env, check=True,
    )  # fmt: skip
    lock = json.loads(status.stdout).get("lock_id")
    if lock:
        subprocess.run(
            [str(bin_dir / "omnigraph"), "--target", f"file://{root}", "cluster",
             "force-unlock", lock],
            capture_output=True, env=env, check=True,
        )  # fmt: skip
    token = os.urandom(12).hex()
    port = _free_port()
    proc = subprocess.Popen(
        [str(bin_dir / "omnigraph-server"), "--cluster", f"file://{root}",
         "--bind", f"127.0.0.1:{port}"],
        stdout=(work / "server.log").open("wb"), stderr=subprocess.STDOUT,
        env={**env, "OMNIGRAPH_SERVER_BEARER_TOKENS_JSON": json.dumps({ACTOR: token}),
             "OMNIGRAPH_OPERATION_ROUTES": "true"},
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
    assert (await og.health())["version"] == SERVER_VERSION
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


async def test_export_streams_ndjson(og: Omnigraph) -> None:
    await og.mutate(INSERT_PERSON, params={"n": "exported", "c": "Delft"})
    rows = [r async for r in og.export(type_names=["Person"])]
    assert any(r.get("data", {}).get("name") == "exported" for r in rows)
    assert all(r.get("type") == "Person" for r in rows)


async def test_load_ndjson_and_diff(og: Omnigraph) -> None:
    await og.branches.create("sdk_load")
    out = await og.load_ndjson(
        '{"type":"Company","data":{"name":"Loaded"}}\n', branch="sdk_load", mode="merge"
    )
    assert out
    diff = await og.diff("main", "sdk_load")
    assert diff["changes"], diff
    await og.branches.delete("sdk_load")


async def test_stored_query_catalog_and_unknown_name(og: Omnigraph) -> None:
    catalog = await og.queries.list()
    assert catalog["queries"] == []
    with pytest.raises(NotFoundError):
        await og.queries.invoke("nope")


async def test_change_feed_and_baseline(og: Omnigraph) -> None:
    page = await og.changes.poll(start="beginning", limit=5)
    assert isinstance(page["blocks"], list)
    assert page.get("cursor") or page.get("next_page_token")
    records = [r async for r in og.changes.baseline(type=["Company"])]
    assert "baseline" in records[-1]
    assert all("baseline" not in r for r in records[:-1])


async def test_blob_put_get_clear(og: Omnigraph) -> None:
    await og.mutate('query d() { insert Doc { slug: "d1" } }')
    sel = {"entity": "node", "type": "Doc", "id": "d1", "property": "body"}
    written = await og.blobs.put(b"hello blob", **sel)
    assert written["commit"] is not None
    got = await og.blobs.get(**sel)
    assert got.status_code == 200 and got.content == b"hello blob"
    head = await og.blobs.stat(**sel)
    assert head.status_code == 200 and head.headers.get("ETag")
    cleared = await og.blobs.clear(**sel)
    assert cleared["commit"] is not None


async def test_branch_list_detailed(og: Omnigraph) -> None:
    await og.branches.create("sdk_detail")
    await og.mutate(
        INSERT_PERSON, params={"n": "detail", "c": None}, branch="sdk_detail"
    )
    listed = await og.branches.list_detailed()
    assert "sdk_detail" in listed["branches"]
    details = {d["name"]: d for d in listed["details"]}
    assert [d["name"] for d in listed["details"]] == [
        b for b in listed["branches"] if b in details
    ]
    branch = details["sdk_detail"]
    assert branch.get("from") == "main" and branch.get("from_commit_id")
    assert branch["head"]["graph_commit_id"] != branch.get("from_commit_id")
    assert branch["updated_at"] >= (branch.get("created_at") or 0)
    assert "from" not in details["main"] or details["main"].get("from") is None
    await og.branches.delete("sdk_detail")


async def test_ranked_read_reports_ranking(og: Omnigraph) -> None:
    await og.mutate(
        'query s() { insert Spot { slug: "near", at: [0.0, 0.0] } '
        'insert Spot { slug: "far", at: [5.0, 5.0] } }'
    )
    read = await og.query(
        "query n($v: Vector(2)) { match { $s: Spot } "
        "return { $s.slug, nearest($s.at, $v) as dist } "
        "order { nearest($s.at, $v) } limit 2 }",
        params={"v": [0.1, 0.1]},
    )
    assert [r["s.slug"] for r in read["rows"]] == ["near", "far"]
    ranking = read.get("ranking")
    assert ranking is not None, read
    assert ranking["by"] == "nearest" and ranking["order"] == "ascending"
    assert ranking["score_columns"] == ["dist"]
    assert ranking["exhaustive"] is True


U64_MAX = 2**64 - 1


@pytest.mark.parametrize("value", [U64_MAX, str(U64_MAX)], ids=["number", "string"])
async def test_u64_parameter_above_i64_max_binds(og: Omnigraph, value: object) -> None:
    name = f"max-{type(value).__name__}"
    await og.mutate(
        "query c($k: String, $n: U64) { insert Counter { name: $k, n: $n } }",
        params={"k": name, "n": value},
    )
    read = await og.query(
        "query r($n: U64) { match { $c: Counter { n: $n } } return { $c.name, $c.n } }",
        params={"n": value},
    )
    assert {"c.name": name, "c.n": U64_MAX} in read["rows"], read["rows"]


async def test_access_reports_maintain_and_no_oauth_client(og: Omnigraph) -> None:
    access = await og.access(branch="main")
    assert "maintain" in access["actions"]
    assert access.get("client_id") is None  # a static token has no OAuth client


async def test_dry_run_merge_reports_without_writing(og: Omnigraph) -> None:
    await og.branches.create("sdk_dry")
    await og.mutate(INSERT_PERSON, params={"n": "dry", "c": None}, branch="sdk_dry")
    head = (await og.query(COUNT))["graph_commit_id"]
    preview = await og.branches.merge("sdk_dry", dry_run=True)
    assert preview["dry_run"] is True and preview["commit"] is None
    assert preview["outcome"] in ("fast_forward", "merged")
    assert (await og.query(COUNT))["graph_commit_id"] == head
    await og.branches.delete("sdk_dry")


async def test_recorded_optimize_submit_wait_lookup_cancel(og: Omnigraph) -> None:
    await og.mutate(INSERT_PERSON, params={"n": "opt", "c": None})
    op_id = new_operation_id()
    submitted = await og.operations.optimize(op_id, max_gate_hold_ms=30_000)
    assert submitted["lookup"] == "found"
    op = submitted.get("operation")
    assert op is not None and op["operation_id"] == op_id
    assert op["request"]["kind"] == "optimize"

    # The same id and request answers the existing record, starting nothing.
    again = await og.operations.optimize(op_id, max_gate_hold_ms=30_000)
    again_op = again.get("operation")
    assert again_op is not None and again_op["accepted_at"] == op["accepted_at"]

    async with asyncio.timeout(120):
        done = await og.operations.wait(op_id, interval=0.2)
    final = done.get("operation")
    assert final is not None and final["state"] == "succeeded", final
    assert is_terminal(final["state"]) and done["in_progress"] is False
    # A full run reports every dataset of the schema, under `datasets`.
    datasets = final["outcome"].get("datasets")
    assert datasets, final
    keys = {d["type_key"] for d in datasets}
    assert {"node:Person", "node:Company", "edge:WorksAt"} <= keys, keys
    for dataset in datasets:
        assert dataset["outcome"] in ("optimized", "unchanged", "deferred", "failed")

    # Cancelling a terminal operation leaves it unchanged.
    cancelled = await og.operations.cancel(op_id)
    cancelled_op = cancelled.get("operation")
    assert cancelled_op is not None and cancelled_op["state"] == "succeeded"

    # The same id with another request is refused, not run.
    with pytest.raises(ConflictError) as info:
        await og.operations.optimize(op_id, datasets=["node:Person"])
    assert info.value.outcome_unknown is False


async def test_a_run_limited_to_one_dataset_reports_exactly_it(og: Omnigraph) -> None:
    op_id = new_operation_id()
    await og.operations.optimize(op_id, datasets=["node:Person"])
    async with asyncio.timeout(120):
        done = await og.operations.wait(op_id, interval=0.05)
    op = done.get("operation")
    assert op is not None and op["request"].get("datasets") == ["node:Person"]
    assert [d["type_key"] for d in op["outcome"].get("datasets", [])] == ["node:Person"]


async def test_cancelling_an_active_run(og: Omnigraph) -> None:
    # A fixture run takes milliseconds, so cancel concurrently with the
    # submission: the first cancel that finds the record meets it accepted or
    # running unless the run already ended. Retry until one meets an active
    # run, then check the terminal record.
    for _ in range(50):
        op_id = new_operation_id()
        submit = asyncio.create_task(og.operations.optimize(op_id))
        while True:
            reply = await og.operations.cancel(op_id)
            if reply["lookup"] == "found":
                break
        await submit
        cancel = reply.get("operation")
        assert cancel is not None
        if is_terminal(cancel["state"]):
            continue
        async with asyncio.timeout(120):
            done = await og.operations.wait(op_id, interval=0.02)
        op = done.get("operation")
        assert op is not None
        if cancel["state"] == "publishing":
            # No cancellation is requested once publishing; it finishes.
            assert op["state"] == "succeeded"
        elif op["state"] == "cancelled":
            assert "published_commit" not in op
            assert "cancelled by" in op.get("reason", "")
        else:
            # omnigraph 0.16.0 settles a run's cancellation when it builds the
            # run's report, but keeps the record running until it writes the
            # terminal record; a cancel in that window is answered 202 and
            # the run ends succeeded with no reason. A reason, when present,
            # says the cancellation arrived late.
            assert op["state"] == "succeeded"
            reason = op.get("reason")
            assert reason is None or "a cancellation arrived after" in reason
        return
    pytest.fail("no cancel met an active run in 50 attempts")


async def test_unknown_operation_lookup(og: Omnigraph) -> None:
    looked = await og.operations.get(new_operation_id())
    assert looked["lookup"] == "unknown" and looked.get("operation") is None
    waited = await og.operations.wait(new_operation_id(), interval=0)
    assert waited["lookup"] == "unknown"


async def test_non_canonical_operation_id_is_refused(og: Omnigraph) -> None:
    with pytest.raises(BadRequestError) as info:
        await og.operations.optimize("not-a-ulid")
    assert info.value.outcome_unknown is False

"""Transport and client behaviour against a mocked server."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import omnigraph
from omnigraph import (
    ApiContractError,
    ConfigurationError,
    ConflictError,
    GraphUnavailableError,
    NetworkError,
    NotFoundError,
    Omnigraph,
    PayloadTooLargeError,
    PreconditionFailedError,
)

TOKEN = "secret-token-value"
CONTRACT = {"Omnigraph-Http-Api": "0.14"}

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, *, graph_id: str | None = "g") -> Omnigraph:
    return Omnigraph(
        "http://og.test/prefix",
        graph_id=graph_id,
        token=TOKEN,
        transport=httpx.MockTransport(handler),
    )


def _json(
    status: int, body: Any, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, json=body, headers={**CONTRACT, **(headers or {})})


def _error(status: int, code: str, effects: str, **extra: Any) -> httpx.Response:
    return _json(
        status,
        {"error": f"{code} happened", "code": code,
         "disposition": {"effects": effects, "action": "fix"}, **extra},
    )  # fmt: skip


class Recorder:
    """A handler that answers discovery and then the scripted data response."""

    def __init__(self, data: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._data = data

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "HEAD" and request.url.path.endswith("/healthz"):
            return httpx.Response(200, headers=CONTRACT)
        return self._data(request)

    @property
    def data_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "HEAD"]


SCHEMA = {"schema_source": "node A { k: String @key }\n"}


async def test_contract_header_auth_and_graph_prefix() -> None:
    rec = Recorder(lambda r: _json(200, SCHEMA))
    async with _client(rec) as og:
        out = await og.schema.get()
    assert out["schema_source"].startswith("node A")
    head, get = rec.requests
    assert head.method == "HEAD" and head.url.path == "/prefix/healthz"
    assert "authorization" not in head.headers
    assert get.url.path == "/prefix/graphs/g/schema"
    assert get.headers["Omnigraph-Http-Api"] == "0.14"
    assert get.headers["Authorization"] == f"Bearer {TOKEN}"


async def test_public_probes_skip_discovery_and_credentials() -> None:
    rec = Recorder(lambda r: _json(200, {"status": "ok", "version": "0.14.0"}))
    async with _client(rec) as og:
        await og.health()
    (req,) = rec.requests
    assert req.url.path == "/prefix/healthz"
    assert "authorization" not in req.headers


async def test_failed_discovery_sends_no_data_request() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)  # no contract header

    async with _client(handler) as og:
        with pytest.raises(ApiContractError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert [r.method for r in sent] == ["HEAD"]
    assert info.value.request_dispatched is False
    assert info.value.outcome_unknown is False


async def test_response_without_contract_header_is_untrusted() -> None:
    rec = Recorder(lambda r: httpx.Response(200, json={"commit": None}))
    async with _client(rec) as og:
        with pytest.raises(ApiContractError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert info.value.outcome_unknown is True


async def test_graph_scoped_call_without_graph_id_is_refused_before_sending() -> None:
    rec = Recorder(lambda r: _json(200, SCHEMA))
    async with _client(rec, graph_id=None) as og:
        with pytest.raises(ConfigurationError):
            await og.schema.get()
        assert await og.graph("h").schema.get() == SCHEMA
    assert [r.url.path for r in rec.data_requests] == ["/prefix/graphs/h/schema"]


@pytest.mark.parametrize(
    ("status", "code", "cls"),
    [
        (404, "not_found", NotFoundError),
        (409, "conflict", ConflictError),
        (412, "precondition_failed", PreconditionFailedError),
        (413, "payload_too_large", PayloadTooLargeError),
        (503, "graph_unavailable", GraphUnavailableError),
        (400, "api_contract_mismatch", ApiContractError),
    ],
)
async def test_errors_map_to_classes(
    status: int, code: str, cls: type[Exception]
) -> None:
    rec = Recorder(lambda r: _error(status, code, "none"))
    async with _client(rec) as og:
        with pytest.raises(cls) as info:
            await og.schema.get()
    err = info.value
    assert isinstance(err, omnigraph.OmnigraphError)
    assert err.status == status and err.code == code
    assert err.disposition == {"effects": "none", "action": "fix"}


async def test_merge_conflicts_are_exposed() -> None:
    conflict = {"entity_kind": "node", "type_name": "A", "entity_id": "x",
                "kind": "divergent_update", "message": "divergent update for id 'x'"}  # fmt: skip
    rec = Recorder(
        lambda r: _error(409, "conflict", "none", merge_conflicts=[conflict])
    )
    async with _client(rec) as og:
        with pytest.raises(ConflictError) as info:
            await og.branches.merge("s")
    assert info.value.merge_conflicts == [conflict]
    assert info.value.outcome_unknown is False


@pytest.mark.parametrize(("effects", "unknown"), [("none", False), ("unknown", True)])
async def test_write_outcome_follows_effects(effects: str, unknown: bool) -> None:
    rec = Recorder(lambda r: _error(400, "bad_request", effects))
    async with _client(rec) as og:
        with pytest.raises(omnigraph.BadRequestError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert info.value.outcome_unknown is unknown


async def test_a_read_error_is_never_outcome_unknown() -> None:
    rec = Recorder(lambda r: _error(400, "bad_request", "unknown"))
    async with _client(rec) as og:
        with pytest.raises(omnigraph.BadRequestError) as info:
            await og.query("query q() { match { $a: A } return { $a.k } }")
    assert info.value.outcome_unknown is False


async def test_transport_loss_after_dispatch_is_outcome_unknown() -> None:
    def data(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=request)

    async with _client(Recorder(data)) as og:
        with pytest.raises(NetworkError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert info.value.request_dispatched is True
    assert info.value.outcome_unknown is True


async def test_invalid_success_body_never_acknowledges_a_write() -> None:
    rec = Recorder(lambda r: httpx.Response(200, content=b"{trunc", headers=CONTRACT))
    async with _client(rec) as og:
        with pytest.raises(NetworkError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert info.value.outcome_unknown is True


async def test_the_token_never_appears_in_reprs_or_errors() -> None:
    rec = Recorder(lambda r: _error(403, "forbidden", "none"))
    og = _client(rec)
    assert TOKEN not in repr(og)
    with pytest.raises(omnigraph.ForbiddenError) as info:
        await og.schema.get()
    assert TOKEN not in str(info.value) and TOKEN not in repr(info.value)
    await og.aclose()


async def test_mutate_with_precondition_uses_the_conditional_route() -> None:
    receipt = {"branch": "main", "query_name": "a", "affected_nodes": 1,
               "affected_edges": 0, "commit": None}  # fmt: skip
    rec = Recorder(lambda r: _json(200, receipt))
    async with _client(rec) as og:
        await og.mutate('query a() { insert A { k: "x" } }', if_graph_commit="hb1.x")
    (req,) = rec.data_requests
    assert req.url.path == "/prefix/graphs/g/mutate/if-graph-commit"
    assert req.headers["Omnigraph-If-Graph-Commit"] == "hb1.x"
    assert json.loads(req.content)["query"].startswith("query a()")


def _merge(outcome: str, commit: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    return {"source": "s", "target": "main", "outcome": outcome, "commit": commit,
            "actor_id": "act", **extra}  # fmt: skip


COMMIT = {"graph_commit_id": "hb1.a", "graph_manifest_version": 3, "graph_branch": None,
          "parent_commit_id": "hb1.p", "merged_parent_commit_id": "hb1.m",
          "actor_id": "act", "published": True, "kind": "published"}  # fmt: skip


async def test_merge_receipt_is_validated() -> None:
    good = _merge("merged", COMMIT, branch_deleted=True)
    async with _client(Recorder(lambda r: _json(200, good))) as og:
        assert (await og.branches.merge("s", delete_branch=True))["branch_deleted"]
    wrong_source = {**good, "source": "other"}
    async with _client(Recorder(lambda r: _json(200, wrong_source))) as og:
        with pytest.raises(ApiContractError):
            await og.branches.merge("s", delete_branch=True)
    up_to_date_with_commit = _merge("already_up_to_date", COMMIT)
    async with _client(Recorder(lambda r: _json(200, up_to_date_with_commit))) as og:
        with pytest.raises(ApiContractError):
            await og.branches.merge("s")


async def test_commit_drop_expects_204() -> None:
    rec = Recorder(lambda r: httpx.Response(204, headers=CONTRACT))
    async with _client(rec) as og:
        await og.commits.drop("hb1.a")
    rec200 = Recorder(lambda r: _json(200, {}))
    async with _client(rec200) as og:
        with pytest.raises(ApiContractError):
            await og.commits.drop("hb1.a")


def test_base_url_must_be_a_plain_server_root() -> None:
    for bad in ("ftp://x", "http://u:p@x", "http://x?q=1", "http://x#f"):
        with pytest.raises(ConfigurationError):
            Omnigraph(bad)

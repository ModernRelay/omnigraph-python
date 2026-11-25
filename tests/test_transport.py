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
        (403, "forbidden", omnigraph.ForbiddenError),
        (403, "not_admitted", omnigraph.NotAdmittedError),
        # A code's class never overrides a status it does not refine.
        (409, "not_admitted", ConflictError),
        (418, "not_admitted", omnigraph.NotAdmittedError),
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


@pytest.mark.parametrize(
    ("status", "code", "effects", "unknown"),
    [
        (403, "not_admitted", "none", False),
        (403, "forbidden", "none", False),
        (500, "outcome_unknown", "unknown", True),
        (503, "service_unavailable", "none", False),
    ],
)
async def test_refused_write_disposition_without_retries(
    status: int, code: str, effects: str, unknown: bool
) -> None:
    rec = Recorder(lambda r: _error(status, code, effects))
    async with _client(rec) as og:
        with pytest.raises(omnigraph.OmnigraphError) as info:
            await og.mutate('query a() { insert A { k: "x" } }')
    assert info.value.code == code
    assert info.value.outcome_unknown is unknown
    assert len(rec.data_requests) == 1


async def test_a_read_refusal_the_server_calls_certain_is_not_outcome_unknown() -> None:
    # A read is uncertain only when the server says so (see
    # test_a_read_keeps_the_servers_word_on_uncertainty).
    rec = Recorder(lambda r: _error(400, "bad_request", "none"))
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


def _commit(cid: str, branch: str | None = None) -> dict[str, Any]:
    return {"graph_commit_id": cid, "graph_manifest_version": 3,
            "graph_branch": branch, "kind": "published", "published": True}  # fmt: skip


async def test_branch_list_detailed_asks_for_details() -> None:
    body = {
        "branches": ["feature", "main", "secret"],
        "details": [
            {"name": "feature", "head": _commit("c2", "feature"), "from": "main",
             "from_commit_id": "c1", "created_at": 1714000000000000,
             "updated_at": 1714000001000000},
            {"name": "main", "head": _commit("c1"), "updated_at": 1714000000000000},
        ],
    }  # fmt: skip
    rec = Recorder(lambda r: _json(200, body))
    async with _client(rec) as og:
        out = await og.branches.list_detailed()
    (req,) = rec.data_requests
    assert req.method == "GET" and req.url.params["detailed"] == "true"
    assert out["branches"] == ["feature", "main", "secret"]
    assert [d["name"] for d in out["details"]] == ["feature", "main"]
    assert out["details"][0]["from"] == "main"


async def test_branch_list_detailed_without_details_is_a_contract_error() -> None:
    rec = Recorder(lambda r: _json(200, {"branches": ["main"]}))
    async with _client(rec) as og:
        with pytest.raises(ApiContractError) as info:
            await og.branches.list_detailed()
    assert info.value.outcome_unknown is False


async def test_ranked_read_reports_its_ranking() -> None:
    body = {
        "query_name": "q", "target": {"branch": "main"}, "row_count": 1,
        "rows": [{"d.slug": "a", "score": 1.5}], "columns": ["d.slug", "score"],
        "ranking": {"by": "bm25", "order": "descending", "exhaustive": True,
                    "score_columns": ["score"]},
    }  # fmt: skip
    rec = Recorder(lambda r: _json(200, body))
    async with _client(rec) as og:
        out = await og.query("query q($t: String) { ... }", params={"t": "x"})
    ranking = out.get("ranking")
    assert ranking is not None
    assert ranking["by"] == "bm25" and ranking["order"] == "descending"
    assert ranking["score_columns"] == ["score"]


async def test_access_reports_the_oauth_client() -> None:
    body = {"graph_id": "g", "actor_id": "principal:p", "client_id": "studio",
            "actions": ["read"], "graph_wide": ["read"]}  # fmt: skip
    rec = Recorder(lambda r: _json(200, body))
    async with _client(rec) as og:
        out = await og.access()
    assert out.get("client_id") == "studio"


async def test_settings_travel_in_query_mutate_and_merge_bodies() -> None:
    def data(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/branches/merge"):
            return _json(200, {"source": "s", "target": "main", "dry_run": True,
                               "outcome": "fast_forward", "commit": None})  # fmt: skip
        if request.url.path.endswith("/mutate"):
            return _json(
                200, {"affected_nodes": 0, "affected_edges": 0, "commit": None}
            )
        return _json(200, {"query_name": "q", "target": {}, "row_count": 0, "rows": []})

    rec = Recorder(data)
    settings: Any = {"change_lineage": "verify"}
    async with _client(rec) as og:
        await og.query("query q() { ... }", settings=settings)
        await og.mutate("query m() { ... }", settings=settings)
        await og.branches.merge("s", dry_run=True, settings=settings)
    bodies = [json.loads(r.content) for r in rec.data_requests]
    assert [b["settings"] for b in bodies] == [settings] * 3


@pytest.mark.parametrize(
    ("status", "code", "field", "cls", "accessor"),
    [
        (409, "conflict", "read_set_conflict", ConflictError, "read_set_conflict"),
        (409, "conflict", "published_dataset_version_conflict", ConflictError,
         "published_dataset_version_conflict"),
        (409, "conflict", "change_diff_refusal", ConflictError, "change_diff_refusal"),
        (409, "conflict", "full_text_index_rebuild_required", ConflictError,
         "full_text_index_rebuild_required"),
        (410, "change_feed_gap", "change_feed_gap", omnigraph.GoneError,
         "change_feed_gap"),
        (416, "range_not_satisfiable", "blob_range",
         omnigraph.RangeNotSatisfiableError, "blob_range"),
        (424, "external_blob_source", "external_blob_source",
         omnigraph.FailedDependencyError, "external_blob_source"),
        (503, "recovery_required", "recovery_required",
         omnigraph.ServiceUnavailableError, "recovery_required"),
    ],
)  # fmt: skip
async def test_error_details_are_exposed(
    status: int, code: str, field: str, cls: type[Exception], accessor: str
) -> None:
    detail = {"marker": field}
    rec = Recorder(lambda r: _error(status, code, "none", **{field: detail}))
    async with _client(rec) as og:
        with pytest.raises(cls) as info:
            await og.schema.get()
    assert getattr(info.value, accessor) == detail


@pytest.mark.parametrize(
    ("body", "status", "unknown"),
    [
        # code outcome_unknown wins over any disposition it carries
        ({"error": "resolution write in doubt", "code": "outcome_unknown",
          "disposition": {"effects": "none", "action": "reconcile"}}, 500, True),
        ({"error": "in doubt", "code": "outcome_unknown"}, 500, True),
        ({"error": "in doubt", "code": "internal",
          "disposition": {"effects": "unknown", "action": "reconcile"}}, 500, True),
        ({"error": "half", "code": "conflict",
          "disposition": {"effects": "partial", "action": "refresh"}}, 409, True),
        ({"error": "retry", "code": "service_unavailable",
          "disposition": {"effects": "none", "action": "retry"}}, 503, False),
        ("gateway timeout", 500, False),
    ],
)  # fmt: skip
async def test_a_read_keeps_the_servers_word_on_uncertainty(
    body: Any, status: int, unknown: bool
) -> None:
    rec = Recorder(lambda r: _json(status, body))
    async with _client(rec) as og:
        with pytest.raises(omnigraph.OmnigraphError) as info:
            await og.snapshot()
    assert info.value.status == status
    assert info.value.outcome_unknown is unknown
    assert len(rec.data_requests) == 1


async def test_a_write_without_a_valid_body_stays_uncertain() -> None:
    rec = Recorder(
        lambda r: httpx.Response(502, content=b"bad gateway", headers=CONTRACT)
    )
    async with _client(rec) as og:
        with pytest.raises(omnigraph.OmnigraphError) as info:
            await og.mutate('query q() { insert A { k: "x" } }')
    assert info.value.outcome_unknown is True

"""Recorded operations against a mocked server."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx
import pytest

import omnigraph
from omnigraph import Omnigraph, is_terminal, new_operation_id

CONTRACT = {"Omnigraph-Http-Api": "0.14"}
OP_ID = "01JC0000000000000000000000"


def _record(state: str, **extra: Any) -> dict[str, Any]:
    return {
        "operation_id": OP_ID, "request_digest": "sha256:x", "graph": "g",
        "schema_identity_domain": "d", "settlement_branch": "main",
        "request": {"kind": "optimize"}, "principal": "act", "accepted_at": "t",
        "state": state, "outcome": {"kind": "optimize"}, "timings": {}, **extra,
    }  # fmt: skip


class Server:
    def __init__(self, *answers: tuple[int, Any]) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers=CONTRACT)
        self.requests.append(request)
        status, body = self.answers.pop(0)
        return httpx.Response(status, json=body, headers=CONTRACT)


def _client(server: Server) -> Omnigraph:
    return Omnigraph(
        "http://og.test", graph_id="g", transport=httpx.MockTransport(server)
    )


def test_new_operation_id_is_a_canonical_ulid() -> None:
    before = time.time_ns() // 1_000_000
    ids = {new_operation_id() for _ in range(64)}
    after = time.time_ns() // 1_000_000
    assert len(ids) == 64
    crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    for op_id in ids:
        assert re.fullmatch(r"[0-7][0-9A-HJKMNP-TV-Z]{25}", op_id), op_id
        stamp = 0
        for ch in op_id[:10]:
            stamp = stamp * 32 + crockford.index(ch)
        assert before <= stamp <= after


@pytest.mark.parametrize(
    ("state", "terminal"),
    [("accepted", False), ("running", False), ("publishing", False),
     ("succeeded", True), ("failed", True), ("cancelled", True),
     ("interrupted", True), ("unsettled", True)],
)  # fmt: skip
def test_terminal_states(state: str, terminal: bool) -> None:
    assert is_terminal(state) is terminal


async def test_optimize_submits_the_callers_id_and_returns_202_record() -> None:
    server = Server((202, {"lookup": "found", "in_progress": True,
                           "operation": _record("accepted")}))  # fmt: skip
    async with _client(server) as og:
        out = await og.operations.optimize(
            OP_ID, datasets=["node:Person"], max_gate_hold_ms=30_000
        )
    (req,) = server.requests
    assert req.method == "POST"
    assert req.url.path == "/graphs/g/operations/optimize"
    assert json.loads(req.content) == {
        "operation_id": OP_ID, "datasets": ["node:Person"], "max_gate_hold_ms": 30_000,
    }  # fmt: skip
    op = out.get("operation")
    assert out["lookup"] == "found" and op is not None and op["state"] == "accepted"


async def test_optimize_sends_only_the_id_by_default() -> None:
    server = Server((200, {"lookup": "found", "in_progress": False,
                           "operation": _record("succeeded")}))  # fmt: skip
    async with _client(server) as og:
        await og.operations.optimize(OP_ID)
    assert json.loads(server.requests[0].content) == {"operation_id": OP_ID}


async def test_optimize_refuses_one_string_as_datasets_before_sending() -> None:
    server = Server()
    async with _client(server) as og:
        with pytest.raises(TypeError, match="list of type keys"):
            await og.operations.optimize(OP_ID, datasets="node:Person")
    assert server.requests == []


async def test_lost_submission_is_outcome_unknown_and_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers=CONTRACT)
        raise httpx.ReadError("reset", request=request)

    calls: list[httpx.Request] = []

    def counting(request: httpx.Request) -> httpx.Response:
        if request.method != "HEAD":
            calls.append(request)
        return handler(request)

    async with Omnigraph(
        "http://og.test", graph_id="g", transport=httpx.MockTransport(counting)
    ) as og:
        with pytest.raises(omnigraph.NetworkError) as info:
            await og.operations.optimize(OP_ID)
    assert info.value.outcome_unknown is True
    assert len(calls) == 1


async def test_get_and_cancel_routes() -> None:
    server = Server(
        (200, {"lookup": "unknown", "in_progress": False}),
        (
            202,
            {"lookup": "found", "in_progress": True, "operation": _record("running")},
        ),
    )
    async with _client(server) as og:
        looked = await og.operations.get(OP_ID)
        cancelled = await og.operations.cancel(OP_ID)
    assert [(r.method, r.url.path) for r in server.requests] == [
        ("GET", f"/graphs/g/operations/{OP_ID}"),
        ("POST", f"/graphs/g/operations/{OP_ID}/cancel"),
    ]
    assert looked["lookup"] == "unknown" and "operation" not in looked
    assert cancelled["in_progress"] is True


async def test_a_refused_cancel_is_not_outcome_unknown() -> None:
    server = Server((503, {"error": "[state_read_error] x", "code": "service_unavailable",
                           "disposition": {"effects": "none", "action": "retry"}}))  # fmt: skip
    async with _client(server) as og:
        with pytest.raises(omnigraph.ServiceUnavailableError) as info:
            await og.operations.cancel(OP_ID)
    assert info.value.outcome_unknown is False


async def test_wait_polls_the_lookup_until_terminal() -> None:
    outcome = {"kind": "optimize", "datasets": [
        {"type_key": "node:Person", "outcome": "optimized", "reason": "index_failed",
         "detail": "boom", "fragments_removed": 2, "fragments_added": 1,
         "duration_ms": 5}], "more_datasets": {"deferred:gate_hold_limit": 3}}  # fmt: skip
    server = Server(
        (200, {"lookup": "found", "in_progress": True, "operation": _record("running")}),
        (200, {"lookup": "found", "in_progress": True,
               "operation": _record("publishing")}),
        (200, {"lookup": "found", "in_progress": False,
               "operation": _record("succeeded", published_commit="c9",
                                    outcome=outcome)}),
    )  # fmt: skip
    async with _client(server) as og:
        out = await og.operations.wait(OP_ID, interval=0)
    assert [r.method for r in server.requests] == ["GET"] * 3
    op = out.get("operation")
    assert op is not None and op["state"] == "succeeded"
    assert op["outcome"].get("more_datasets") == {"deferred:gate_hold_limit": 3}
    assert op["outcome"].get("datasets", [])[0].get("reason") == "index_failed"


async def test_wait_stops_at_an_unknown_lookup() -> None:
    server = Server((200, {"lookup": "unknown", "in_progress": False}))
    async with _client(server) as og:
        out = await og.operations.wait(OP_ID, interval=0)
    assert out["lookup"] == "unknown" and len(server.requests) == 1


async def test_wait_does_not_retry_an_error() -> None:
    server = Server(
        (200, {"lookup": "found", "in_progress": True, "operation": _record("running")}),
        (500, {"error": "x", "code": "internal",
               "disposition": {"effects": "none", "action": "retry"}}),
    )  # fmt: skip
    async with _client(server) as og:
        with pytest.raises(omnigraph.InternalServerError):
            await og.operations.wait(OP_ID, interval=0)
    assert len(server.requests) == 2


async def test_wait_is_bounded_by_the_caller() -> None:
    running = {"lookup": "found", "in_progress": True, "operation": _record("running")}
    server = Server(*[(200, running)] * 1000)
    async with _client(server) as og:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await og.operations.wait(OP_ID, interval=0.01)

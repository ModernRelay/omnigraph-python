"""Recorded operations (server 0.16+): submit, look up, cancel and wait.

A cluster server with `OMNIGRAPH_OPERATION_ROUTES=true` runs `optimize` on a
graph's `main` as a recorded operation, tracked by an id the caller chose.
Every route needs the `maintain` action on `main`.

The spec leaves the operation record an open object; the `TypedDict`s here
describe the record as server 0.16 writes it, with its wire names. A later
server may add fields.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence
from typing import Any, Literal, NotRequired, TypedDict, cast
from urllib.parse import quote

from ._models import OperationLookup
from ._transport import Transport

OperationState = Literal[
    "accepted",
    "running",
    "publishing",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "unsettled",
]

#: States an operation never leaves. `unsettled` means its publication can no
#: longer be answered (the graph was deleted while it was in doubt).
TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted", "unsettled"}
)


def is_terminal(state: str) -> bool:
    """Whether an operation in `state` is finished."""
    return state in TERMINAL_STATES


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_operation_id() -> str:
    """A fresh canonical ULID to submit an operation under.

    Mint it, keep it, then submit: after a lost response, look the same id
    up instead of submitting again.
    """
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(os.urandom(10))
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


class OptimizeRequestRecord(TypedDict):
    """The request an operation was submitted with."""

    kind: Literal["optimize"]
    datasets: NotRequired[list[str]]
    max_gate_hold_ms: NotRequired[int]


class TableOutcome(TypedDict):
    """One dataset's outcome in an optimize run."""

    type_key: str
    #: `optimized`, `unchanged`, `deferred` or `failed`.
    outcome: str
    #: Why a `deferred` dataset was not started, or `index_failed` on an
    #: `optimized` one whose index work failed after its compaction committed.
    reason: NotRequired[str]
    detail: NotRequired[str]
    fragments_removed: int
    fragments_added: int
    duration_ms: int
    source_bytes: NotRequired[int]


class TailOutcome(TypedDict):
    """An outcome after the graph commit; it never fails the operation."""

    outcome: str
    detail: NotRequired[str]


class OptimizeOutcome(TypedDict):
    kind: Literal["optimize"]
    start_at: NotRequired[str]
    #: At most 1,024 datasets, in visit order.
    datasets: NotRequired[list[TableOutcome]]
    #: Datasets beyond the listed ones, counted by `outcome` or
    #: `outcome:reason` (for example `deferred:gate_hold_limit`).
    more_datasets: NotRequired[dict[str, int]]
    resume_at: NotRequired[str]
    configuration_clear: NotRequired[TailOutcome]
    artifact: NotRequired[TailOutcome]


class ResolutionProgress(TypedDict):
    """Where a `publishing` operation's history walk stands."""

    cursor: NotRequired[str]
    visited: int


class OperationTimings(TypedDict, total=False):
    queued_ms: int
    gate_hold_ms: int
    compute_ms: int


class Operation(TypedDict):
    """A recorded operation, with the server's field names."""

    operation_id: str
    request_digest: str
    graph: str
    schema_identity_domain: str
    settlement_branch: str
    request: OptimizeRequestRecord
    principal: str
    accepted_at: str
    state: OperationState
    nonce: NotRequired[str]
    input_commit: NotRequired[str]
    input_manifest_version: NotRequired[int]
    published_commit: NotRequired[str]
    resolution: NotRequired[ResolutionProgress]
    outcome: OptimizeOutcome
    timings: OperationTimings
    reason: NotRequired[str]


class OperationResult(TypedDict):
    """A submission, lookup or cancellation answer. `lookup: "unknown"` has no
    `operation`; it does not prove the operation never ran, and is never a
    reason to resubmit the same work under the same id."""

    lookup: OperationLookup
    in_progress: bool
    operation: NotRequired[Operation | None]


class Operations:
    """`og.operations`: recorded operations on the client's graph."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def optimize(
        self,
        operation_id: str,
        *,
        datasets: Sequence[str] | None = None,
        max_gate_hold_ms: int | None = None,
        if_actor: str | None = None,
    ) -> OperationResult:
        """Submit an optimize run of `main` under `operation_id`, a canonical
        ULID from `new_operation_id()`.

        `datasets` limits the run to these type keys (`node:Person`,
        `edge:Knows`), in order; `max_gate_hold_ms` bounds how long writers to
        `main` wait, within the server's ceiling. The answer is the record:
        accepted or running (HTTP 202), or terminal (200). Submitting the same
        id with the same request returns the existing record. After an
        `outcome_unknown` error, look the id up with `get`.
        """
        body: dict[str, Any] = {"operation_id": operation_id}
        if isinstance(datasets, str):
            # A str is a Sequence[str] of characters; sending it would record
            # one dataset key per character under this id.
            raise TypeError("datasets must be a list of type keys, not one string")
        if datasets is not None:
            body["datasets"] = list(datasets)
        if max_gate_hold_ms is not None:
            body["max_gate_hold_ms"] = max_gate_hold_ms
        return cast(
            OperationResult,
            await self._t.request(
                "POST", "/operations/optimize", body=body, if_actor=if_actor
            ),
        )

    async def get(
        self, operation_id: str, *, if_actor: str | None = None
    ) -> OperationResult:
        """Look an operation up by its id, whatever its kind."""
        return cast(
            OperationResult,
            await self._t.request(
                "GET", f"/operations/{quote(operation_id, safe='')}", if_actor=if_actor
            ),
        )

    async def cancel(
        self, operation_id: str, *, if_actor: str | None = None
    ) -> OperationResult:
        """Ask an operation to stop at its next safe boundary. A terminal
        operation is unchanged; a `publishing` one finishes its publication."""
        return cast(
            OperationResult,
            await self._t.request(
                "POST",
                f"/operations/{quote(operation_id, safe='')}/cancel",
                if_actor=if_actor,
            ),
        )

    async def wait(
        self,
        operation_id: str,
        *,
        interval: float = 1.0,
        if_actor: str | None = None,
    ) -> OperationResult:
        """Look the operation up every `interval` seconds until it is terminal
        or the lookup answers `unknown`, and return that answer.

        Only the read route is called, and an error ends the wait: nothing is
        retried. Bound the wait with `asyncio.timeout(...)`.
        """
        while True:
            result = await self.get(operation_id, if_actor=if_actor)
            operation = result.get("operation")
            if (
                result["lookup"] == "unknown"
                or operation is None
                or is_terminal(operation["state"])
            ):
                return result
            await asyncio.sleep(interval)

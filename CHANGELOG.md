# Changelog

The package's major.minor follows the `omnigraph-server` release it is generated from; the
patch number is the SDK's own. Every release so far speaks HTTP contract 0.14.

## 0.16.0

Generated from and tested against `omnigraph-server` 0.16.0, which still speaks HTTP contract
0.14. The additions below need server 0.16.

### Added

- `og.operations` for recorded operations: `optimize(operation_id, datasets=...,
  max_gate_hold_ms=...)`, `get`, `cancel`, and `wait`, which polls the lookup until the record
  is terminal. The caller mints the id with `new_operation_id()` and keeps it before
  submitting; `optimize` never mints one. `is_terminal()`
  and `TERMINAL_STATES` name the final states. `Operation`, `OperationResult`,
  `OptimizeOutcome` and `DatasetOutcome` type the record.
- `WriterFencedError`, a `ConflictError`, for the new `writer_fenced` code, with
  `writer_fenced` (`current`, `held`, `read` epochs). A refused write is not `outcome_unknown`.
- Types for the `maintain` access action and `WriterFencedOutput`.

### Fixed

- Every operation route accepts only a receipt for the id it was given: a lookup envelope
  whose `found` record names that id, or `unknown` where the route can answer it (lookup and
  cancel). Anything else raises `ApiContractError`, `outcome_unknown` after a submission or
  cancellation. Before, `{}` under HTTP 200 counted as an accepted operation.
- `optimize(datasets="node:Person")` raises `TypeError` instead of sending one key per
  character.

### Changed

- A `branches.merge(dry_run=True)` whose answer is lost is no longer `outcome_unknown`: a dry
  run is a read, as the 0.16 CLI now reports it. A reply that contradicts the dry run still is.

### Server changes that affect callers

- A graph with no applied policy refuses reads (`ForbiddenError`) unless the server sets
  `OMNIGRAPH_ALLOW_READS_WITHOUT_POLICY=1`.
- A request setting above the server's resource budget is refused with `BadRequestError`.
- A conditional mutation that loses a race fails with `PreconditionFailedError`, not a `@card`
  violation.
- A Blob write on a recreated branch fails with `ConflictError.read_set_conflict`; an update,
  delete or overwrite load overtaken by another commit reruns instead of failing.
- Deployment routes answer a failed control-state read with 503 (retry) or 500, with
  `effects: none`, instead of 409.
- A recorded-operation lookup can answer 500 `outcome_unknown` when a settlement write it made
  has no definite answer; it is `outcome_unknown`, and retrying the lookup is safe. `cancel`
  is best effort and returns a `publishing` operation unchanged.
- A merge refused by its validation limit names the resource
  `branch-merge retained validation key bytes` (it was `… delta bytes`) and counts only the
  delta's keys. `PayloadTooLargeError.resource_limit` already carries the new name; match on
  the code, not the name.

## 0.15.0

Generated from and tested against `omnigraph-server` 0.15.0. Works with any server that
speaks HTTP contract 0.14; the additions below need server 0.15.

### Fixed

- The `Omnigraph-Http-Api` header is read from the server's OpenAPI document instead of being
  derived from the server's minor version. Server 0.15 still speaks contract 0.14, so deriving
  it would have sent `0.15` and failed every request with `api_contract_mismatch`.
- An error reply that says a write may have taken effect sets `outcome_unknown` on every
  route, reads included: code `outcome_unknown` always (whatever its disposition reads), and
  otherwise effects `unknown` or `partial`. Before, a GET could never be `outcome_unknown`.

### Added

- `branches.list_detailed()` (`GET /branches?detailed=true`): each readable branch's head,
  start (`from`, `from_commit_id`), `created_at` and `updated_at`.
- `NotAdmittedError`, a `ForbiddenError`, for the new `not_admitted` code: a valid OIDC token
  whose subject the server does not admit. A refused write is not `outcome_unknown`.
- `settings=` on `query`, `mutate` and `branches.merge`, including the new `change_lineage`
  setting.
- Types for `ReadOutput.ranking` (`RankingOutput`, `SearchFunction`, `RankOrder`),
  `AccessOutput.client_id` and `LoadSliceExecutedOutput.read_ns`.
- Error detail properties matching the TypeScript SDK: `ConflictError.read_set_conflict`,
  `.published_dataset_version_conflict`, `.change_diff_refusal`,
  `.full_text_index_rebuild_required`; `GoneError.change_feed_gap`;
  `RangeNotSatisfiableError.blob_range`; `FailedDependencyError.external_blob_source`;
  `ServiceUnavailableError.recovery_required`.

### Changed

- An error's class is chosen by one rule: the status picks the class, and the code's class
  replaces it when it is a subclass of it.
- `U64` parameters above `i64::MAX` now bind on the server; Python sends them exactly.

## 0.14.0

First release, for `omnigraph-server` 0.14.

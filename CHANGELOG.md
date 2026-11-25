# Changelog

The package's major.minor follows the `omnigraph-server` release it is generated from; the
patch number is the SDK's own. Every release so far speaks HTTP contract 0.14.

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

# AGENTS.md

Python SDK for the Omnigraph HTTP API. Reference implementation: `ModernRelay/omnigraph-ts`
(`packages/sdk`), pinned to the same server release. Match its behaviour (contract header,
discovery, no retries, no redirects, receipt validation, error classes); use Python idioms
for names and shapes.

- The server version lives in `pyproject.toml` `[tool.omnigraph] server-version`. Bumping it:
  `scripts/sync_spec.py`, then `scripts/generate.py`, then run the e2e suite against that
  release's binaries.
- Versioning: the package's major.minor equals the server's contract (`generate.py --check`
  enforces it); bump the patch for an SDK-only fix, the minor only with `server-version`.
- `src/omnigraph/_models.py` and `_version.py` are generated; never edit them by hand.
  `scripts/generate.py --check` must pass.
- Public results are the generated `TypedDict`s; do not rename wire fields.
- Never add automatic retries. A lost write response is `outcome_unknown`, not a retry signal.
- Runtime dependency: `httpx` only.
- Checks: `uv run pytest`, `uv run mypy`, `uv run ruff check .`, `uv run ruff format --check .`;
  e2e with `OMNIGRAPH_TEST_SERVER=1 OMNIGRAPH_BIN_DIR=...` (needs a free local port).

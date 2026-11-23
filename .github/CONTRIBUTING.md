# Contributing to sentinel-mcp

Thank you for considering a contribution.

## Ground rules

1. **Determinism first.** Tool outputs must be reproducible for identical
   inputs; no wall-clock time or unseeded randomness in scoring paths.
   (Audit entries may carry caller-provided timestamps; chain hashing is
   canonical and deterministic.)
2. **Fail closed.** The policy gate and audit ledger must never open or
   validate on infrastructure errors.
3. **Honest degradation.** FalkorDB-backed graph memory must silently fall
   back to the embedded SQLite backend when FalkorDB is unreachable, and the
   active backend must be observable.
4. **Dual-SDK parity.** Every server-level feature must work on both `mcp`
   1.x (FastMCP) and 2.x (MCPServer).
5. **Zero third-party scaffolding strings** in commits or docs.

## Development setup

```bash
git clone https://github.com/Sandeep-Hipparagi/sentinel-mcp.git
cd sentinel-mcp
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before opening a PR

```bash
ruff check .
ruff format --check .
mypy --strict src tests
pytest
sentinel-mcp conformance
```

All five must pass. CI enforces the same checks.

## Adding a tool

1. Implement the pure logic in `src/sentinel_mcp/tools/` (SDK-independent).
2. Register it in `src/sentinel_mcp/server.py` with a Pydantic-typed signature.
3. Add unit tests plus a conformance check in `src/sentinel_mcp/conformance.py`.
4. Document the tool schema in README's tool reference table.

## Commit style

Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `perf:`).

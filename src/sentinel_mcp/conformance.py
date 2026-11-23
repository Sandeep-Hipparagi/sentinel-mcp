"""Built-in conformance self-test: `sentinel-mcp conformance`.

Verifies, without any external service: tool registration, schema-validated
round-trips, WORM chain integrity + tamper detection, policy fail-closed
behavior, memory fallback, and tool latency (p95 budget 5 ms).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from sentinel_mcp.schemas import (
    MemoryEdgeInput,
    MemoryQueryInput,
    MemoryUpsertInput,
    PolicyCheckInput,
    VerifyClaimInput,
)
from sentinel_mcp.server import TOOL_NAMES, build_server
from sentinel_mcp.tools.audit_log import WormAuditLedger
from sentinel_mcp.tools.graph_memory import GraphMemory
from sentinel_mcp.tools.policy_check import PolicyGate
from sentinel_mcp.tools.verify_claim import verify_claim

P95_BUDGET_MS = 5.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _check_tool_logic() -> list[CheckResult]:
    results: list[CheckResult] = []
    out = verify_claim(
        VerifyClaimInput(
            claim_text="Officials confirmed the merger on 2026-01-15.",
            url="https://www.reuters.com/p/1",
        )
    )
    results.append(
        CheckResult(
            "verify_claim: primary source citable",
            out.citable and out.source_tier == 1,
            out.rationale,
        )
    )
    sat = verify_claim(
        VerifyClaimInput(
            claim_text="Sources say everyone knows the shocking news.",
            url="https://www.theonion.com/a",
        )
    )
    results.append(
        CheckResult(
            "verify_claim: satire blocked",
            (not sat.citable) and sat.source_tier == 5,
            sat.rationale,
        )
    )
    return results


def _check_policy_gate() -> list[CheckResult]:
    results: list[CheckResult] = []
    gate = PolicyGate()
    ok = gate.check(PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "hello"}))
    results.append(
        CheckResult(
            "policy_check: allowlisted tool passes",
            ok.allowed and ok.reason_code == "OK",
            ok.reason_code,
        )
    )
    blocked = gate.check(PolicyCheckInput(tool_name="shell_exec", args={}))
    results.append(
        CheckResult(
            "policy_check: unknown tool denied",
            (not blocked.allowed) and blocked.reason_code == "POL_TOOL_BLOCKED",
            blocked.reason_code,
        )
    )
    pollution = gate.check(
        PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "x", "__proto__": {}})
    )
    results.append(
        CheckResult(
            "policy_check: prototype-pollution denied",
            (not pollution.allowed) and pollution.reason_code == "POL_ARG_FORBIDDEN_KEY",
            pollution.reason_code,
        )
    )
    bound = gate.check(
        PolicyCheckInput(tool_name="memory_query", args={"node_id": "n", "max_depth": 99})
    )
    results.append(
        CheckResult(
            "policy_check: argument bound enforced",
            (not bound.allowed) and bound.reason_code == "POL_ARG_BOUND",
            bound.reason_code,
        )
    )
    return results


def _check_worm_chain() -> list[CheckResult]:
    results: list[CheckResult] = []
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.jsonl"
        ledger = WormAuditLedger(path)
        for i in range(10):
            ledger.append({"action": f"op-{i}", "target": f"t{i}"})
        status = ledger.verify_chain()
        results.append(
            CheckResult(
                "audit: 10-append chain valid",
                status.valid and status.length == 10,
                f"root={status.merkle_root[:12]}...",
            )
        )
        # Single-block tamper: rewrite entry 4 in place.
        lines = path.read_text(encoding="utf-8").splitlines()
        entry = __import__("json").loads(lines[3])
        entry["event"]["action"] = "TAMPERED"
        lines[3] = __import__("json").dumps(entry, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered = WormAuditLedger(path)
        status_bad = tampered.verify_chain()
        results.append(
            CheckResult(
                "audit: single-block tamper detected",
                (not status_bad.valid) and status_bad.first_bad_sequence == 4,
                f"first_bad_sequence={status_bad.first_bad_sequence}",
            )
        )
    return results


def _check_memory_fallback() -> list[CheckResult]:
    results: list[CheckResult] = []
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        mem = GraphMemory(sqlite_path=Path(td) / "mem.db")
        mem.upsert_node(
            MemoryUpsertInput(node_id="svc-a", labels=["Service"], properties={"tier": 1})
        )
        mem.upsert_node(MemoryUpsertInput(node_id="svc-b", labels=["Service"], properties={}))
        mem.add_edge(MemoryEdgeInput(src="svc-a", relation="DEPENDS_ON", dst="svc-b"))
        out = mem.query_neighbors(MemoryQueryInput(node_id="svc-a", max_depth=2))
        ids = {n["id"] for n in out.nodes}
        results.append(
            CheckResult(
                f"memory: SQLite graph round-trip (backend={out.backend})",
                {"svc-a", "svc-b"} <= ids and len(out.edges) >= 1,
                f"nodes={len(out.nodes)} edges={len(out.edges)}",
            )
        )
        mem.close()
    return results


def _check_latency() -> list[CheckResult]:
    results: list[CheckResult] = []
    samples: list[float] = []
    for _ in range(200):
        start = time.perf_counter()
        verify_claim(
            VerifyClaimInput(
                claim_text="The bank raised rates in 2026.", url="https://apnews.com/x"
            )
        )
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    p95 = samples[int(0.95 * (len(samples) - 1))]
    results.append(
        CheckResult(
            f"latency: verify_claim p95 = {p95:.3f} ms (< {P95_BUDGET_MS} ms)",
            p95 < P95_BUDGET_MS,
            f"p95={p95:.3f}",
        )
    )
    return results


def _check_server_registration() -> list[CheckResult]:
    results: list[CheckResult] = []
    server = build_server()
    results.append(
        CheckResult(
            "server: builds for installed SDK generation",
            server is not None,
            type(server).__module__,
        )
    )
    results.append(
        CheckResult("server: 7 tools registered", len(TOOL_NAMES) == 7, ", ".join(TOOL_NAMES))
    )
    return results


CHECKS: list[Callable[[], list[CheckResult]]] = [
    _check_server_registration,
    _check_tool_logic,
    _check_policy_gate,
    _check_worm_chain,
    _check_memory_fallback,
    _check_latency,
]


def run_conformance() -> int:
    """Run all conformance checks; return process exit code (0 = pass)."""
    console = Console()
    all_results: list[CheckResult] = []
    for check in CHECKS:
        try:
            all_results.extend(check())
        except Exception as e:  # noqa: BLE001 - conformance must report, not crash
            all_results.append(CheckResult(check.__name__, False, f"exception: {e}"))

    table = Table(title="sentinel-mcp conformance")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for r in all_results:
        table.add_row(r.name, "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]", r.detail)
    console.print(table)

    failed = [r for r in all_results if not r.passed]
    if failed:
        console.print(f"[red]{len(failed)} conformance check(s) failed.[/red]")
        return 1
    console.print(f"[green]All {len(all_results)} conformance checks passed.[/green]")
    return 0

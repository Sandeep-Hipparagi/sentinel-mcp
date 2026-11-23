"""Server wiring tests (dual SDK generation) and latency budget tests."""

import time

import pytest

from sentinel_mcp.schemas import VerifyClaimInput
from sentinel_mcp.server import TOOL_NAMES, build_server, server_generation
from sentinel_mcp.tools.policy_check import PolicyGate
from sentinel_mcp.tools.verify_claim import verify_claim


class TestServerWiring:
    def test_generation_is_reported(self):
        assert server_generation() in {"1.x-fastmcp", "2.x-mcpserver"}

    def test_build_returns_server(self):
        server = build_server()
        assert server is not None

    def test_seven_tools_declared(self):
        assert TOOL_NAMES == (
            "verify_claim",
            "policy_check",
            "audit_append",
            "audit_verify",
            "memory_upsert",
            "memory_add_edge",
            "memory_query",
        )

    @pytest.mark.skipif(server_generation() != "2.x-mcpserver", reason="mcp 2.x only")
    def test_mcp2_registers_all_tools(self):
        server = build_server()
        import anyio

        async def _list():
            return await server.list_tools()

        tools = anyio.run(_list)
        declared = {t.name for t in tools}
        assert declared == set(TOOL_NAMES)

    @pytest.mark.skipif(server_generation() != "2.x-mcpserver", reason="mcp 2.x only")
    def test_mcp2_input_schemas_are_objects(self):
        server = build_server()
        import anyio

        async def _list():
            return await server.list_tools()

        tools = anyio.run(_list)
        for tool in tools:
            schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema
            assert schema.get("type") == "object", tool.name


class TestLatencyBudget:
    P95_BUDGET_MS = 5.0

    def _p95(self, fn, n: int = 300) -> float:
        samples = []
        for _ in range(n):
            start = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - start) * 1000.0)
        samples.sort()
        return samples[int(0.95 * (len(samples) - 1))]

    def test_verify_claim_p95_under_budget(self):
        p95 = self._p95(
            lambda: verify_claim(
                VerifyClaimInput(claim_text="x" * 200, url="https://reuters.com/a")
            )
        )
        assert p95 < self.P95_BUDGET_MS, f"p95={p95:.3f} ms exceeds {self.P95_BUDGET_MS} ms"

    def test_policy_gate_p95_under_budget(self):
        gate = PolicyGate()
        p95 = self._p95(
            lambda: gate.check(
                __import__("sentinel_mcp.schemas", fromlist=["PolicyCheckInput"]).PolicyCheckInput(
                    tool_name="verify_claim", args={"claim_text": "hello world"}
                )
            )
        )
        assert p95 < self.P95_BUDGET_MS, f"p95={p95:.3f} ms exceeds {self.P95_BUDGET_MS} ms"

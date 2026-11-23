"""MCP server wiring: dual-generation support for mcp 1.x (FastMCP) and 2.x (MCPServer).

Tool logic lives in `sentinel_mcp.tools` (pure, SDK-independent). This module
registers it against whichever MCP SDK generation is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sentinel_mcp._version import __version__
from sentinel_mcp.schemas import (
    MemoryEdgeInput,
    MemoryQueryInput,
    MemoryUpsertInput,
    PolicyCheckInput,
    VerifyClaimInput,
)
from sentinel_mcp.tools.audit_log import WormAuditLedger
from sentinel_mcp.tools.graph_memory import GraphMemory
from sentinel_mcp.tools.policy_check import PolicyGate
from sentinel_mcp.tools.verify_claim import verify_claim as _verify_claim_logic

INSTRUCTIONS = (
    "Sentinel MCP: deterministic claim verification, declarative policy gate, "
    "Merkle-chained WORM audit ledger, and graph memory with SQLite fallback."
)


class SentinelServices:
    """Shared tool backends (policy gate, ledger, memory) for one server instance."""

    def __init__(
        self,
        ledger_path: str | Path | None = None,
        memory_path: str | Path | None = None,
    ) -> None:
        self.gate = PolicyGate()
        self.ledger = WormAuditLedger(ledger_path)
        self.memory = GraphMemory(memory_path if memory_path is not None else "sentinel_memory.db")


def server_generation() -> str:
    """Report which MCP SDK generation will serve ('1.x-fastmcp' or '2.x-mcpserver')."""
    try:
        import mcp.server.mcpserver  # noqa: F401,PLC0415

        return "2.x-mcpserver"
    except ImportError:
        return "1.x-fastmcp"


def _build_mcp2(services: SentinelServices, name: str) -> Any:
    from mcp.server.mcpserver import MCPServer  # noqa: PLC0415

    server = MCPServer(name=name, instructions=INSTRUCTIONS, version=__version__)

    @server.add_tool
    def verify_claim(claim_text: str, url: str = "") -> dict[str, Any]:
        """Deterministically tier a claim's source (1-5) and flag text risks. Zero network."""
        return _verify_claim_logic(VerifyClaimInput(claim_text=claim_text, url=url)).model_dump()

    @server.add_tool
    def policy_check(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Declarative allow/deny gate for a tool invocation (fail-closed)."""
        return services.gate.check(
            PolicyCheckInput(tool_name=tool_name, args=args or {})
        ).model_dump()

    @server.add_tool
    def audit_append(event: dict[str, Any]) -> dict[str, Any]:
        """Append one event to the tamper-evident WORM audit ledger."""
        return services.ledger.append(event).model_dump()

    @server.add_tool
    def audit_verify() -> dict[str, Any]:
        """Replay the WORM ledger chain and report integrity."""
        return services.ledger.verify_chain().model_dump()

    @server.add_tool
    def memory_upsert(
        node_id: str, labels: list[str] | None = None, properties: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Upsert a node in graph memory (FalkorDB, or SQLite when unavailable)."""
        return services.memory.upsert_node(
            MemoryUpsertInput(node_id=node_id, labels=labels or [], properties=properties or {})
        )

    @server.add_tool
    def memory_add_edge(src: str, relation: str, dst: str) -> dict[str, Any]:
        """Add a directed edge between two graph-memory nodes."""
        return services.memory.add_edge(MemoryEdgeInput(src=src, relation=relation, dst=dst))

    @server.add_tool
    def memory_query(node_id: str, max_depth: int = 2) -> dict[str, Any]:
        """Query the neighborhood of a node up to max_depth hops."""
        return services.memory.query_neighbors(
            MemoryQueryInput(node_id=node_id, max_depth=max_depth)
        ).model_dump()

    return server


def _build_fastmcp(services: SentinelServices, name: str) -> Any:
    from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]  # noqa: PLC0415

    server = FastMCP(name, instructions=INSTRUCTIONS)

    def verify_claim(claim_text: str, url: str = "") -> dict[str, Any]:
        """Deterministically tier a claim's source (1-5) and flag text risks. Zero network."""
        return _verify_claim_logic(VerifyClaimInput(claim_text=claim_text, url=url)).model_dump()

    def policy_check(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Declarative allow/deny gate for a tool invocation (fail-closed)."""
        return services.gate.check(
            PolicyCheckInput(tool_name=tool_name, args=args or {})
        ).model_dump()

    def audit_append(event: dict[str, Any]) -> dict[str, Any]:
        """Append one event to the tamper-evident WORM audit ledger."""
        return services.ledger.append(event).model_dump()

    def audit_verify() -> dict[str, Any]:
        """Replay the WORM ledger chain and report integrity."""
        return services.ledger.verify_chain().model_dump()

    def memory_upsert(
        node_id: str, labels: list[str] | None = None, properties: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Upsert a node in graph memory (FalkorDB, or SQLite when unavailable)."""
        return services.memory.upsert_node(
            MemoryUpsertInput(node_id=node_id, labels=labels or [], properties=properties or {})
        )

    def memory_add_edge(src: str, relation: str, dst: str) -> dict[str, Any]:
        """Add a directed edge between two graph-memory nodes."""
        return services.memory.add_edge(MemoryEdgeInput(src=src, relation=relation, dst=dst))

    def memory_query(node_id: str, max_depth: int = 2) -> dict[str, Any]:
        """Query the neighborhood of a node up to max_depth hops."""
        return services.memory.query_neighbors(
            MemoryQueryInput(node_id=node_id, max_depth=max_depth)
        ).model_dump()

    for fn in (
        verify_claim,
        policy_check,
        audit_append,
        audit_verify,
        memory_upsert,
        memory_add_edge,
        memory_query,
    ):
        server.add_tool(fn)

    return server


def build_server(services: SentinelServices | None = None, name: str = "sentinel-mcp") -> Any:
    """Build the MCP server object for the installed SDK generation."""
    services = services or SentinelServices()
    if server_generation() == "2.x-mcpserver":
        return _build_mcp2(services, name)
    return _build_fastmcp(services, name)


TOOL_NAMES = (
    "verify_claim",
    "policy_check",
    "audit_append",
    "audit_verify",
    "memory_upsert",
    "memory_add_edge",
    "memory_query",
)

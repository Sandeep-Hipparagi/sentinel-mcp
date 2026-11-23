"""sentinel-mcp: registry-ready MCP server for verification, policy, audit, and memory."""

from sentinel_mcp._version import __version__
from sentinel_mcp.schemas import (
    AuditAppendOutput,
    ChainStatus,
    MemoryQueryOutput,
    PolicyDecision,
    VerifyClaimOutput,
)
from sentinel_mcp.server import TOOL_NAMES, SentinelServices, build_server, server_generation
from sentinel_mcp.tools import (
    GENESIS_HASH,
    GraphMemory,
    PolicyGate,
    PolicyRules,
    WormAuditLedger,
    classify_source,
    verify_claim,
)

__all__ = [
    "GENESIS_HASH",
    "TOOL_NAMES",
    "AuditAppendOutput",
    "ChainStatus",
    "GraphMemory",
    "MemoryQueryOutput",
    "PolicyDecision",
    "PolicyGate",
    "PolicyRules",
    "SentinelServices",
    "VerifyClaimOutput",
    "WormAuditLedger",
    "build_server",
    "classify_source",
    "__version__",
    "server_generation",
    "verify_claim",
]

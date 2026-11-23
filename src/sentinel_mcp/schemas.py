"""Strict Pydantic I/O models for sentinel-mcp tools (published as MCP JSON schemas)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerifyClaimInput(BaseModel):
    """Input for deterministic claim/source verification."""

    claim_text: str = Field(description="The claim to assess.", min_length=1, max_length=10_000)
    url: str = Field(default="", description="Optional source URL to tier (1-5).", max_length=2_048)


class VerifyClaimOutput(BaseModel):
    """Deterministic, zero-hallucination verification verdict."""

    citable: bool = Field(description="True when the source tier is 1 or 2.")
    source_tier: int = Field(
        ge=1, le=5, description="Accountability tier 1 (primary) .. 5 (satire)."
    )
    tier_name: str = Field(description="Human-readable tier name.")
    registered_domain: str = Field(description="Extracted registered domain (empty if no URL).")
    risk_flags: list[str] = Field(
        default_factory=list, description="Deterministic text-risk flags."
    )
    rationale: str = Field(description="Rule-based explanation of the verdict.")


class PolicyCheckInput(BaseModel):
    """Input for the declarative policy gate."""

    tool_name: str = Field(description="Tool being invoked.", min_length=1, max_length=128)
    args: dict[str, object] = Field(
        default_factory=dict,
        description="JSON arguments the caller wants to pass to the tool.",
    )


class PolicyDecision(BaseModel):
    """Gate outcome (fail-closed)."""

    allowed: bool
    reason_code: str = Field(
        description="OK, POL_TOOL_BLOCKED, POL_ARG_BOUND, POL_ARG_FORBIDDEN_KEY, POL_INVALID_ARGS."
    )


class AuditAppendOutput(BaseModel):
    """Result of appending one entry to the WORM ledger."""

    sequence: int = Field(ge=1)
    entry_hash: str = Field(description="SHA-256 chain hash of the appended entry.")
    merkle_root: str = Field(description="Merkle root over all entry hashes after append.")


class ChainStatus(BaseModel):
    """Integrity inspection result for the WORM ledger."""

    valid: bool
    length: int = Field(ge=0)
    merkle_root: str
    first_bad_sequence: int | None = Field(
        default=None, description="1-based sequence of first invalid entry."
    )


class MemoryUpsertInput(BaseModel):
    """Node upsert for graph memory."""

    node_id: str = Field(min_length=1, max_length=256)
    labels: list[str] = Field(default_factory=list, max_length=16)
    properties: dict[str, object] = Field(default_factory=dict)


class MemoryEdgeInput(BaseModel):
    """Directed edge for graph memory."""

    src: str = Field(min_length=1, max_length=256)
    relation: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    dst: str = Field(min_length=1, max_length=256)


class MemoryQueryInput(BaseModel):
    """Neighborhood query for graph memory."""

    node_id: str = Field(min_length=1, max_length=256)
    max_depth: int = Field(default=2, ge=1, le=6)


class MemoryQueryOutput(BaseModel):
    """Subgraph response for graph memory queries."""

    backend: str = Field(description="'falkordb' or 'sqlite'.")
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]

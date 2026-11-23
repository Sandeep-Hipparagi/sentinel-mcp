"""Declarative allow/deny policy gate for tool invocations (fail-closed)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from sentinel_mcp.schemas import PolicyCheckInput, PolicyDecision

_FORBIDDEN_KEYS = frozenset({"__proto__", "constructor", "prototype", "__class__"})


class ArgBound(BaseModel):
    """A single argument bound enforced by the gate."""

    kind: str = Field(description="'string' | 'number' | 'boolean' | 'object'")
    required: bool = False
    max_length: int | None = Field(default=None, description="For strings: max length.")
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[str] | None = None


class PolicyRules(BaseModel):
    """Declarative policy: tool allowlist plus per-tool argument bounds."""

    allowed_tools: list[str] = Field(
        default_factory=list, description="Empty allowlist denies everything."
    )
    arg_bounds: dict[str, dict[str, ArgBound]] = Field(default_factory=dict)
    max_payload_json_bytes: int = Field(default=65_536, ge=1)


DEFAULT_RULES = PolicyRules(
    allowed_tools=[
        "verify_claim",
        "audit_append",
        "audit_verify",
        "memory_upsert",
        "memory_add_edge",
        "memory_query",
    ],
    arg_bounds={
        "verify_claim": {
            "claim_text": ArgBound(kind="string", required=True, max_length=10_000),
            "url": ArgBound(kind="string", max_length=2_048),
        },
        "memory_upsert": {
            "node_id": ArgBound(kind="string", required=True, max_length=256),
        },
        "memory_query": {
            "node_id": ArgBound(kind="string", required=True, max_length=256),
            "max_depth": ArgBound(kind="number", minimum=1, maximum=6),
        },
    },
    max_payload_json_bytes=65_536,
)


def _has_forbidden_key(obj: Any) -> bool:
    if isinstance(obj, dict):
        return bool(_FORBIDDEN_KEYS & obj.keys()) or any(
            _has_forbidden_key(v) for v in obj.values()
        )
    if isinstance(obj, list):
        return any(_has_forbidden_key(v) for v in obj)
    return False


class PolicyGate:
    """Schema-level allow/deny gate. Denies on any doubt (fail-closed)."""

    def __init__(self, rules: PolicyRules | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    def check(self, payload: PolicyCheckInput) -> PolicyDecision:
        if payload.tool_name not in self.rules.allowed_tools:
            return PolicyDecision(allowed=False, reason_code="POL_TOOL_BLOCKED")
        bounds = self.rules.arg_bounds.get(payload.tool_name, {})
        try:
            payload_bytes = len(
                json.dumps(payload.args, allow_nan=False, default=str).encode("utf-8")
            )
        except (TypeError, ValueError):
            return PolicyDecision(allowed=False, reason_code="POL_INVALID_ARGS")
        if payload_bytes > self.rules.max_payload_json_bytes:
            return PolicyDecision(allowed=False, reason_code="POL_ARG_BOUND")
        if _has_forbidden_key(payload.args):
            return PolicyDecision(allowed=False, reason_code="POL_ARG_FORBIDDEN_KEY")
        for name, bound in bounds.items():
            if name not in payload.args:
                if bound.required:
                    return PolicyDecision(allowed=False, reason_code="POL_INVALID_ARGS")
                continue
            value = payload.args[name]
            if bound.kind == "string":
                if not isinstance(value, str):
                    return PolicyDecision(allowed=False, reason_code="POL_INVALID_ARGS")
                if bound.max_length is not None and len(value) > bound.max_length:
                    return PolicyDecision(allowed=False, reason_code="POL_ARG_BOUND")
            elif bound.kind == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return PolicyDecision(allowed=False, reason_code="POL_INVALID_ARGS")
                if bound.minimum is not None and value < bound.minimum:
                    return PolicyDecision(allowed=False, reason_code="POL_ARG_BOUND")
                if bound.maximum is not None and value > bound.maximum:
                    return PolicyDecision(allowed=False, reason_code="POL_ARG_BOUND")
        return PolicyDecision(allowed=True, reason_code="OK")

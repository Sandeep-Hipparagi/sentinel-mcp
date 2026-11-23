"""Policy gate tests: allowlist, bounds, prototype pollution, fail-closed."""

from sentinel_mcp.schemas import PolicyCheckInput
from sentinel_mcp.tools.policy_check import DEFAULT_RULES, PolicyGate, PolicyRules


class TestAllowlist:
    def test_allowlisted_tool_passes(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "hi"})
        )
        assert d.allowed and d.reason_code == "OK"

    def test_unknown_tool_blocked(self):
        d = PolicyGate().check(PolicyCheckInput(tool_name="rm_rf", args={}))
        assert not d.allowed and d.reason_code == "POL_TOOL_BLOCKED"

    def test_empty_allowlist_denies_everything(self):
        gate = PolicyGate(PolicyRules(allowed_tools=[]))
        d = gate.check(PolicyCheckInput(tool_name="verify_claim", args={}))
        assert not d.allowed


class TestArgumentBounds:
    def test_missing_required_arg(self):
        d = PolicyGate().check(PolicyCheckInput(tool_name="verify_claim", args={}))
        assert not d.allowed and d.reason_code == "POL_INVALID_ARGS"

    def test_string_over_max_length(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "a" * 10_001})
        )
        assert not d.allowed and d.reason_code == "POL_ARG_BOUND"

    def test_number_out_of_range(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="memory_query", args={"node_id": "n", "max_depth": 99})
        )
        assert not d.allowed and d.reason_code == "POL_ARG_BOUND"

    def test_bool_is_not_number(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="memory_query", args={"node_id": "n", "max_depth": True})
        )
        assert not d.allowed and d.reason_code == "POL_INVALID_ARGS"

    def test_wrong_type(self):
        d = PolicyGate().check(PolicyCheckInput(tool_name="verify_claim", args={"claim_text": 42}))
        assert not d.allowed and d.reason_code == "POL_INVALID_ARGS"

    def test_optional_arg_absent_ok(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "fine"})
        )
        assert d.allowed


class TestPrototypePollution:
    def test_top_level_forbidden_key(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "x", "__proto__": {}})
        )
        assert not d.allowed and d.reason_code == "POL_ARG_FORBIDDEN_KEY"

    def test_nested_forbidden_key(self):
        d = PolicyGate().check(
            PolicyCheckInput(
                tool_name="verify_claim", args={"claim_text": "x", "opts": {"constructor": 1}}
            )
        )
        assert not d.allowed and d.reason_code == "POL_ARG_FORBIDDEN_KEY"


class TestPayloadSize:
    def test_oversized_payload_denied(self):
        gate = PolicyGate(PolicyRules(allowed_tools=["verify_claim"], max_payload_json_bytes=64))
        d = gate.check(PolicyCheckInput(tool_name="verify_claim", args={"claim_text": "x" * 1000}))
        assert not d.allowed and d.reason_code == "POL_ARG_BOUND"

    def test_unserializable_args_denied(self):
        d = PolicyGate().check(
            PolicyCheckInput(tool_name="verify_claim", args={"claim_text": object()})
        )
        assert not d.allowed and d.reason_code in {"POL_INVALID_ARGS", "POL_ARG_BOUND"}


class TestDefaults:
    def test_default_rules_cover_all_tools(self):
        for tool in (
            "verify_claim",
            "audit_append",
            "audit_verify",
            "memory_upsert",
            "memory_add_edge",
            "memory_query",
        ):
            assert tool in DEFAULT_RULES.allowed_tools

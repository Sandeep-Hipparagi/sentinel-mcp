"""Deterministic verification tests: tiering, risk flags, typosquat defense."""

import pytest

from sentinel_mcp.schemas import VerifyClaimInput
from sentinel_mcp.tools.verify_claim import (
    claim_risk_flags,
    classify_source,
    registered_domain,
    verify_claim,
)


class TestRegisteredDomain:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.reuters.com/p/1", "reuters.com"),
            ("http://NEWS.BBC.com:8080/x", "news.bbc.com"),
            ("ftp://apnews.com", "apnews.com"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_extraction(self, url: str, expected: str):
        assert registered_domain(url) == expected


class TestClassifySource:
    @pytest.mark.parametrize(
        ("url", "tier"),
        [
            ("https://www.reuters.com/p/1", 1),
            ("https://federalreserve.gov/press", 1),
            ("https://sub.nature.com/article", 1),
            ("https://www.nytimes.com", 2),
            ("https://university.edu/news", 2),
            ("https://techcrunch.com/x", 3),
            ("https://random-blog.example", 3),
            ("https://reddit.com/r/news", 4),
            ("https://www.theonion.com/a/b", 5),
            ("https://agency.gov", 1),
            ("https://lab.mit.edu", 2),
        ],
    )
    def test_tiers(self, url: str, tier: int):
        assert classify_source(url).tier == tier

    def test_empty_url_is_cautious_default(self):
        assert classify_source("").tier == 3


class TestClaimRiskFlags:
    def test_shouting(self):
        assert "EXCESSIVE_CAPITALISATION" in claim_risk_flags(
            "THIS IS AN OUTRAGE AND EVERYONE MUST KNOW"
        )

    def test_clickbait(self):
        assert "CLICKBAIT_MARKER" in claim_risk_flags("You won't believe what happens next")

    def test_absolute_claim(self):
        assert "ABSOLUTE_CLAIM" in claim_risk_flags(
            "It is always the banks, 100% proven by everyone"
        )

    def test_unattributed(self):
        assert "UNATTRIBUTED_SOURCE" in claim_risk_flags("Sources say the deal collapsed")

    def test_no_date(self):
        assert "NO_DATE_REFERENCE" in claim_risk_flags(
            "The central bank raised rates sharply today"
        )

    def test_clean_claim_no_flags(self):
        assert claim_risk_flags("On 2026-03-01 the bank raised rates by 25 basis points.") == []


class TestVerifyClaim:
    def test_primary_source_citable(self):
        out = verify_claim(
            VerifyClaimInput(
                claim_text="Officials confirmed the merger on 2026-01-15.",
                url="https://reuters.com/p/1",
            )
        )
        assert out.citable
        assert out.source_tier == 1
        assert out.registered_domain == "reuters.com"

    def test_satire_blocked(self):
        out = verify_claim(
            VerifyClaimInput(
                claim_text="Sources say the shocking merger is done.",
                url="https://www.theonion.com/a",
            )
        )
        assert not out.citable
        assert out.source_tier == 5
        assert "UNATTRIBUTED_SOURCE" in out.risk_flags

    def test_typosquat_upgraded_to_satire_tier(self):
        out = verify_claim(
            VerifyClaimInput(claim_text="The merger is done.", url="https://reuters-breaking.com/x")
        )
        assert not out.citable
        assert out.source_tier == 5
        assert "TYPOSQUAT_LOOKALIKE" in out.risk_flags

    def test_no_url_defaults_tier3_not_citable(self):
        out = verify_claim(VerifyClaimInput(claim_text="The merger is done."))
        assert not out.citable
        assert out.source_tier == 3

    def test_deterministic(self):
        a = verify_claim(
            VerifyClaimInput(claim_text="X happened in 2026.", url="https://apnews.com/1")
        )
        b = verify_claim(
            VerifyClaimInput(claim_text="X happened in 2026.", url="https://apnews.com/1")
        )
        assert a == b

    def test_output_schema_shape(self):
        out = verify_claim(VerifyClaimInput(claim_text="x", url="https://reuters.com"))
        assert set(out.model_dump()) == {
            "citable",
            "source_tier",
            "tier_name",
            "registered_domain",
            "risk_flags",
            "rationale",
        }

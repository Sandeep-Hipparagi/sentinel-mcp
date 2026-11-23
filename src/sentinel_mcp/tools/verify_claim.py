"""Deterministic claim/source verification (rule-backed, zero network, zero API keys)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sentinel_mcp.schemas import VerifyClaimInput, VerifyClaimOutput

_TIER_RULES: list[tuple[int, str, tuple[str, ...]]] = [
    (
        5,
        "Satire / parody outlet",
        (
            "theonion.com",
            "babylonbee.com",
            "waterfordwhispersnews.com",
            "duffelblog.com",
            "newsthump.com",
            "clickhole.com",
        ),
    ),
    (
        4,
        "User-generated content / social platform",
        (
            "reddit.com",
            "quora.com",
            "x.com",
            "twitter.com",
            "facebook.com",
            "youtube.com",
            "stackoverflow.com",
            "news.ycombinator.com",
        ),
    ),
    (
        1,
        "Primary / official / global wire service",
        (
            "reuters.com",
            "apnews.com",
            "afp.com",
            "bloomberg.com",
            "federalreserve.gov",
            "sec.gov",
            "who.int",
            "un.org",
            "nature.com",
            "science.org",
            "nejm.org",
            "factcheck.org",
        ),
    ),
    (
        2,
        "Established editorial newsroom",
        (
            "nytimes.com",
            "theguardian.com",
            "wsj.com",
            "ft.com",
            "bbc.com",
            "economist.com",
            "washingtonpost.com",
            "thehindu.com",
        ),
    ),
    (
        3,
        "Secondary publication / blog / newsletter",
        (
            "techcrunch.com",
            "arstechnica.com",
            "substack.com",
            "medium.com",
            "yourstory.com",
            "inc42.com",
        ),
    ),
]

_TIER1_TLDS = ("gov", "mil", "int")
_EDU_TLD = "edu"
_HOMOGLYPH_DOMAINS = ("reuters-breaking", "bbc-news-live", "cnn-trending")

_SHOUTY = re.compile(r"[A-Z]")
_WORD = re.compile(r"[A-Za-z]{2,}")
_CLICKBAIT = ("you won't believe", "shocking", "what happens next", "doctors hate", "gone wrong")
_ABSOLUTES = ("always", "never", "everyone knows", "100% proven", "they don't want you to know")
_UNATTRIBUTED = ("sources say", "insiders claim", "a report claims", "people are saying")


@dataclass(frozen=True)
class SourceTier:
    """Tier classification for a source URL."""

    tier: int
    tier_name: str
    registered_domain: str


def registered_domain(url: str) -> str:
    """Extract lowercase host (any scheme/port/path/www stripped)."""
    host = url.strip().lower()
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", host)
    host = host.split("/", 1)[0].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_source(url: str) -> SourceTier:
    """Deterministically tier a URL 1 (primary) .. 5 (satire); unknown -> 3."""
    host = registered_domain(url)
    if not host:
        return SourceTier(tier=3, tier_name="Unknown / unattributed source", registered_domain="")
    for tier, name, domains in _TIER_RULES:
        if any(host == d or host.endswith("." + d) for d in domains):
            return SourceTier(tier=tier, tier_name=name, registered_domain=host)
    parts = host.rsplit(".", 1)
    tld = parts[1] if len(parts) == 2 else ""
    if tld in _TIER1_TLDS:
        return SourceTier(
            tier=1, tier_name="Primary / official / global wire service", registered_domain=host
        )
    if tld == _EDU_TLD:
        return SourceTier(
            tier=2, tier_name="Established editorial newsroom", registered_domain=host
        )
    return SourceTier(
        tier=3, tier_name="Secondary publication / blog / newsletter", registered_domain=host
    )


def claim_risk_flags(claim_text: str) -> list[str]:
    """Deterministic text-risk flags (no model calls)."""
    flags: list[str] = []
    words = _WORD.findall(claim_text)
    if words:
        letters = _SHOUTY.findall(claim_text)
        if len(letters) > 0.5 * len("".join(words)):
            flags.append("EXCESSIVE_CAPITALISATION")
    low = claim_text.lower()
    if any(m in low for m in _CLICKBAIT):
        flags.append("CLICKBAIT_MARKER")
    if any(m in low for m in _ABSOLUTES):
        flags.append("ABSOLUTE_CLAIM")
    if any(m in low for m in _UNATTRIBUTED):
        flags.append("UNATTRIBUTED_SOURCE")
    if not re.search(r"\b(19|20)\d{2}\b", claim_text) and len(words) > 6:
        flags.append("NO_DATE_REFERENCE")
    return flags


def verify_claim(payload: VerifyClaimInput) -> VerifyClaimOutput:
    """Deterministically verify a claim against its source (zero hallucination)."""
    source = classify_source(payload.url)
    flags = claim_risk_flags(payload.claim_text)

    host = source.registered_domain
    if any(h in host for h in _HOMOGLYPH_DOMAINS):
        flags.append("TYPOSQUAT_LOOKALIKE")
        source = SourceTier(tier=5, tier_name="Satire / parody outlet", registered_domain=host)

    citable = source.tier <= 2 and "TYPOSQUAT_LOOKALIKE" not in flags
    if citable:
        rationale = (
            f"Source '{host or 'unattributed'}' is Tier {source.tier} ({source.tier_name}); "
            f"{len(flags)} text-risk flag(s)."
        )
    else:
        rationale = (
            f"Source tier {source.tier} ({source.tier_name}) is below the citable threshold "
            f"(requires Tier 1-2){'; flags: ' + ', '.join(flags) if flags else ''}."
        )
    return VerifyClaimOutput(
        citable=citable,
        source_tier=source.tier,
        tier_name=source.tier_name,
        registered_domain=host,
        risk_flags=flags,
        rationale=rationale,
    )

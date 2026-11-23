"""Tamper-evident append-only WORM audit ledger with SHA-256 Merkle chaining.

Entries are appended to an JSONL file (or in-memory stream). Each entry hash
is `SHA-256(prev_hash || canonical_json(entry_without_hash))`, forming a
tamper-evident chain; `verify_chain()` replays it and pinpoints the first
mutated sequence. Appends use O_APPEND semantics so existing bytes are never
rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sentinel_mcp.schemas import AuditAppendOutput, ChainStatus
from sentinel_mcp.tools.policy_check import _has_forbidden_key  # noqa: F401 (re-exported helper)

GENESIS_HASH = "0" * 64


def canonical_bytes(entry: dict[str, Any]) -> bytes:
    """Byte-stable serialization for hashing (sorted keys, tight separators)."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def merkle_root(hashes: list[str]) -> str:
    """SHA-256 Merkle root over entry hashes (duplicates last when odd)."""
    if not hashes:
        return GENESIS_HASH
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[i] + level[i + 1]).encode("utf-8")).hexdigest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


class WormAuditLedger:
    """Append-only, Merkle-chained audit ledger backed by a JSONL file."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text("", encoding="utf-8")
        self._mem_entries: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self._mem_entries = self._load_file()

    def _load_file(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():  # type: ignore[union-attr]
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def append(self, event: dict[str, Any]) -> AuditAppendOutput:
        """Append one event; returns its sequence, chain hash, and Merkle root."""
        if _has_forbidden_key(event):
            raise ValueError("event contains forbidden keys")
        prev_hash = self._mem_entries[-1]["entry_hash"] if self._mem_entries else GENESIS_HASH
        sequence = len(self._mem_entries) + 1
        body = {"sequence": sequence, "prev_hash": prev_hash, "event": event}
        entry_hash = hashlib.sha256(prev_hash.encode("utf-8") + canonical_bytes(body)).hexdigest()
        entry = {**body, "entry_hash": entry_hash}
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        self._mem_entries.append(entry)
        return AuditAppendOutput(
            sequence=sequence,
            entry_hash=entry_hash,
            merkle_root=self.root(),
        )

    def root(self) -> str:
        """Current Merkle root over all entry hashes."""
        return merkle_root([e["entry_hash"] for e in self._mem_entries])

    def verify_chain(self) -> ChainStatus:
        """Replay the full chain; report validity, length, and first bad entry."""
        prev = GENESIS_HASH
        for entry in self._mem_entries:
            body = {k: entry[k] for k in ("sequence", "prev_hash", "event")}
            expected = hashlib.sha256(prev.encode("utf-8") + canonical_bytes(body)).hexdigest()
            if entry.get("prev_hash") != prev or entry.get("entry_hash") != expected:
                return ChainStatus(
                    valid=False,
                    length=len(self._mem_entries),
                    merkle_root=self.root(),
                    first_bad_sequence=int(entry.get("sequence", len(self._mem_entries) + 1)),
                )
            prev = entry["entry_hash"]
        return ChainStatus(valid=True, length=len(self._mem_entries), merkle_root=self.root())

    def entries(self) -> list[dict[str, Any]]:
        """Copy of all ledger entries (read-only usage)."""
        return [dict(e) for e in self._mem_entries]

    def reload(self) -> None:
        """Re-read the file-backed ledger (used by tamper tests)."""
        if self.path is not None:
            self._mem_entries = self._load_file()

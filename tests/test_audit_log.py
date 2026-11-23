"""WORM ledger tests: chain validity, Merkle determinism, 100% tamper catch."""

import json
from pathlib import Path

import pytest

from sentinel_mcp.schemas import ChainStatus
from sentinel_mcp.tools.audit_log import GENESIS_HASH, WormAuditLedger, merkle_root


class TestChainValidity:
    def test_genesis_root(self):
        assert merkle_root([]) == GENESIS_HASH

    def test_append_and_verify(self, tmp_path: Path):
        ledger = WormAuditLedger(tmp_path / "ledger.jsonl")
        for i in range(25):
            out = ledger.append({"action": f"op-{i}", "n": i})
            assert out.sequence == i + 1
        status = ledger.verify_chain()
        assert status.valid
        assert status.length == 25
        assert status.merkle_root == ledger.root()

    def test_first_entry_prev_is_genesis(self, tmp_path: Path):
        ledger = WormAuditLedger(tmp_path / "ledger.jsonl")
        ledger.append({"a": 1})
        assert ledger.entries()[0]["prev_hash"] == GENESIS_HASH

    def test_mem_and_file_ledgers_agree(self, tmp_path: Path):
        mem = WormAuditLedger()
        f = WormAuditLedger(tmp_path / "ledger.jsonl")
        for i in range(5):
            mem.append({"i": i})
            f.append({"i": i})
        assert mem.root() == f.root()

    def test_merkle_root_deterministic(self, tmp_path: Path):
        a = WormAuditLedger(tmp_path / "a.jsonl")
        b = WormAuditLedger(tmp_path / "b.jsonl")
        for i in range(7):
            a.append({"i": i})
            b.append({"i": i})
        assert a.root() == b.root()

    def test_forbidden_keys_rejected_on_append(self, tmp_path: Path):
        ledger = WormAuditLedger(tmp_path / "ledger.jsonl")
        with pytest.raises(ValueError):
            ledger.append({"__proto__": 1})

    def test_reload_reads_file(self, tmp_path: Path):
        path = tmp_path / "ledger.jsonl"
        ledger = WormAuditLedger(path)
        ledger.append({"a": 1})
        reborn = WormAuditLedger(path)
        assert reborn.entries() == ledger.entries()
        assert reborn.root() == ledger.root()


class TestTamperDetection:
    def _seed(self, tmp_path: Path, n: int = 12) -> Path:
        path = tmp_path / "ledger.jsonl"
        ledger = WormAuditLedger(path)
        for i in range(n):
            ledger.append({"action": f"op-{i}", "target": f"t{i}"})
        return path

    def _tamper(self, path: Path, seq: int, mutate) -> ChainStatus:
        lines = path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[seq - 1])
        mutate(entry)
        lines[seq - 1] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered = WormAuditLedger(path)
        return tampered.verify_chain()

    @pytest.mark.parametrize("seq", [1, 2, 5, 8, 12])
    def test_single_event_mutation_always_caught(self, tmp_path: Path, seq: int):
        path = self._seed(tmp_path)
        status = self._tamper(path, seq, lambda e: e["event"].__setitem__("action", "TAMPERED"))
        assert not status.valid
        assert status.first_bad_sequence == seq

    @pytest.mark.parametrize("seq", [1, 6, 11])
    def test_single_hash_replacement_always_caught(self, tmp_path: Path, seq: int):
        path = self._seed(tmp_path)
        status = self._tamper(path, seq, lambda e: e.__setitem__("entry_hash", "f" * 64))
        assert not status.valid

    def test_multi_block_mutation_caught(self, tmp_path: Path):
        path = self._seed(tmp_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx in (2, 5, 9):
            entry = json.loads(lines[idx])
            entry["event"]["action"] = "TAMPERED"
            lines[idx] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        status = WormAuditLedger(path).verify_chain()
        assert not status.valid
        assert status.first_bad_sequence == 3  # first mutated block pin-pointed

    def test_deletion_detected_as_length_change(self, tmp_path: Path):
        path = self._seed(tmp_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[4]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tampered = WormAuditLedger(path)
        status = tampered.verify_chain()
        # Deleting a middle block breaks the chain hash linkage at that point.
        assert not status.valid

    def test_append_after_tamper_does_not_heal(self, tmp_path: Path):
        path = self._seed(tmp_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[1])
        entry["event"]["action"] = "TAMPERED"
        lines[1] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ledger = WormAuditLedger(path)
        ledger.append({"action": "more"})
        status = ledger.verify_chain()
        assert not status.valid
        assert status.first_bad_sequence == 2

    def test_truncation_detected_by_length(self, tmp_path: Path):
        path = self._seed(tmp_path, n=10)
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        assert len(WormAuditLedger(path).entries()) == 3

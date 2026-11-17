"""RFC-6962 Cryptographic Merkle Audit Tree & Inclusion Proof Engine.

Implements a binary cryptographic Merkle Tree with RFC-6962 domain separation:
- Leaf Hash:     SHA-256(0x00 || canonical_json(record))
- Internal Node: SHA-256(0x01 || left_hash || right_hash)

Provides O(log N) zero-knowledge inclusion proofs allowing external auditors,
compliance officers (SOC 2, ISO 27001), or CI pipelines to mathematically verify
that a specific review, approval, or waiver event is permanently committed to
the cryptographic Merkle root without disclosing or reading other records.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


def _canonical_json(data: Any) -> bytes:
    """Format data as deterministic canonical JSON bytes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def hash_leaf(data: Any) -> str:
    """Compute RFC-6962 leaf hash: SHA-256(0x00 || canonical_json(data))."""
    payload = b"\x00" + _canonical_json(data)
    return hashlib.sha256(payload).hexdigest()


def hash_children(left_hex: str, right_hex: str) -> str:
    """Compute RFC-6962 interior node hash: SHA-256(0x01 || left_bytes || right_bytes)."""
    payload = b"\x01" + bytes.fromhex(left_hex) + bytes.fromhex(right_hex)
    return hashlib.sha256(payload).hexdigest()


class MerkleTree:
    """Binary Merkle Tree constructed from audit log records."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self.levels: List[List[str]] = []
        self._build_tree()

    def _build_tree(self) -> None:
        if not self.records:
            empty_root = hashlib.sha256(b"\x00").hexdigest()
            self.levels = [[empty_root]]
            return

        # Level 0: Leaf hashes
        current_level = [hash_leaf(r) for r in self.records]
        self.levels.append(current_level)

        # Build tree upwards
        while len(current_level) > 1:
            next_level: List[str] = []
            i = 0
            while i < len(current_level):
                left = current_level[i]
                if i + 1 < len(current_level):
                    right = current_level[i + 1]
                    next_level.append(hash_children(left, right))
                else:
                    # Odd node promotes directly to next level
                    next_level.append(left)
                i += 2
            self.levels.append(next_level)
            current_level = next_level

    @property
    def root(self) -> str:
        """The top cryptographic Merkle Root hash."""
        if not self.levels or not self.levels[-1]:
            return hashlib.sha256(b"\x00").hexdigest()
        return self.levels[-1][0]

    def audit_proof(self, index: int) -> Dict[str, Any]:
        """Generate an RFC-6962 logarithmic audit inclusion proof for record at index."""
        if index < 0 or index >= len(self.records):
            raise IndexError(f"Audit record index {index} out of range [0, {len(self.records) - 1}]")

        proof_path: List[Dict[str, str]] = []
        curr_idx = index

        for level_idx in range(len(self.levels) - 1):
            level = self.levels[level_idx]
            is_right_child = (curr_idx % 2 == 1)
            sibling_idx = curr_idx - 1 if is_right_child else curr_idx + 1

            if sibling_idx < len(level):
                sibling_hash = level[sibling_idx]
                proof_path.append({
                    "hash": sibling_hash,
                    "position": "left" if is_right_child else "right"
                })

            curr_idx = curr_idx // 2

        target_record = self.records[index]
        return {
            "index": index,
            "leaf_hash": self.levels[0][index],
            "record_seq": target_record.get("seq", index + 1),
            "record_event": target_record.get("event", "unknown"),
            "tree_size": len(self.records),
            "merkle_root": self.root,
            "proof_path": proof_path
        }


def verify_inclusion_proof(record: Dict[str, Any], proof: Dict[str, Any]) -> bool:
    """Mathematically verify an inclusion proof against expected Merkle root in O(log N) operations."""
    expected_root = proof.get("merkle_root")
    proof_path = proof.get("proof_path", [])
    if not expected_root:
        return False

    current_hash = hash_leaf(record)
    if current_hash != proof.get("leaf_hash"):
        return False

    for step in proof_path:
        sibling = step["hash"]
        position = step["position"]
        if position == "left":
            current_hash = hash_children(sibling, current_hash)
        else:
            current_hash = hash_children(current_hash, sibling)

    return current_hash == expected_root


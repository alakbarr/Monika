# ==============================================================================
# File: analysis/memory/skill_ledger_sha.py
# ==============================================================================

"""
Cryptographic SHA-256 Chained Audit Ledger for Skills & Playbooks.
Institutional-grade engine turn protection architecture.

Guarantees tamper-evident provenance and reproducibility for all dynamic skills,
trading strategy playbooks, and tactical rules evolved by the AI system.
Every mutation links back to its predecessor via SHA-256 merkle hash chaining.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Memory.SkillLedgerSha")

GENESIS_PREV_HASH = "0" * 64


@dataclass
class ShaLedgerBlock:
    index: int
    timestamp: float
    skill_id: str
    mutation_type: str  # 'CREATE', 'UPDATE', 'DEPRECATE', 'ROLLBACK'
    author_role: str    # 'macro_specialist', 'quant_arbiter', 'learning_loop'
    content_sha256: str
    content_text: str
    metadata: Dict[str, Any]
    prev_hash: str
    block_hash: str

    def calculate_expected_hash(self) -> str:
        """Compute SHA-256 of the block content invariant."""
        payload = (
            f"{self.index}:{self.timestamp}:{self.skill_id}:{self.mutation_type}:"
            f"{self.author_role}:{self.content_sha256}:{self.prev_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ShaSkillLedger:
    """
    Append-only tamper-evident chained ledger for skills and playbooks.
    """

    def __init__(self, ledger_file: Optional[Path] = None):
        self.ledger_file = ledger_file or Path("trading-agent/data/skill_ledger_sha.jsonl")
        self._chain: List[ShaLedgerBlock] = []
        self._load_ledger()

    def _load_ledger(self) -> None:
        """Load and parse ledger chain from storage."""
        self._chain.clear()
        if not self.ledger_file.exists():
            return

        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    block = ShaLedgerBlock(**data)
                    self._chain.append(block)
        except Exception as e:
            logger.error(f"[ShaSkillLedger] Failed to load ledger: {e}")

    def append_mutation(
        self,
        skill_id: str,
        content_text: str,
        mutation_type: str = "UPDATE",
        author_role: str = "learning_loop",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ShaLedgerBlock:
        """
        Record a new mutation into the chained ledger.
        """
        content_sha256 = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        prev_hash = self._chain[-1].block_hash if self._chain else GENESIS_PREV_HASH
        index = len(self._chain)
        timestamp = time.time()

        temp_block = ShaLedgerBlock(
            index=index,
            timestamp=timestamp,
            skill_id=skill_id,
            mutation_type=mutation_type,
            author_role=author_role,
            content_sha256=content_sha256,
            content_text=content_text,
            metadata=metadata or {},
            prev_hash=prev_hash,
            block_hash="",
        )
        block_hash = temp_block.calculate_expected_hash()
        temp_block.block_hash = block_hash

        # Append to in-memory chain
        self._chain.append(temp_block)

        # Write to disk
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(temp_block)) + "\n")

        logger.info(
            f"[ShaSkillLedger] Block #{index} committed for '{skill_id}' "
            f"type={mutation_type} hash={block_hash[:12]}"
        )
        return temp_block

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """
        Verify cryptographic integrity of the entire chain from genesis to head.
        Returns: (is_valid, failure_reason)
        """
        if not self._chain:
            return True, None

        expected_prev_hash = GENESIS_PREV_HASH
        for i, block in enumerate(self._chain):
            if block.index != i:
                return False, f"Sequence error at index {i}: block.index={block.index}"

            if block.prev_hash != expected_prev_hash:
                return False, f"Broken chain at index {i}: expected prev_hash={expected_prev_hash[:12]}, got={block.prev_hash[:12]}"

            # Verify content hash matches text
            actual_content_hash = hashlib.sha256(block.content_text.encode("utf-8")).hexdigest()
            if actual_content_hash != block.content_sha256:
                return False, f"Content tampering detected at index {i} for '{block.skill_id}': content mismatch"

            # Verify block hash
            calc_hash = block.calculate_expected_hash()
            if calc_hash != block.block_hash:
                return False, f"Tampered block hash at index {i}: expected {calc_hash[:12]}, got {block.block_hash[:12]}"

            expected_prev_hash = block.block_hash

        return True, None

    def get_latest_version(self, skill_id: str) -> Optional[ShaLedgerBlock]:
        """Retrieve most recent block for a skill."""
        for block in reversed(self._chain):
            if block.skill_id == skill_id:
                return block
        return None

    def get_version_by_hash(self, block_hash: str) -> Optional[ShaLedgerBlock]:
        """Retrieve historical block by its full or 12-char prefix hash."""
        for block in self._chain:
            if block.block_hash == block_hash or block.block_hash.startswith(block_hash):
                return block
        return None

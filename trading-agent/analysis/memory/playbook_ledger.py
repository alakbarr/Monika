"""
File: analysis/memory/playbook_ledger.py
Audit ledger and content-addressed blob backup system for trading playbooks and skills.
Enables full auditability and 1-click rollback of synthesized or mutated trading rules.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("TradingAgent.Memory.PlaybookLedger")


@dataclass
class LedgerEntry:
    timestamp: str
    action: str  # "create", "update", "deprecate", "rollback", "delete"
    playbook_name: str
    sha256_hash: str
    reason: str
    author: str = "ai_agent"
    version_id: Optional[str] = None


class PlaybookLedger:
    """
    Manages append-only JSONL ledger (.curator_ledger.jsonl) and
    content-addressed blob storage (.backups/blobs/<sha256>) for playbooks.
    """

    def __init__(self, playbooks_dir: Optional[str] = None):
        if playbooks_dir:
            self.playbooks_dir = playbooks_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.playbooks_dir = os.path.join(base_dir, "skills", "trading", "playbooks")

        self.ledger_file = os.path.join(self.playbooks_dir, ".curator_ledger.jsonl")
        self.blobs_dir = os.path.join(self.playbooks_dir, ".backups", "blobs")
        os.makedirs(self.blobs_dir, exist_ok=True)

    def record_mutation(
        self,
        playbook_name: str,
        content: str,
        action: str = "update",
        reason: str = "Synthesized rule modification",
        author: str = "ai_agent",
    ) -> str:
        """
        Saves content to blob storage and writes an audit record to the ledger.
        Returns the SHA-256 hash.
        """
        raw_bytes = content.encode("utf-8")
        blob_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 1. Save blob
        blob_path = os.path.join(self.blobs_dir, blob_hash)
        if not os.path.exists(blob_path):
            with open(blob_path, "wb") as bf:
                bf.write(raw_bytes)

        # 2. Append ledger entry
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "timestamp": now_iso,
            "action": action,
            "playbook_name": playbook_name,
            "sha256_hash": blob_hash,
            "reason": reason,
            "author": author,
        }
        with open(self.ledger_file, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(entry) + "\n")

        logger.info(f"[PlaybookLedger] Recorded {action} on '{playbook_name}' [hash={blob_hash[:12]}]")
        return blob_hash

    def list_history(self, playbook_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List mutation history from the ledger, optionally filtered by playbook."""
        if not os.path.exists(self.ledger_file):
            return []

        entries = []
        with open(self.ledger_file, "r", encoding="utf-8") as lf:
            for line in lf:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if playbook_name is None or data.get("playbook_name") == playbook_name:
                        entries.append(data)
                except Exception:
                    continue
        return entries

    def rollback(self, playbook_name: str, target_hash: Optional[str] = None) -> bool:
        """
        Rolls back a playbook to a previous version from blob storage.
        If target_hash is None, rolls back to the immediate prior version.
        """
        history = self.list_history(playbook_name)
        if len(history) < 2 and target_hash is None:
            logger.warning(f"[PlaybookLedger] Cannot rollback '{playbook_name}': insufficient history.")
            return False

        chosen_hash = target_hash
        if not chosen_hash:
            # Pick the second-to-last entry's hash
            chosen_hash = history[-2]["sha256_hash"]

        blob_path = os.path.join(self.blobs_dir, chosen_hash)
        if not os.path.exists(blob_path):
            logger.error(f"[PlaybookLedger] Blob {chosen_hash} not found in backup storage.")
            return False

        with open(blob_path, "rb") as bf:
            restored_content = bf.read().decode("utf-8")

        # Write to playbook file
        playbook_path = os.path.join(self.playbooks_dir, f"{playbook_name}.md")
        with open(playbook_path, "w", encoding="utf-8") as pf:
            pf.write(restored_content)

        # Record rollback action in ledger
        self.record_mutation(
            playbook_name=playbook_name,
            content=restored_content,
            action="rollback",
            reason=f"Rolled back to version {chosen_hash[:12]}",
            author="operator",
        )
        logger.info(f"[PlaybookLedger] Successfully rolled back '{playbook_name}' to {chosen_hash[:12]}")
        return True

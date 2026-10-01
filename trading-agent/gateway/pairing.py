# ==============================================================================
# File: gateway/pairing.py
# ==============================================================================

"""
Production Paired DM Authorization and Direct Message Security Gateway.
Enforces an 8-character salted SHA-256 One-Time Password (OTP) challenge
before granting administrative, execution, or financial access to users across
messaging platforms (Telegram, Discord, Slack, etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import string
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Gateway.Pairing")

DEFAULT_PAIRED_USERS_STORE = "data/paired_users.json"


@dataclass
class PairedUserRecord:
    """Record of a verified and authorized user for a specific platform."""
    platform: str
    user_id: str
    username: Optional[str] = None
    paired_at: float = field(default_factory=time.time)
    role: str = "operator"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivePairingRequest:
    """In-memory active OTP challenge waiting for user input."""
    platform: str
    user_id: str
    username: Optional[str]
    salt: str
    otp_hash: str
    created_at: float
    expires_at: float
    attempts: int = 0
    max_attempts: int = 3


class PairingManager:
    """
    Manages user authorization via secure out-of-band console OTP pairing.
    Prevents unauthorized strangers on public messaging platforms from controlling
    the trading agent or issuing arbitrary execution commands.
    """

    def __init__(self, store_path: str = DEFAULT_PAIRED_USERS_STORE):
        self.store_path = store_path
        self._lock = threading.RLock()
        self._paired_users: Dict[str, PairedUserRecord] = {}  # key: f"{platform}:{user_id}"
        self._pending_requests: Dict[str, ActivePairingRequest] = {}  # key: f"{platform}:{user_id}"
        self._load_store()

    def _make_key(self, platform: str, user_id: str) -> str:
        return f"{platform.strip().lower()}:{str(user_id).strip()}"

    def _load_store(self) -> None:
        """Loads verified paired users from disk."""
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                with self._lock:
                    self._paired_users.clear()
                    for item in data:
                        rec = PairedUserRecord(**item)
                        key = self._make_key(rec.platform, rec.user_id)
                        self._paired_users[key] = rec
            logger.info(f"[PairingManager] Loaded {len(self._paired_users)} paired user(s) from {self.store_path}")
        except Exception as exc:
            logger.error(f"[PairingManager] Failed loading paired users store: {exc}")

    def _save_store(self) -> None:
        """Persists paired users atomically to disk."""
        try:
            store_dir = os.path.dirname(os.path.abspath(self.store_path))
            if store_dir:
                os.makedirs(store_dir, exist_ok=True)
            tmp_path = f"{self.store_path}.tmp"
            with self._lock:
                records = [asdict(r) for r in list(self._paired_users.values())]
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            os.replace(tmp_path, self.store_path)
        except Exception as exc:
            logger.error(f"[PairingManager] Failed saving paired users: {exc}")

    def is_user_paired(self, platform: str, user_id: str) -> bool:
        """Checks if a given platform user has already completed OTP pairing."""
        key = self._make_key(platform, user_id)
        with self._lock:
            return key in self._paired_users

    def get_paired_user(self, platform: str, user_id: str) -> Optional[PairedUserRecord]:
        """Retrieves pairing details for an authorized user."""
        key = self._make_key(platform, user_id)
        with self._lock:
            return self._paired_users.get(key)

    def generate_otp_code(self) -> str:
        """Generates a high-entropy 8-character OTP (format: XXXX-XXXX, excluding confusing chars)."""
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # Excludes 0, 1, I, O
        p1 = "".join(secrets.choice(alphabet) for _ in range(4))
        p2 = "".join(secrets.choice(alphabet) for _ in range(4))
        return f"{p1}-{p2}"

    def _hash_otp(self, otp_code: str, salt: str) -> str:
        """Computes salted SHA-256 hash of normalized OTP."""
        normalized = otp_code.replace("-", "").strip().upper()
        payload = f"{salt}:{normalized}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def create_pairing_request(
        self,
        platform: str,
        user_id: str,
        username: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> Tuple[str, str]:
        """
        Creates an active OTP challenge for an unverified user.
        Prints the OTP to the operator's local terminal/log for security.
        
        Returns:
            (instructions_for_user: str, raw_otp_for_operator: str)
        """
        key = self._make_key(platform, user_id)
        now = time.time()

        # Generate fresh OTP and salt
        raw_otp = self.generate_otp_code()
        salt = secrets.token_hex(8)
        otp_hash = self._hash_otp(raw_otp, salt)

        req = ActivePairingRequest(
            platform=platform,
            user_id=str(user_id),
            username=username,
            salt=salt,
            otp_hash=otp_hash,
            created_at=now,
            expires_at=now + ttl_seconds,
            attempts=0,
            max_attempts=3,
        )

        with self._lock:
            self._pending_requests[key] = req

        # Security invariant: Print OTP to host console / system logs
        logger.warning(
            f"\n=======================================================\n"
            f"[SECURITY PAIRING CHALLENGE]\n"
            f"Platform: {platform.upper()} | User ID: {user_id} | Username: @{username or 'N/A'}\n"
            f"One-Time Pairing Code: >>>  {raw_otp}  <<<\n"
            f"Expires in {ttl_seconds} seconds. Enter '/pair {raw_otp}' in chat.\n"
            f"======================================================="
        )

        user_message = (
            "**[OTORISASI DIPERLUKAN] Pairing Authorization Required (Pemasangan Akun)**\n\n"
            "Sistem Monika memerlukan otorisasi sebelum memproses instruksi pada channel ini.\n"
            "Kode otorisasi (8 karakter) telah ditampilkan pada konsol server Monika.\n\n"
            "Silakan periksa konsol server Anda dan balas dengan format:\n"
            "`/pair <KODE>`"
        )
        return user_message, raw_otp

    def verify_pairing_code(self, platform: str, user_id: str, input_code: str) -> Tuple[bool, str]:
        """
        Verifies input OTP code against active challenge.
        On success, registers user permanently to the authorized store.
        """
        key = self._make_key(platform, user_id)
        now = time.time()

        with self._lock:
            req = self._pending_requests.get(key)
            if not req:
                return False, "[GAGAL] Tidak ditemukan permintaan pairing aktif. Silakan minta kode baru."

            if now > req.expires_at:
                self._pending_requests.pop(key, None)
                return False, "[KEDALUWARSA] Kode pairing telah kedaluwarsa. Silakan lakukan pairing ulang."

            req.attempts += 1
            calculated_hash = self._hash_otp(input_code, req.salt)

            if secrets.compare_digest(calculated_hash, req.otp_hash):
                # Correct OTP! Authorize permanently
                record = PairedUserRecord(
                    platform=req.platform,
                    user_id=req.user_id,
                    username=req.username,
                    paired_at=now,
                    role="operator",
                )
                self._paired_users[key] = record
                self._pending_requests.pop(key, None)
                self._save_store()
                logger.info(f"[PairingManager] Successfully authorized user {key} (User: @{req.username})")
                return True, "[BERHASIL] Pairing berhasil! Akun Anda kini telah terotorisasi sebagai operator Monika."

            # Failed match
            remaining = req.max_attempts - req.attempts
            if remaining <= 0:
                self._pending_requests.pop(key, None)
                logger.warning(f"[PairingManager] Max pairing attempts exceeded for {key}. Request revoked.")
                return False, "[GAGAL] Kode tidak valid. Batas percobaan habis. Permintaan dibatalkan."

            return False, f"[GAGAL] Kode pairing tidak valid. Tersisa {remaining} kesempatan lagi."

    def unpair_user(self, platform: str, user_id: str) -> bool:
        """Revokes authorization for a paired user."""
        key = self._make_key(platform, user_id)
        with self._lock:
            if key in self._paired_users:
                self._paired_users.pop(key)
                self._save_store()
                logger.info(f"[PairingManager] Revoked authorization for user {key}")
                return True
            return False

    def list_paired_users(self, platform: Optional[str] = None) -> List[PairedUserRecord]:
        """Lists all authorized users, optionally filtered by platform."""
        with self._lock:
            records = list(self._paired_users.values())
        if platform:
            plat_clean = platform.strip().lower()
            return [r for r in records if r.platform.lower() == plat_clean]
        return records


# Global singleton instance
_GLOBAL_PAIRING_MANAGER: Optional[PairingManager] = None


def get_pairing_manager(store_path: str = DEFAULT_PAIRED_USERS_STORE) -> PairingManager:
    """Returns global singleton PairingManager."""
    global _GLOBAL_PAIRING_MANAGER
    if _GLOBAL_PAIRING_MANAGER is None:
        _GLOBAL_PAIRING_MANAGER = PairingManager(store_path=store_path)
    return _GLOBAL_PAIRING_MANAGER


def reset_pairing_manager() -> None:
    """Resets global singleton for testing purposes."""
    global _GLOBAL_PAIRING_MANAGER
    _GLOBAL_PAIRING_MANAGER = None


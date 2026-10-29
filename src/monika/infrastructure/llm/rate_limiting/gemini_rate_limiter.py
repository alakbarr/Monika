# ==============================================================================
# File: utils/gemini_rate_limiter.py
# ==============================================================================

"""
GeminiRateLimiter — Fast-path in-memory rate limiter dengan persistensi DB berkala.
Mendukung pelacakan per model kanonikal, isolasi per key_id, dan reset waktu Pasifik (US/Pacific).
"""

import asyncio
import json
import logging
import os
import time
import zoneinfo
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, ClassVar, Optional

logger = logging.getLogger("TradingAgent.GeminiRateLimiter")

PT_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")

_QUOTA_LOCK: Optional[asyncio.Lock] = None
_QUOTA_LOCK_LOOP: Any = None


def get_today_pt() -> str:
    """Mengembalikan tanggal hari ini dalam zona waktu US/Pacific (sinkron dengan server Google AI Studio)."""
    return datetime.now(PT_TZ).strftime("%Y-%m-%d")


def canonical_gemini_model_name(model_name: str) -> str:
    """Normalisasi nama model Gemini ke bentuk kanonikal (menghapus prefix gc/, ag/, google/, dll)."""
    if not model_name:
        return ""
    m = model_name.strip()
    for prefix in ("gc/", "ag/", "google/", "gemini:"):
        if m.startswith(prefix):
            m = m[len(prefix) :]
    if m.endswith("-high"):
        m = m[:-5]
    return m


def _get_quota_lock() -> asyncio.Lock:
    global _QUOTA_LOCK, _QUOTA_LOCK_LOOP
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _QUOTA_LOCK is None or _QUOTA_LOCK_LOOP != loop:
        _QUOTA_LOCK = asyncio.Lock()
        _QUOTA_LOCK_LOOP = loop
    return _QUOTA_LOCK


def _get_num_keys() -> int:
    raw = os.getenv("GEMINI_API_KEYS", "")
    keys = [k for k in raw.split(",") if k.strip()]
    if not keys and os.getenv("GEMINI_API_KEY"):
        keys = [os.getenv("GEMINI_API_KEY")]
    return max(1, len(keys))


_CUSTOM_QUOTAS: dict[str, int] = {}


def get_quota_for_model(model_name: str) -> dict:
    num_keys = _get_num_keys()
    canon = canonical_gemini_model_name(model_name).lower()
    if "pro" in canon or "argon" in canon:
        rpd = _CUSTOM_QUOTAS.get("pro_daily_quota", 10000)
        return {"rpd": rpd, "rpm": 360}
    if "lite" in canon:
        rpd = _CUSTOM_QUOTAS.get("flash_lite_daily_quota", 500 * num_keys)
        return {"rpd": rpd, "rpm": 15 * num_keys}
    rpd = _CUSTOM_QUOTAS.get("flash_daily_quota", 500 * num_keys)
    return {"rpd": rpd, "rpm": 15 * num_keys}


def configure_from_settings(settings: dict) -> None:
    num_keys = _get_num_keys()
    gemini_cfg = (settings or {}).get("gemini", {}) or (settings or {}).get("llm", {}).get("providers", {}).get(
        "gemini", {}
    )
    if "flash_daily_quota" in gemini_cfg:
        _CUSTOM_QUOTAS["flash_daily_quota"] = int(gemini_cfg["flash_daily_quota"]) * num_keys
    if "flash_lite_daily_quota" in gemini_cfg:
        _CUSTOM_QUOTAS["flash_lite_daily_quota"] = int(gemini_cfg["flash_lite_daily_quota"]) * num_keys


class GeminiRateLimiter:
    # Class-level shared state — keyed by (canon_model, key_id) or canon_model
    _daily_counts: ClassVar[dict] = {}  # {(model, key_id): {"date": "2026-10-28", "count": 5}}
    _rpm_windows: ClassVar[dict] = defaultdict(deque)
    _rpm_lock: ClassVar[Optional[asyncio.Lock]] = None
    _rpm_lock_loop: ClassVar[Any] = None
    _BACKGROUND_TASKS: ClassVar[set] = set()
    _initialized: ClassVar[bool] = False

    @classmethod
    def _get_rpm_lock(cls) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if cls._rpm_lock is None or cls._rpm_lock_loop != loop:
            cls._rpm_lock = asyncio.Lock()
            cls._rpm_lock_loop = loop
        return cls._rpm_lock

    def __init__(self, session=None):
        self._session = session

    @staticmethod
    def _resolve_key_id(api_key: Optional[str] = None) -> str:
        if api_key:
            return api_key[-8:]
        return "default"

    @classmethod
    async def _ensure_initialized(cls, session) -> None:
        """Muat jumlah penggunaan hari ini dari DB (persisten antar restart, sinkron US/Pacific)."""
        if cls._initialized:
            return
        cls._initialized = True
        today = get_today_pt()

        try:
            from sqlalchemy import select
            from monika.infrastructure.database.models import SystemConfig

            prefix = "gemini_quota_%"
            suffix = f"%_{today}"
            cfgs = (
                (
                    await session.execute(
                        select(SystemConfig).where(SystemConfig.key.like(prefix)).where(SystemConfig.key.like(suffix))
                    )
                )
                .scalars()
                .all()
            )

            for cfg in cfgs:
                parts = cfg.key.split("_")
                if len(parts) >= 4:
                    raw_model = "_".join(parts[2:-1])
                    canon_model = canonical_gemini_model_name(raw_model)
                    try:
                        count = int(cfg.value) if cfg.value else 0
                    except ValueError:
                        count = 0
                    key_tuple = (canon_model, "default")
                    cls._daily_counts[key_tuple] = {"date": today, "count": count}
                    # Keep backward compatibility for string keys
                    cls._daily_counts[canon_model] = {"date": today, "count": count}
        except Exception as e:
            logger.warning(f"Failed to load Gemini quota from DB: {e}")

    async def _persist_count(self, model: str, key_id: str = "default") -> None:
        """Simpan jumlah penggunaan saat ini ke DB secara asinkron (best-effort)."""
        if not self._session:
            return
        try:
            today = get_today_pt()
            canon = canonical_gemini_model_name(model)
            key = f"gemini_quota_{canon}_{today}"
            key_tuple = (canon, key_id)
            count = self._daily_counts.get(key_tuple, self._daily_counts.get(canon, {})).get("count", 0)

            from monika.infrastructure.database.models import SystemConfig

            await SystemConfig.upsert(self._session, key=key, value=str(count))
            await self._session.commit()
        except Exception as e:
            logger.debug(f"Gemini quota persist failed (non-fatal): {e}")

    async def try_acquire(self, model: str, api_key: Optional[str] = None) -> bool:
        """Ambil (acquire) satu slot kuota secara atomik. Return True jika sukses."""
        if self._session:
            await self._ensure_initialized(self._session)

        today = get_today_pt()
        canon = canonical_gemini_model_name(model)
        key_id = self._resolve_key_id(api_key)
        key_tuple = (canon, key_id)

        cfg = get_quota_for_model(canon)
        max_rpd = cfg.get("rpd", 0)
        max_rpm = cfg.get("rpm", 999)

        # Atomic RPM check + record
        async with self._get_rpm_lock():
            window = self._rpm_windows[key_tuple]
            now = time.time()
            while window and now - window[0] > 60.0:
                window.popleft()

            if len(window) >= max_rpm:
                logger.warning(f"Gemini {canon} [{key_id}] RPM limit reached ({len(window)}/{max_rpm})")
                return False

            window.append(now)

        # Check and increment RPD (separate lock)
        acquired = False
        async with _get_quota_lock():
            if self._daily_counts.get(key_tuple, {}).get("date") != today:
                self._daily_counts[key_tuple] = {"date": today, "count": 0}

            current = self._daily_counts[key_tuple]["count"]
            if max_rpd > 0 and current >= max_rpd:
                logger.warning(f"Gemini {canon} [{key_id}] daily quota exhausted ({current}/{max_rpd})")
                # Rollback RPM record
                async with self._get_rpm_lock():
                    try:
                        self._rpm_windows[key_tuple].remove(now)
                    except ValueError:
                        pass
                return False

            self._daily_counts[key_tuple]["count"] = current + 1
            # Mirror to string key for legacy compatibility
            self._daily_counts[canon] = {"date": today, "count": self._daily_counts[key_tuple]["count"]}
            acquired = True

        # Persist periodically with strong task reference
        if acquired and self._daily_counts[key_tuple]["count"] % 5 == 0:
            task = asyncio.create_task(self._persist_async(canon, today, key_tuple))
            self._BACKGROUND_TASKS.add(task)
            task.add_done_callback(self._BACKGROUND_TASKS.discard)

        return acquired

    async def _persist_async(self, canon_model: str, today: str, key_tuple: tuple) -> None:
        """Simpan data di background agar tidak memblokir main thread."""
        try:
            from monika.infrastructure.database.db import get_session as _gs

            async with _gs() as persist_session:
                key = f"gemini_quota_{canon_model}_{today}"
                count = self._daily_counts.get(key_tuple, {}).get("count", 0)
                from monika.infrastructure.database.models import SystemConfig as _SC

                await _SC.upsert(persist_session, key=key, value=str(count))
                await persist_session.commit()
        except Exception as e:
            logger.debug(f"Gemini quota async persist failed (non-fatal): {e}")

    async def check_quota(self, model: str, api_key: Optional[str] = None) -> bool:
        """Cek ketersediaan kuota tanpa mengurangi saldo."""
        if self._session:
            await self._ensure_initialized(self._session)
        today = get_today_pt()
        canon = canonical_gemini_model_name(model)
        key_id = self._resolve_key_id(api_key)
        key_tuple = (canon, key_id)

        cfg = get_quota_for_model(canon)
        max_rpd = cfg.get("rpd", 0)
        async with _get_quota_lock():
            current = self._daily_counts.get(key_tuple, self._daily_counts.get(canon, {})).get("count", 0)
            if self._daily_counts.get(key_tuple, {}).get("date") != today:
                current = 0
            return current < max_rpd

    async def consume_quota(self, model: str, api_key: Optional[str] = None) -> bool:
        """Deprecated: gunakan try_acquire() saja."""
        return await self.try_acquire(model, api_key=api_key)

    async def get_usage(self, model: str) -> dict:
        """
        Ambil statistik penggunaan harian terkini.
        Mendukung query model kanonikal maupun query agregasi dashboard ('flash', 'flash_lite').
        """
        if self._session:
            await self._ensure_initialized(self._session)
        today = get_today_pt()
        q = model.lower().strip()
        cfg = get_quota_for_model(model)
        max_rpd = cfg.get("rpd", 0)

        # Aggregate counts for category queries from dashboard / scheduler
        total_used = 0
        is_category_query = q in ("flash", "flash_lite", "flash-lite")

        if is_category_query:
            for k, val in list(self._daily_counts.items()):
                if not isinstance(val, dict) or val.get("date") != today:
                    continue
                # Extract model string from key (tuple or string)
                m_str = (k[0] if isinstance(k, tuple) else str(k)).lower()
                c_count = val.get("count", 0)
                if q in ("flash_lite", "flash-lite"):
                    if "lite" in m_str:
                        total_used += c_count
                elif q == "flash":
                    if "flash" in m_str and "lite" not in m_str:
                        total_used += c_count
            current = total_used
        else:
            canon = canonical_gemini_model_name(model)
            current = self._daily_counts.get(canon, {}).get("count", 0)
            if not current:
                # Sum over all keys for this canonical model
                for k, val in list(self._daily_counts.items()):
                    if isinstance(k, tuple) and k[0] == canon and val.get("date") == today:
                        current += val.get("count", 0)
            if self._daily_counts.get(canon, {}).get("date") != today and current == 0:
                current = 0

        return {
            "tier": model,
            "date": today,
            "used": current,
            "remaining": max(0, max_rpd - current),
            "max_rpd": max_rpd,
        }

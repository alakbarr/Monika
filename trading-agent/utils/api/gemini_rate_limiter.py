# ==============================================================================
# File: utils/gemini_rate_limiter.py
# ==============================================================================

"""
GeminiRateLimiter — Fast-path in-memory rate limiter dengan persistensi DB berkala.
"""
import asyncio
import json
import logging
import time
from collections import deque, defaultdict
from datetime import datetime, timezone
from typing import ClassVar

logger = logging.getLogger("TradingAgent.GeminiRateLimiter")

_QUOTA_LOCK = asyncio.Lock()

import os

def _get_num_keys() -> int:
    raw = os.getenv("GEMINI_API_KEYS", "")
    keys = [k for k in raw.split(",") if k.strip()]
    if not keys and os.getenv("GEMINI_API_KEY"):
        keys = [os.getenv("GEMINI_API_KEY")]
    return max(1, len(keys))

_CUSTOM_QUOTAS = {}

def get_quota_for_model(model_name: str) -> dict:
    num_keys = _get_num_keys()
    if "pro" in model_name.lower():
        rpd = _CUSTOM_QUOTAS.get("pro_daily_quota", 10000)
        return {"rpd": rpd, "rpm": 360}
    if "lite" in model_name:
        rpd = _CUSTOM_QUOTAS.get("flash_lite_daily_quota", 500 * num_keys)
        return {"rpd": rpd, "rpm": 15 * num_keys}
    rpd = _CUSTOM_QUOTAS.get("flash_daily_quota", 500 * num_keys)
    return {"rpd": rpd, "rpm": 15 * num_keys}

def configure_from_settings(settings: dict) -> None:
    num_keys = _get_num_keys()
    gemini_cfg = settings.get("gemini", {})
    if "flash_daily_quota" in gemini_cfg:
        _CUSTOM_QUOTAS["flash_daily_quota"] = int(gemini_cfg["flash_daily_quota"]) * num_keys
    if "flash_lite_daily_quota" in gemini_cfg:
        _CUSTOM_QUOTAS["flash_lite_daily_quota"] = int(gemini_cfg["flash_lite_daily_quota"]) * num_keys


class GeminiRateLimiter:
    # Class-level shared state — persists across instances within same process
    _daily_counts: ClassVar[dict] = {}   # {"gemini-3.5-flash": {"date": "2026-08-08", "count": 5}}
    _rpm_windows: ClassVar[dict] = defaultdict(deque)
    _rpm_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _initialized: ClassVar[bool] = False

    def __init__(self, session=None):
        # session is kept for backward compatibility but used only for initial load
        self._session = session

    @classmethod
    async def _ensure_initialized(cls, session) -> None:
        """Muat jumlah penggunaan hari ini dari DB (persisten antar restart)."""
        if cls._initialized:
            return
        cls._initialized = True
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        try:
            from sqlalchemy import select
            from database.models import SystemConfig
            
            # We will lazy-load counts per model as they are encountered instead of pre-loading all possible models here.
            # But we can try to fetch all gemini_quota_%_today configs
            prefix = f"gemini_quota_%"
            suffix = f"%_{today}"
            cfgs = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.like(prefix)).where(SystemConfig.key.like(suffix))
            )).scalars().all()
            
            for cfg in cfgs:
                # Key format: gemini_quota_{model}_{date}
                parts = cfg.key.split("_")
                # e.g. gemini_quota_gemini-3.5-flash-lite_2026-08-15
                if len(parts) >= 4:
                    model = "_".join(parts[2:-1])
                    try:
                        count = int(cfg.value) if cfg.value else 0
                    except ValueError:
                        count = 0
                    cls._daily_counts[model] = {"date": today, "count": count}
        except Exception as e:
            logger.warning(f"Failed to load Gemini quota from DB: {e}")

    async def _persist_count(self, model: str) -> None:
        """Simpan jumlah penggunaan saat ini ke DB secara asinkron (best-effort)."""
        if not self._session:
            return
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"gemini_quota_{model}_{today}"
            count = self._daily_counts[model]["count"]
            
            from sqlalchemy import select
            from database.models import SystemConfig
            
            cfg = (await self._session.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )).scalar_one_or_none()
            
            if cfg:
                cfg.value = str(count)
            else:
                self._session.add(SystemConfig(key=key, value=str(count)))
            await self._session.commit()
        except Exception as e:
            logger.debug(f"Gemini quota persist failed (non-fatal): {e}")

    async def try_acquire(self, model: str) -> bool:
        """Ambil (acquire) satu slot kuota secara atomik. Return True jika sukses."""
        if self._session:
            await self._ensure_initialized(self._session)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cfg = get_quota_for_model(model)
        max_rpd = cfg.get("rpd", 0)
        max_rpm = cfg.get("rpm", 999)

        # Atomic RPM check + record (single lock acquisition prevents race condition)
        async with self._rpm_lock:
            window = self._rpm_windows[model]
            now = time.time()
            # Remove entries older than 60 seconds
            while window and now - window[0] > 60.0:
                window.popleft()
            
            if len(window) >= max_rpm:
                logger.warning(f"Gemini {model} RPM limit reached ({len(window)}/{max_rpm})")
                return False
            
            # Tentative: record BEFORE RPD check (will remove if RPD fails)
            window.append(now)
            rpm_recorded = True

        # Check and increment RPD (separate lock)
        acquired = False
        async with _QUOTA_LOCK:
            if self._daily_counts.get(model, {}).get("date") != today:
                self._daily_counts[model] = {"date": today, "count": 0}
            
            current = self._daily_counts[model]["count"]
            if max_rpd > 0 and current >= max_rpd:
                logger.warning(f"Gemini {model} daily quota exhausted ({current}/{max_rpd})")
                # Rollback RPM record
                async with self._rpm_lock:
                    try:
                        self._rpm_windows[model].remove(now)
                    except ValueError:
                        pass
                return False
            
            self._daily_counts[model]["count"] = current + 1
            acquired = True

        # Persist periodically
        if acquired and self._daily_counts[model]["count"] % 5 == 0:
            asyncio.create_task(self._persist_async(model, today))
        
        return acquired

    async def _persist_async(self, model: str, today: str) -> None:
        """Simpan data di background agar tidak memblokir main thread."""
        try:
            from database.db import get_session as _gs
            async with _gs() as persist_session:
                key = f"gemini_quota_{model}_{today}"
                count = self._daily_counts.get(model, {}).get("count", 0)
                from sqlalchemy import select as _sel
                from database.models import SystemConfig as _SC
                cfg = (await persist_session.execute(
                    _sel(_SC).where(_SC.key == key)
                )).scalar_one_or_none()
                if cfg:
                    cfg.value = str(count)
                else:
                    persist_session.add(_SC(key=key, value=str(count)))
                await persist_session.commit()
        except Exception as e:
            logger.debug(f"Gemini quota async persist failed (non-fatal): {e}")

    async def check_quota(self, model: str) -> bool:
        """Cek ketersediaan kuota tanpa mengurangi saldo."""
        if self._session:
            await self._ensure_initialized(self._session)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cfg = get_quota_for_model(model)
        max_rpd = cfg.get("rpd", 0)
        current = self._daily_counts.get(model, {}).get("count", 0)
        if self._daily_counts.get(model, {}).get("date") != today:
            current = 0
        return current < max_rpd

    async def consume_quota(self, model: str) -> bool:
        """Deprecated: gunakan try_acquire() saja."""
        return await self.try_acquire(model)

    async def get_usage(self, model: str) -> dict:
        """Ambil statistik penggunaan harian terkini."""
        if self._session:
            await self._ensure_initialized(self._session)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cfg = get_quota_for_model(model)
        max_rpd = cfg.get("rpd", 0)
        current = self._daily_counts.get(model, {}).get("count", 0)
        if self._daily_counts.get(model, {}).get("date") != today:
            current = 0
        return {
            "tier": model,
            "date": today,
            "used": current,
            "remaining": max_rpd - current,
            "max_rpd": max_rpd,
        }

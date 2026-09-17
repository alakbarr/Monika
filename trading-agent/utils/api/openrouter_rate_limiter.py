"""
OpenRouterRateLimiter — In-memory rate limiter dan key manager untuk OpenRouter API.
Mendukung pemisahan Paid Key vs Free Keys dan tracking sliding window RPM/RPD.
"""
import asyncio
import time
import logging
import os
from collections import deque, defaultdict
from typing import ClassVar, Optional

logger = logging.getLogger("TradingAgent.OpenRouterRateLimiter")

def get_paid_key() -> Optional[str]:
    """Mengambil API key khusus tier berbayar (fallback: OPENROUTER_API_KEY)."""
    return os.getenv("OPENROUTER_PAID_API_KEY") or os.getenv("OPENROUTER_API_KEY") or None

def get_free_keys() -> list[str]:
    """Mengambil daftar API key khusus tier gratis dari OPENROUTER_API_KEYS."""
    raw = os.getenv("OPENROUTER_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]

def get_all_keys() -> list[str]:
    """Menggabungkan seluruh kunci (paid + free) tanpa duplikasi."""
    all_keys = []
    paid = get_paid_key()
    if paid:
        all_keys.append(paid)
    for k in get_free_keys():
        if k not in all_keys:
            all_keys.append(k)
    return all_keys

def is_free_tier_model(model: str) -> bool:
    """Mendeteksi apakah model merupakan varian free-tier OpenRouter."""
    if not model:
        return False
    m = model.lower()
    if m.endswith(":free"):
        return True
    if m in ("ox-alpha", "0x-alpha", "stealth/ox-alpha", "openrouter/free", "openrouter-free"):
        return True
    if "ox-alpha" in m or ":free" in m:
        return True
    return False

# Default limits per key on OpenRouter (RPM 20, RPD 200 for free; RPM 100, RPD 10000 for paid)
_num_keys = max(1, len(get_all_keys()))
DEFAULT_FREE_QUOTA_PER_KEY = {"rpm": 20, "rpd": 200}
DEFAULT_PAID_QUOTA_PER_KEY = {"rpm": 100, "rpd": 10000}

# Expose multiplied quota for backward compatibility
DEFAULT_FREE_QUOTA = {"rpm": 20 * _num_keys, "rpd": 200 * _num_keys}
DEFAULT_PAID_QUOTA = {"rpm": 100, "rpd": 10000}

import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "openrouter_rate_limit_state.json"

class OpenRouterRateLimiter:
    """Sliding window rate limiter untuk OpenRouter API — keyed per (model, key_id)."""
    _rpm_windows: ClassVar[dict] = defaultdict(deque)
    _daily_counts: ClassVar[dict] = {}
    _cooldowns: ClassVar[dict] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _loaded_from_disk: ClassVar[bool] = False

    @classmethod
    def _ensure_loaded(cls):
        if cls._loaded_from_disk:
            return
        cls._loaded_from_disk = True
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                or_data = data.get("openrouter", data)
                counts = or_data.get("daily_counts", {})
                for k_str, val in counts.items():
                    if "||" in k_str:
                        model, key_id = k_str.split("||", 1)
                        cls._daily_counts[(model, key_id)] = val
                cooldowns = or_data.get("cooldowns", {})
                for k_str, until in cooldowns.items():
                    if "||" in k_str:
                        model, key_id = k_str.split("||", 1)
                        cls._cooldowns[(model, key_id)] = until
        except Exception as e:
            logger.debug(f"Could not load rate limit state from disk: {e}")

    @classmethod
    def _save_state(cls):
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            daily_payload = {
                f"{k[0]}||{k[1]}": v for k, v in cls._daily_counts.items()
            }
            cooldown_payload = {
                f"{k[0]}||{k[1]}": v for k, v in cls._cooldowns.items() if v > time.time()
            }
            data = {
                "openrouter": {
                    "daily_counts": daily_payload,
                    "cooldowns": cooldown_payload,
                    "updated_at": time.time()
                }
            }
            tmp_file = _STATE_FILE.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp_file, _STATE_FILE)
        except Exception as e:
            logger.debug(f"Could not save rate limit state to disk: {e}")

    def _resolve_key_id(self, api_key: Optional[str] = None) -> str:
        if api_key:
            return api_key[-8:]
        return "default"

    @classmethod
    def mark_cooldown(cls, model: str, api_key: Optional[str] = None, cooldown_seconds: float = 3600) -> None:
        """Tandai kunci API / model sedang dalam masa cooldown (misal setelah HTTP 429)."""
        cls._ensure_loaded()
        key_id = api_key[-8:] if api_key else "default"
        key_tuple = (model, key_id)
        until = time.time() + cooldown_seconds
        cls._cooldowns[key_tuple] = until
        cls._save_state()
        logger.warning(f"OpenRouter [{key_id}] cooldown marked for {model} until {time.ctime(until)} ({cooldown_seconds}s)")

    async def try_acquire(self, model: str, api_key: Optional[str] = None) -> bool:
        self._ensure_loaded()
        is_free = is_free_tier_model(model)
        quota = DEFAULT_FREE_QUOTA_PER_KEY if is_free else DEFAULT_PAID_QUOTA_PER_KEY
        max_rpm = quota.get("rpm", 20 if is_free else 100)
        max_rpd = quota.get("rpd", 200 if is_free else 10000)
        today = time.strftime("%Y-%m-%d")
        now = time.time()
        key_tuple = (model, self._resolve_key_id(api_key))

        async with self._lock:
            # Check cooldown
            if key_tuple in self._cooldowns:
                cooldown_until = self._cooldowns[key_tuple]
                if now < cooldown_until:
                    logger.warning(f"OpenRouter {model} [{key_tuple[1]}] is in cooldown for {int(cooldown_until - now)}s")
                    return False
                else:
                    self._cooldowns.pop(key_tuple, None)

            # RPM window check
            window = self._rpm_windows[key_tuple]
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= max_rpm:
                logger.warning(f"OpenRouter {model} [{key_tuple[1]}] RPM limit reached ({len(window)}/{max_rpm})")
                return False

            # RPD daily check
            if self._daily_counts.get(key_tuple, {}).get("date") != today:
                self._daily_counts[key_tuple] = {"date": today, "count": 0}
            count = self._daily_counts[key_tuple]["count"]
            if count >= max_rpd:
                logger.warning(f"OpenRouter {model} [{key_tuple[1]}] RPD limit reached ({count}/{max_rpd})")
                return False

            window.append(now)
            self._daily_counts[key_tuple]["count"] += 1
            self._save_state()
            return True

    async def check_quota(self, model: str, api_key: Optional[str] = None) -> bool:
        self._ensure_loaded()
        is_free = is_free_tier_model(model)
        quota = DEFAULT_FREE_QUOTA_PER_KEY if is_free else DEFAULT_PAID_QUOTA_PER_KEY
        today = time.strftime("%Y-%m-%d")
        key_tuple = (model, self._resolve_key_id(api_key))
        if key_tuple in self._cooldowns and time.time() < self._cooldowns[key_tuple]:
            return False
        if self._daily_counts.get(key_tuple, {}).get("date") != today:
            return True
        return self._daily_counts[key_tuple]["count"] < quota.get("rpd", 200 if is_free else 10000)

    async def get_usage(self, model: str, api_key: Optional[str] = None) -> dict:
        self._ensure_loaded()
        is_free = is_free_tier_model(model)
        quota = DEFAULT_FREE_QUOTA_PER_KEY if is_free else DEFAULT_PAID_QUOTA_PER_KEY
        today = time.strftime("%Y-%m-%d")
        key_tuple = (model, self._resolve_key_id(api_key))
        count = 0
        if self._daily_counts.get(key_tuple, {}).get("date") == today:
            count = self._daily_counts[key_tuple]["count"]
        cooldown_remaining = max(0, int(self._cooldowns.get(key_tuple, 0) - time.time()))
        return {
            "model": model,
            "key_id": key_tuple[1],
            "is_free_tier": is_free,
            "date": today,
            "used": count,
            "remaining": max(0, quota.get("rpd", 200 if is_free else 10000) - count),
            "max_rpd": quota.get("rpd", 200 if is_free else 10000),
            "max_rpm": quota.get("rpm", 20 if is_free else 100),
            "cooldown_remaining_s": cooldown_remaining,
        }

    @classmethod
    def reset(cls, model: Optional[str] = None) -> None:
        """Mereset jendela RPM dan hitungan harian untuk model tertentu atau seluruh model."""
        if model:
            keys_to_del_rpm = [k for k in cls._rpm_windows if (isinstance(k, tuple) and k[0] == model) or k == model]
            for k in keys_to_del_rpm:
                cls._rpm_windows.pop(k, None)
            keys_to_del_daily = [k for k in cls._daily_counts if (isinstance(k, tuple) and k[0] == model) or k == model]
            for k in keys_to_del_daily:
                cls._daily_counts.pop(k, None)
            keys_to_del_cd = [k for k in cls._cooldowns if (isinstance(k, tuple) and k[0] == model) or k == model]
            for k in keys_to_del_cd:
                cls._cooldowns.pop(k, None)
            logger.info(f"OpenRouterRateLimiter reset for model: {model}")
        else:
            cls._rpm_windows.clear()
            cls._daily_counts.clear()
            cls._cooldowns.clear()
            logger.info("OpenRouterRateLimiter reset for all models.")
        cls._save_state()

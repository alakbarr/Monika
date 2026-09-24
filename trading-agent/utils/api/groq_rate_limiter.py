"""
GroqRateLimiter — In-memory rate limiter untuk Groq API.
Groq memiliki limit sangat ketat: RPM 30, RPD 250-1000.
"""
import asyncio
import time
import logging
import os
from collections import deque, defaultdict
from typing import ClassVar, Optional

logger = logging.getLogger("TradingAgent.GroqRateLimiter")

def get_api_keys() -> list[str]:
    """Parse GROQ_API_KEYS env var. Fallback ke GROQ_API_KEY (backward compat)."""
    raw = os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", ""))
    return [k.strip() for k in raw.split(",") if k.strip()]

_num_keys = max(1, len(get_api_keys()))

# Quota per model alias (per individual key)
GROQ_QUOTA_PER_KEY = {
    "groq/compound":       {"rpm": 30, "rpd": 250,  "tpm": 70000},
    "groq/compound-mini":  {"rpm": 30, "rpd": 250,  "tpm": 70000},
    "groq-compound":       {"rpm": 30, "rpd": 250,  "tpm": 70000},
    "openai/gpt-oss-120b": {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "openai/gpt-oss-20b":  {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "groq-gpt-oss-120b":   {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "groq-gpt-oss-20b":    {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "qwen/qwen3.6-27b":    {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
    "qwen/qwen3.8-27b":    {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 2000000},
    "groq-qwen3.8-27b":    {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 2000000},
    "groq-qwen3.6-27b":    {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000},
}
DEFAULT_QUOTA_PER_KEY = {"rpm": 30, "rpd": 250, "tpm": 70000}

# Expose multiplied quota for backward compatibility
GROQ_QUOTA = {k: {sub_k: sub_v * _num_keys for sub_k, sub_v in v.items()} for k, v in GROQ_QUOTA_PER_KEY.items()}
DEFAULT_QUOTA = {k: v * _num_keys for k, v in DEFAULT_QUOTA_PER_KEY.items()}

import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "groq_rate_limit_state.json"

class GroqRateLimiter:
    """Sliding window rate limiter untuk Groq API — keyed per (model, key_id)."""
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
                groq_data = data.get("groq", data)
                counts = groq_data.get("daily_counts", {})
                for k_str, val in counts.items():
                    if "||" in k_str:
                        model, key_id = k_str.split("||", 1)
                        cls._daily_counts[(model, key_id)] = val
                cooldowns = groq_data.get("cooldowns", {})
                for k_str, until in cooldowns.items():
                    if "||" in k_str:
                        model, key_id = k_str.split("||", 1)
                        cls._cooldowns[(model, key_id)] = until
        except Exception as e:
            logger.debug(f"Could not load Groq rate limit state from disk: {e}")

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
                "groq": {
                    "daily_counts": daily_payload,
                    "cooldowns": cooldown_payload,
                    "updated_at": time.time()
                }
            }
            tmp_file = _STATE_FILE.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp_file, _STATE_FILE)
        except Exception as e:
            logger.debug(f"Could not save Groq rate limit state to disk: {e}")

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
        logger.warning(f"Groq [{key_id}] cooldown marked for {model} until {time.ctime(until)} ({cooldown_seconds}s)")

    async def try_acquire(self, model: str, api_key: Optional[str] = None) -> bool:
        self._ensure_loaded()
        quota = GROQ_QUOTA_PER_KEY.get(model, DEFAULT_QUOTA_PER_KEY)
        max_rpm = quota.get("rpm", 30)
        max_rpd = quota.get("rpd", 250)
        today = time.strftime("%Y-%m-%d")
        now = time.time()
        key_tuple = (model, self._resolve_key_id(api_key))

        async with self._lock:
            # Check cooldown
            if key_tuple in self._cooldowns:
                cooldown_until = self._cooldowns[key_tuple]
                if now < cooldown_until:
                    logger.warning(f"Groq {model} [{key_tuple[1]}] is in cooldown for {int(cooldown_until - now)}s")
                    return False
                else:
                    self._cooldowns.pop(key_tuple, None)

            # RPM check
            window = self._rpm_windows[key_tuple]
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= max_rpm:
                logger.warning(f"Groq {model} [{key_tuple[1]}] RPM limit reached ({len(window)}/{max_rpm})")
                return False

            # RPD check
            if self._daily_counts.get(key_tuple, {}).get("date") != today:
                self._daily_counts[key_tuple] = {"date": today, "count": 0}
            count = self._daily_counts[key_tuple]["count"]
            if count >= max_rpd:
                logger.warning(f"Groq {model} [{key_tuple[1]}] RPD limit reached ({count}/{max_rpd})")
                return False

            window.append(now)
            self._daily_counts[key_tuple]["count"] += 1
            self._save_state()
            return True

    async def check_quota(self, model: str, api_key: Optional[str] = None) -> bool:
        self._ensure_loaded()
        quota = GROQ_QUOTA_PER_KEY.get(model, DEFAULT_QUOTA_PER_KEY)
        today = time.strftime("%Y-%m-%d")
        key_tuple = (model, self._resolve_key_id(api_key))
        if key_tuple in self._cooldowns and time.time() < self._cooldowns[key_tuple]:
            return False
        if self._daily_counts.get(key_tuple, {}).get("date") != today:
            return True
        return self._daily_counts[key_tuple]["count"] < quota.get("rpd", 250)

    async def get_usage(self, model: str, api_key: Optional[str] = None) -> dict:
        self._ensure_loaded()
        quota = GROQ_QUOTA_PER_KEY.get(model, DEFAULT_QUOTA_PER_KEY)
        today = time.strftime("%Y-%m-%d")
        key_tuple = (model, self._resolve_key_id(api_key))
        count = 0
        if self._daily_counts.get(key_tuple, {}).get("date") == today:
            count = self._daily_counts[key_tuple]["count"]
        cooldown_remaining = max(0, int(self._cooldowns.get(key_tuple, 0) - time.time()))
        return {
            "model": model,
            "key_id": key_tuple[1],
            "date": today,
            "used": count,
            "remaining": max(0, quota.get("rpd", 250) - count),
            "max_rpd": quota.get("rpd", 250),
            "max_rpm": quota.get("rpm", 30),
            "cooldown_remaining_s": cooldown_remaining,
        }

    @classmethod
    def reset(cls, model: Optional[str] = None) -> None:
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
        else:
            cls._rpm_windows.clear()
            cls._daily_counts.clear()
            cls._cooldowns.clear()
        cls._save_state()

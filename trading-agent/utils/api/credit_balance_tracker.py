"""
Credit Balance & Quota Tracker — Layanan pemantau saldo kredit live dan kuota seluruh provider.

Fitur:
1. OpenRouter Live Credits & Key Quota API (GET /api/v1/credits, GET /api/v1/key)
2. DeepSeek Live Balance API (GET /user/balance)
3. Google Gemini & Groq Free Tier Daily Quota Consumption Tracker (Database RPD/TPD)
4. Anthropic & OpenAI Monthly Expense Aggregator (Database)
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import aiohttp
from sqlalchemy import select, func

from database.db import get_session
from database.models import TokenUsageLog

logger = logging.getLogger("TradingAgent.CreditBalanceTracker")


class CreditBalanceTracker:
    """Layanan terpusat untuk memeriksa sisa kredit live dan kuota API seluruh provider."""

    @staticmethod
    async def fetch_openrouter_credits(api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Mengambil informasi sisa kredit OpenRouter untuk OPENROUTER_PAID_API_KEY (tier berbayar)
        serta status kesehatan pool OPENROUTER_API_KEYS (tier gratisan).
        Endpoint:
          - GET https://openrouter.ai/api/v1/credits
          - GET https://openrouter.ai/api/v1/key
        """
        from utils.api.openrouter_rate_limiter import get_paid_key, get_free_keys

        paid_key = api_key or get_paid_key()
        free_keys = get_free_keys()

        result = {
            "provider": "openrouter",
            "status": "unconfigured",
            "remaining_usd": None,
            "total_credits_usd": None,
            "total_usage_usd": None,
            "key_limit_usd": None,
            "key_usage_usd": None,
            "is_free_tier": False,
            "rate_limit": None,
            "paid_key": {
                "configured": bool(paid_key),
                "status": "unconfigured",
                "remaining_usd": None,
                "total_credits_usd": None,
                "total_usage_usd": None,
                "message": ""
            },
            "free_keys": {
                "configured_count": len(free_keys),
                "active_count": 0,
                "status": "unconfigured" if not free_keys else "ok",
                "details": []
            }
        }

        timeout = aiohttp.ClientTimeout(total=6.0)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. Query Paid Key (Saldo Berbayar)
                if paid_key and paid_key.strip() not in ("", "dummy", "placeholder", "dummy_key"):
                    headers_paid = {
                        "Authorization": f"Bearer {paid_key.strip()}",
                        "HTTP-Referer": "https://tradeagent.local",
                        "X-Title": "AI Trading Agent"
                    }
                    try:
                        async with session.get("https://openrouter.ai/api/v1/credits", headers=headers_paid) as resp:
                            if resp.status == 200:
                                data = (await resp.json()).get("data", {})
                                total_credits = float(data.get("total_credits", 0.0) or 0.0)
                                total_usage = float(data.get("total_usage", 0.0) or 0.0)
                                remaining = round(max(0.0, total_credits - total_usage), 4)

                                result["total_credits_usd"] = round(total_credits, 4)
                                result["total_usage_usd"] = round(total_usage, 4)
                                result["remaining_usd"] = remaining
                                result["status"] = "ok"

                                result["paid_key"]["status"] = "ok"
                                result["paid_key"]["total_credits_usd"] = round(total_credits, 4)
                                result["paid_key"]["total_usage_usd"] = round(total_usage, 4)
                                result["paid_key"]["remaining_usd"] = remaining
                            elif resp.status == 401:
                                result["paid_key"]["status"] = "auth_error"
                                result["paid_key"]["message"] = "OPENROUTER_PAID_API_KEY tidak valid (401)."
                                result["status"] = "auth_error"
                            elif resp.status == 402:
                                result["paid_key"]["status"] = "insufficient_credits"
                                result["paid_key"]["message"] = "Saldo OPENROUTER_PAID_API_KEY habis ($0.00)."
                    except Exception as e:
                        logger.debug(f"OpenRouter paid key credits check failed: {e}")
                        result["paid_key"]["status"] = "error"
                        result["paid_key"]["message"] = str(e)

                # 2. Query Free Keys Pool (Kunci-Kunci Model Gratisan)
                for idx, fk in enumerate(free_keys):
                    if not fk or fk.strip() in ("", "dummy", "placeholder", "dummy_key"):
                        continue
                    headers_free = {
                        "Authorization": f"Bearer {fk.strip()}",
                        "HTTP-Referer": "https://tradeagent.local",
                        "X-Title": "AI Trading Agent"
                    }
                    try:
                        async with session.get("https://openrouter.ai/api/v1/key", headers=headers_free) as resp:
                            if resp.status == 200:
                                kdata = (await resp.json()).get("data", {})
                                result["free_keys"]["active_count"] += 1
                                result["free_keys"]["details"].append({
                                    "index": idx + 1,
                                    "label": kdata.get("label", f"key_{idx+1}"),
                                    "is_free_tier": bool(kdata.get("is_free_tier", True)),
                                    "status": "active"
                                })
                            else:
                                result["free_keys"]["details"].append({
                                    "index": idx + 1,
                                    "status": f"http_{resp.status}"
                                })
                    except Exception as e:
                        logger.debug(f"OpenRouter free key #{idx+1} check failed: {e}")

                if not result["paid_key"]["configured"] and result["free_keys"]["active_count"] > 0:
                    result["status"] = "free_tier_only"

        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["message"] = "Koneksi ke OpenRouter API timeout (6s)."
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)

        return result

    @staticmethod
    async def fetch_deepseek_balance(api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Mengambil saldo live akun DeepSeek via endpoint resmi GET https://api.deepseek.com/user/balance.
        """
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key or key.strip() in ("", "dummy", "placeholder"):
            return {
                "provider": "deepseek",
                "status": "unconfigured",
                "message": "DEEPSEEK_API_KEY tidak disetel di environment."
            }

        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "Accept": "application/json"
        }

        result = {
            "provider": "deepseek",
            "status": "unknown",
            "is_available": False,
            "total_balance_usd": None,
            "granted_balance_usd": None,
            "topped_up_balance_usd": None,
            "currency": "USD"
        }

        timeout = aiohttp.ClientTimeout(total=6.0)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.deepseek.com/user/balance", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result["is_available"] = bool(data.get("is_available", True))
                        balance_infos = data.get("balance_infos", [])
                        if balance_infos:
                            info = balance_infos[0]
                            result["currency"] = info.get("currency", "USD")
                            result["total_balance_usd"] = float(info.get("total_balance", 0.0) or 0.0)
                            result["granted_balance_usd"] = float(info.get("granted_balance", 0.0) or 0.0)
                            result["topped_up_balance_usd"] = float(info.get("topped_up_balance", 0.0) or 0.0)
                        result["status"] = "ok"
                    elif resp.status == 401:
                        result["status"] = "auth_error"
                        result["message"] = "DeepSeek API Key tidak valid."
                    elif resp.status == 402:
                        result["status"] = "insufficient_balance"
                        result["message"] = "Saldo DeepSeek habis ($0.00)."
                    else:
                        result["status"] = f"http_{resp.status}"
                        result["message"] = f"DeepSeek returned status {resp.status}"
        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["message"] = "Koneksi ke DeepSeek API timeout (6s)."
        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)

        return result

    @staticmethod
    async def get_daily_quota_summary(session=None) -> Dict[str, Any]:
        """
        Menghitung konsumsi kuota harian Free Tier (RPD/TPD) untuk Gemini & Groq
        berdasarkan pemanggilan yang tercatat sejak 00:00 UTC hari ini.
        """
        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        async def _query(s):
            stmt = (
                select(
                    TokenUsageLog.provider,
                    TokenUsageLog.model_name,
                    func.count(TokenUsageLog.id).label("call_count"),
                    func.coalesce(func.sum(TokenUsageLog.total_tokens), 0).label("sum_tokens")
                )
                .where(TokenUsageLog.timestamp >= today_utc)
                .group_by(TokenUsageLog.provider, TokenUsageLog.model_name)
            )
            rows = (await s.execute(stmt)).all()
            return rows

        if session:
            rows = await _query(session)
        else:
            async with get_session() as s:
                rows = await _query(s)

        # Limits standar Google Gemini & Groq Free Tier
        LIMITS = {
            "gemini-3.7-flash": {"rpd_limit": 20, "label": "Gemini 3.7 Flash"},
            "gemini-3.6-flash": {"rpd_limit": 20, "label": "Gemini 3.6 Flash"},
            "gemini-3.5-flash": {"rpd_limit": 20, "label": "Gemini 3.5 Flash"},
            "gemini-3.5-flash-lite": {"rpd_limit": 500, "label": "Gemini 3.5 Flash-Lite"},
            "gemini-3.1-flash-lite": {"rpd_limit": 500, "label": "Gemini 3.1 Flash-Lite"},
            "gemini-3.0-flash-preview": {"rpd_limit": 500, "label": "Gemini 3.0 Flash"},
            "groq-compound": {"rpd_limit": 250, "tpd_limit": 2000000, "label": "Groq Compound"},
            "groq-compound-mini": {"rpd_limit": 250, "tpd_limit": 2000000, "label": "Groq Compound Mini"},
            "groq-gpt-oss-120b": {"rpd_limit": 1000, "tpd_limit": 200000, "label": "Groq GPT-OSS 120B"},
            "groq-gpt-oss-20b": {"rpd_limit": 1000, "tpd_limit": 200000, "label": "Groq GPT-OSS 20B"},
            "qwen3.6-27b": {"rpd_limit": 1000, "tpd_limit": 2000000, "label": "Groq Qwen 3.6 27B"},
            "groq-qwen3.6-27b": {"rpd_limit": 1000, "tpd_limit": 2000000, "label": "Groq Qwen 3.6 27B"},
            "qwen3.8-27b": {"rpd_limit": 1000, "tpd_limit": 2000000, "label": "Groq Qwen 3.8 27B"},
            "groq-qwen3.8-27b": {"rpd_limit": 1000, "tpd_limit": 2000000, "label": "Groq Qwen 3.8 27B"},
        }

        quota_data = {}
        for r in rows:
            m = str(r.model_name).lower()
            norm_m = m.replace("/", "-")
            cfg = LIMITS.get(m) or LIMITS.get(norm_m)
            if cfg:
                key_name = norm_m
                rpd_limit = cfg.get("rpd_limit", 500)
                used_calls = r.call_count
                remaining_calls = max(0, rpd_limit - used_calls)
                quota_data[key_name] = {
                    "label": cfg["label"],
                    "used_calls": used_calls,
                    "rpd_limit": rpd_limit,
                    "remaining_calls": remaining_calls,
                    "pct_used": round((used_calls / rpd_limit) * 100, 1) if rpd_limit else 0,
                    "total_tokens_today": r.sum_tokens
                }

        # Masukkan model penting yang belum dipanggil hari ini (0 used)
        for m, cfg in LIMITS.items():
            if m not in quota_data:
                rpd_limit = cfg.get("rpd_limit", 500)
                quota_data[m] = {
                    "label": cfg["label"],
                    "used_calls": 0,
                    "rpd_limit": rpd_limit,
                    "remaining_calls": rpd_limit,
                    "pct_used": 0.0,
                    "total_tokens_today": 0
                }

        return quota_data

    @staticmethod
    async def get_monthly_expense_summary(session=None) -> Dict[str, Any]:
        """
        Menghitung akumulasi estimasi pengeluaran per provider sejak awal bulan berjalan.
        """
        now = datetime.now(timezone.utc)
        first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async def _query(s):
            stmt = (
                select(
                    TokenUsageLog.provider,
                    func.count(TokenUsageLog.id).label("total_calls"),
                    func.coalesce(func.sum(TokenUsageLog.total_tokens), 0).label("total_tokens"),
                    func.coalesce(func.sum(TokenUsageLog.cached_tokens), 0).label("cached_tokens"),
                    func.coalesce(func.sum(TokenUsageLog.cost_estimate), 0.0).label("total_cost")
                )
                .where(TokenUsageLog.timestamp >= first_day_of_month)
                .group_by(TokenUsageLog.provider)
            )
            return (await s.execute(stmt)).all()

        if session:
            rows = await _query(session)
        else:
            async with get_session() as s:
                rows = await _query(s)

        expenses = {}
        total_month_usd = 0.0
        total_month_calls = 0

        for r in rows:
            prov = str(r.provider).lower()
            cost = float(r.total_cost or 0.0)
            total_month_usd += cost
            total_month_calls += r.total_calls
            expenses[prov] = {
                "calls": r.total_calls,
                "tokens": r.total_tokens,
                "cached_tokens": r.cached_tokens,
                "cost_usd": round(cost, 4)
            }

        return {
            "month_str": now.strftime("%B %Y"),
            "total_month_usd": round(total_month_usd, 4),
            "total_month_calls": total_month_calls,
            "by_provider": expenses
        }

    @classmethod
    async def get_full_credit_report(cls) -> Dict[str, Any]:
        """
        Mengumpulkan seluruh metrik saldo live, sisa kuota, dan pengeluaran bulan berjalan.
        """
        or_task = cls.fetch_openrouter_credits()
        ds_task = cls.fetch_deepseek_balance()
        quota_task = cls.get_daily_quota_summary()
        expense_task = cls.get_monthly_expense_summary()

        or_res, ds_res, quota_res, expense_res = await asyncio.gather(
            or_task, ds_task, quota_task, expense_task, return_exceptions=True
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "openrouter": or_res if not isinstance(or_res, Exception) else {"status": "error", "message": str(or_res)},
            "deepseek": ds_res if not isinstance(ds_res, Exception) else {"status": "error", "message": str(ds_res)},
            "quotas": quota_res if not isinstance(quota_res, Exception) else {},
            "expenses": expense_res if not isinstance(expense_res, Exception) else {}
        }

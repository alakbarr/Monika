# ==============================================================================
# File: data_sources/eia_oil_inventory.py
# ==============================================================================

"""
Fetcher EIA (U.S. Energy Information Administration) Weekly Oil Inventory.
Data dirilis setiap Rabu ~10:30 AM ET.
API key gratis: https://www.eia.gov/opendata/ (perlu registrasi).
"""
import json
import logging
import os
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.EIAOil")

EIA_URL = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"


class EIAInventoryFetcher:
    """Mengambil data inventaris minyak mentah komersial AS (series WCESTUS1)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.api_key = os.getenv("EIA_API_KEY", "")

    async def fetch(self) -> dict:
        if not self.api_key:
            logger.warning("EIA_API_KEY not set — skipping oil inventory fetch")
            return {"error": "EIA_API_KEY not configured"}

        params = {
            "api_key": self.api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": "WCESTUS1",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 5,
        }

        data = await fetch_with_retry(EIA_URL, params=params, timeout=15)
        if not data or not isinstance(data, dict) or "response" not in data:
            return {"error": "EIA API returned no data"}

        resp_obj = data.get("response")
        if not isinstance(resp_obj, dict):
            return {"error": "EIA API returned invalid response format"}

        records = resp_obj.get("data", [])
        if not isinstance(records, list) or not records:
            return {"error": "No inventory records returned"}

        history = []
        for r in records:
            if not isinstance(r, dict):
                continue
            val = r.get("value")
            if val is not None:
                history.append({
                    "period": str(r.get("period", "")),
                    "value_mbbl": round(float(val) / 1000, 2),
                })

        if not history:
            return {"error": "No valid inventory values"}

        wow_change = None
        if len(history) >= 2:
            wow_change = round(history[0]["value_mbbl"] - history[1]["value_mbbl"], 2)

        result = {
            "latest_inventory_mbbl": history[0]["value_mbbl"],
            "latest_period": history[0]["period"],
            "wow_change_mbbl": wow_change,
            "trend": ("build" if wow_change and wow_change > 0
                      else "draw" if wow_change and wow_change < 0
                      else "neutral"),
            "market_signal": (
                "bearish_supply" if wow_change and wow_change > 2 else
                "mildly_bearish" if wow_change and 0 < wow_change <= 2 else
                "bullish_supply" if wow_change and wow_change < -2 else
                "mildly_bullish" if wow_change and -2 <= wow_change < 0 else
                "neutral"
            ),
            "history_5w": history,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        cfg_key = "eia_oil_inventory_latest"
        existing = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == cfg_key).limit(1)
        )).scalar_one_or_none()

        if existing:
            existing.value = json.dumps(result)
        else:
            self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))

        from database.safe_ops import safe_commit
        await safe_commit(self.session, label="EIAOil")
        logger.info(f"EIA Oil: {result['latest_inventory_mbbl']}M bbl "
                    f"(WoW: {wow_change:+.2f}M — {result['trend']})")
        return result

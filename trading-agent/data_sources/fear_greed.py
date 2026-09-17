# ==============================================================================
# File: data_sources/fear_greed.py
# ==============================================================================

"""
Fetcher Fear & Greed Index dari API alternative.me.
API gratis, tanpa perlu autentikasi.
Mewakili sentimen pasar kripto umum dan spesifik BTC.
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.FearGreed")

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=7"


class FearGreedFetcher:
    """Mengambil Fear & Greed Index dan menyimpannya ke SystemConfig."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch(self) -> dict:
        data = await fetch_with_retry(FEAR_GREED_URL, timeout=10)
        if not data or not isinstance(data, dict) or "data" not in data:
            logger.warning("Fear & Greed API returned no data")
            return {"error": "Fear & Greed API returned no data"}

        items = data.get("data")
        if not isinstance(items, list):
            logger.warning("Fear & Greed API returned invalid data format")
            return {"error": "Fear & Greed API returned invalid data format"}

        history = []
        for d in items[:7]:
            if not isinstance(d, dict):
                continue
            history.append({
                "value": int(d.get("value", 0)),
                "classification": str(d.get("value_classification", "Unknown")),
                "timestamp": str(d.get("timestamp", "")),
            })

        if not history:
            return {"error": "Fear & Greed API empty history"}

        latest = history[0]
        wow_change = (history[0]["value"] - history[6]["value"]) if len(history) >= 7 else None

        result = {
            "current_value": latest["value"],
            "classification": latest["classification"],
            "wow_change": wow_change,
            "history_7d": history,
            "interpretation": self._interpret(latest["value"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        cfg_key = "fear_greed_latest"
        existing = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == cfg_key).limit(1)
        )).scalar_one_or_none()

        if existing:
            existing.value = json.dumps(result)
        else:
            self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))

        from database.safe_ops import safe_commit
        await safe_commit(self.session, label="FearGreed")
        logger.info(f"Fear & Greed: {latest['value']} ({latest['classification']})")
        return result

    @staticmethod
    def _interpret(value: int) -> str:
        if value <= 25:
            return "Extreme Fear — potential contrarian buy zone"
        elif value <= 45:
            return "Fear — cautious risk-off sentiment"
        elif value <= 55:
            return "Neutral — no strong sentiment bias"
        elif value <= 75:
            return "Greed — risk-on, watch for exhaustion"
        else:
            return "Extreme Greed — elevated reversal risk"

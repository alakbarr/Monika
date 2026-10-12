# ==============================================================================
# File: data_sources/prediction_market.py
# Monika Prediction Market Intelligence Fetcher (Polymarket Gamma & CLOB API)
# ==============================================================================

"""
Prediction Market Intelligence Ingestion Engine.

Fetches decentralized market-implied odds for macroeconomic and geopolitical catalysts
(e.g., Fed FOMC rate decisions, ECB/BOE policy, US CPI inflation, geopolitical risks,
energy supply shocks) via Polymarket public APIs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SystemConfig
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.DataSources.PredictionMarket")

GAMMA_API_URL = "https://gamma-api.polymarket.com/events"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"

DEFAULT_MACRO_QUERIES = [
    "Fed",
    "FOMC",
    "interest rate",
    "recession",
    "inflation",
    "CPI",
    "tariff",
    "crude oil",
]


class PredictionMarketClient:
    """Consumes decentralized prediction market odds for quantitative macro context."""

    def __init__(self, session: Optional[AsyncSession] = None, timeout: int = 10) -> None:
        self.session = session
        self.timeout = timeout

    async def fetch_macro_events(
        self,
        tags: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Queries Polymarket Gamma API for active macro events.
        """
        params = f"?limit={limit}&active=true&closed=false"
        url = f"{GAMMA_API_URL}{params}"
        data = await fetch_with_retry(url, timeout=self.timeout)
        if not data or not isinstance(data, list):
            logger.warning("Gamma API returned no event data or unexpected format")
            return []

        macro_events = []
        queries = [q.lower() for q in (tags or DEFAULT_MACRO_QUERIES)]

        for event in data:
            if not isinstance(event, dict):
                continue
            title = str(event.get("title", "")).lower()
            description = str(event.get("description", "")).lower()
            
            # Check relevance against macro query terms
            if any(q in title or q in description for q in queries):
                markets = event.get("markets", [])
                parsed_markets = []
                for m in markets:
                    if not isinstance(m, dict):
                        continue
                    parsed_markets.append(self._parse_market(m))

                macro_events.append({
                    "id": event.get("id"),
                    "title": event.get("title"),
                    "category": event.get("category", "Macro"),
                    "volume": float(event.get("volume", 0.0) or 0.0),
                    "liquidity": float(event.get("liquidity", 0.0) or 0.0),
                    "end_date": event.get("endDate"),
                    "markets": parsed_markets,
                })

        return macro_events

    def _parse_market(self, market: dict[str, Any]) -> dict[str, Any]:
        """Parses individual market token within an event."""
        # Outcome prices are JSON encoded strings or arrays in Gamma API
        outcome_prices = market.get("outcomePrices")
        yes_prob: Optional[float] = None
        no_prob: Optional[float] = None

        if outcome_prices:
            try:
                if isinstance(outcome_prices, str):
                    prices = json.loads(outcome_prices)
                else:
                    prices = list(outcome_prices)
                if len(prices) >= 2:
                    yes_prob = round(float(prices[0]), 4)
                    no_prob = round(float(prices[1]), 4)
            except Exception:
                pass

        if yes_prob is None and market.get("lastTradePrice") is not None:
            try:
                yes_prob = round(float(market["lastTradePrice"]), 4)
                no_prob = round(1.0 - yes_prob, 4)
            except Exception:
                pass

        clob_token_ids = market.get("clobTokenIds")
        token_id = ""
        if clob_token_ids:
            try:
                if isinstance(clob_token_ids, str):
                    parsed_tokens = json.loads(clob_token_ids)
                else:
                    parsed_tokens = list(clob_token_ids)
                if parsed_tokens:
                    token_id = str(parsed_tokens[0])
            except Exception:
                pass

        return {
            "id": market.get("id"),
            "question": market.get("question"),
            "yes_probability": yes_prob,
            "no_probability": no_prob,
            "token_id": token_id,
            "volume_24h": float(market.get("volume24hr", 0.0) or 0.0),
            "clob_active": market.get("acceptingOrders", True),
        }

    async def fetch_clob_orderbook(self, token_id: str) -> dict[str, Any]:
        """
        Fetches orderbook depth and spread from CLOB API for a specific token.
        """
        if not token_id:
            return {"error": "Missing token_id"}

        url = f"{CLOB_BOOK_URL}?token_id={token_id}"
        data = await fetch_with_retry(url, timeout=self.timeout)
        if not data or not isinstance(data, dict):
            return {"error": "CLOB API returned no orderbook"}

        bids = data.get("bids", [])
        asks = data.get("asks", [])
        best_bid = float(bids[0]["price"]) if bids else None
        best_ask = float(asks[0]["price"]) if asks else None
        spread = round(best_ask - best_bid, 4) if (best_bid is not None and best_ask is not None) else None

        return {
            "token_id": token_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "bid_depth": len(bids),
            "ask_depth": len(asks),
        }

    async def ingest_and_persist(self) -> dict[str, Any]:
        """
        Full macro ingestion pipeline: fetches, parses, classifies macro bias,
        and saves snapshot to SystemConfig database.
        """
        events = await self.fetch_macro_events()
        fed_rates = []
        geopolitics = []
        inflation_data = []

        for ev in events:
            title_lower = ev["title"].lower()
            for mkt in ev.get("markets", []):
                q = mkt.get("question", "")
                prob = mkt.get("yes_probability")
                if prob is None:
                    continue

                item = {
                    "event": ev["title"],
                    "question": q,
                    "probability": prob,
                    "volume": mkt.get("volume_24h", 0.0),
                }

                if "fed" in title_lower or "interest rate" in title_lower or "fomc" in title_lower:
                    fed_rates.append(item)
                elif "cpi" in title_lower or "inflation" in title_lower:
                    inflation_data.append(item)
                elif "tariff" in title_lower or "war" in title_lower or "oil" in title_lower:
                    geopolitics.append(item)

        # Macro risk sentiment heuristic
        # If rate cut expectations or low inflation odds are strong -> Risk-On (+), else Risk-Off (-)
        sentiment_bias = "NEUTRAL"
        if geopolitics:
            high_risk_geo = [g for g in geopolitics if g["probability"] > 0.50]
            if high_risk_geo:
                sentiment_bias = "RISK_OFF"

        result = {
            "source": "Polymarket",
            "events_count": len(events),
            "fed_rate_odds": fed_rates,
            "inflation_odds": inflation_data,
            "geopolitics_odds": geopolitics,
            "sentiment_bias": sentiment_bias,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.session is not None:
            cfg_key = "prediction_market_latest"
            existing = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key).limit(1)
            )).scalar_one_or_none()

            payload = json.dumps(result)
            if existing:
                existing.value = payload
            else:
                self.session.add(SystemConfig(key=cfg_key, value=payload))

            from database.safe_ops import safe_commit
            await safe_commit(self.session, label="PredictionMarket")
            logger.info(f"Ingested {len(events)} macro events from Polymarket (Bias={sentiment_bias})")

        return result

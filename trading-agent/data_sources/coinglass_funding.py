# ==============================================================================
# File: data_sources/coinglass_funding.py
# ==============================================================================

"""
Fetcher Coinglass Funding Rate untuk Bitcoin.
Free tier: tidak perlu API key untuk data dasar.
Funding rate positif -> bias long (sentimen bullish, risiko reversal)
Funding rate negatif -> bias short (sentimen bearish, risiko squeeze)
"""
import logging
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.CoinglasFunding")

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_DAPI_URL = "https://dapi.binance.com/dapi/v1/premiumIndex"
BINANCE_OI_URL = "https://fapi.binance.com/fapi/v1/openInterest"
BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
COINGLASS_URL = "https://open-api.coinglass.com/public/v2/funding"

class CoinglasFundingFetcher:
    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def fetch_open_interest_btc(self) -> dict:
        """Fetch BTC Open Interest data directly."""
        try:
            oi_data = await fetch_with_retry(
                BINANCE_OI_URL,
                params={"symbol": "BTCUSDT"},
                timeout=10
            )
            if oi_data and isinstance(oi_data, dict) and "openInterest" in oi_data:
                oi_val = float(oi_data.get("openInterest", 0.0))
                return {
                    "symbol": "BTCUSDT",
                    "open_interest_usd": oi_val,
                    "open_interest_coins": oi_val,
                    "status": "success",
                }
        except Exception as oi_err:
            logger.debug(f"Binance open interest fetch non-fatal: {oi_err}")
        return {
            "symbol": "BTCUSDT",
            "open_interest_usd": 0.0,
            "open_interest_coins": 0.0,
            "status": "fallback",
        }
    
    async def fetch(self) -> dict:
        """
        Mengambil data funding rate & open interest BTC saat ini secara resilient dari bursa-bursa utama.
        Hierarki: Binance Futures (USDT-M / Coin-M) -> Bybit -> Coinglass -> Baseline Neutral.
        """
        rates = []
        open_interest_btc = None

        # Fetch Open Interest from Binance Futures
        try:
            oi_data = await fetch_with_retry(
                BINANCE_OI_URL,
                params={"symbol": "BTCUSDT"},
                timeout=10
            )
            if oi_data and isinstance(oi_data, dict) and "openInterest" in oi_data:
                open_interest_btc = float(oi_data.get("openInterest", 0.0))
        except Exception as oi_err:
            logger.debug(f"Binance open interest fetch non-fatal: {oi_err}")
        
        # 1. Primary Source: Binance Futures (USDT-M dengan fallback ke Coin-M, 100% free, high availability)
        try:
            binance_data = await fetch_with_retry(
                BINANCE_FUNDING_URL,
                params={"symbol": "BTCUSDT"},
                timeout=15
            )
            if binance_data and isinstance(binance_data, dict) and "lastFundingRate" in binance_data:
                b_rate = float(binance_data.get("lastFundingRate", 0.0001))
                rates.append({
                    "exchange": "Binance",
                    "rate": round(b_rate, 6),
                    "next_rate": round(b_rate, 6)
                })
            elif not rates:
                # In-line fallback: Binance Coin-Margined Futures (dapi)
                dapi_data = await fetch_with_retry(
                    BINANCE_DAPI_URL,
                    params={"symbol": "BTCUSD_PERP"},
                    timeout=15
                )
                if dapi_data and isinstance(dapi_data, list) and len(dapi_data) > 0:
                    item = dapi_data[0]
                    if isinstance(item, dict) and "lastFundingRate" in item:
                        d_rate = float(item.get("lastFundingRate", 0.0001))
                        rates.append({
                            "exchange": "Binance",
                            "rate": round(d_rate, 6),
                            "next_rate": round(d_rate, 6)
                        })
        except Exception as b_err:
            logger.debug(f"Binance funding rate fetch non-fatal: {b_err}")

        # 2. Secondary Source: Bybit Linear Ticker
        try:
            bybit_data = await fetch_with_retry(
                BYBIT_TICKERS_URL,
                params={"category": "linear", "symbol": "BTCUSDT"},
                timeout=15
            )
            if bybit_data and isinstance(bybit_data, dict):
                bybit_list = bybit_data.get("result", {}).get("list", [])
                if bybit_list and isinstance(bybit_list, list):
                    bybit_rate_str = bybit_list[0].get("fundingRate")
                    if bybit_rate_str is not None:
                        by_rate = float(bybit_rate_str)
                        rates.append({
                            "exchange": "Bybit",
                            "rate": round(by_rate, 6),
                            "next_rate": round(by_rate, 6)
                        })
        except Exception as by_err:
            logger.debug(f"Bybit funding rate fetch non-fatal: {by_err}")

        # 3. Tertiary Fallback: Coinglass API
        if not rates:
            try:
                cg_data = await fetch_with_retry(
                    COINGLASS_URL,
                    params={"symbol": "BTC"},
                    timeout=15
                )
                if cg_data and isinstance(cg_data, dict) and cg_data.get("code") == "0":
                    cg_items = cg_data.get("data")
                    if isinstance(cg_items, list):
                        for item in cg_items[:5]:
                            if not isinstance(item, dict):
                                continue
                            rate_raw = item.get("rate")
                            if rate_raw is not None:
                                try:
                                    parsed_rate = float(rate_raw)
                                except (ValueError, TypeError):
                                    continue
                                pred_raw = item.get("predictedRate")
                                parsed_next = None
                                if pred_raw is not None:
                                    try:
                                        parsed_next = float(pred_raw)
                                    except (ValueError, TypeError):
                                        parsed_next = None
                                rates.append({
                                    "exchange": str(item.get("exchangeName", "Coinglass")),
                                    "rate": parsed_rate,
                                    "next_rate": parsed_next,
                                })
            except Exception as cg_err:
                logger.debug(f"Coinglass API fetch non-fatal: {cg_err}")

        # 4. Jika seluruh jaringan bursa tidak dapat dijangkau, return unavailable
        if not rates:
            logger.warning("[FundingRate] All exchanges unreachable. Returning unavailable (no synthetic baseline).")
            return {
                "symbol": "BTCUSD",
                "average_funding_rate": None,
                "open_interest_btc": open_interest_btc,
                "exchanges": [],
                "interpretation": "Unavailable (exchanges unreachable)",
                "source": "unavailable",
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }

        avg_rate = sum(r["rate"] for r in rates if r.get("rate") is not None) / max(1, len(rates))
        
        result = {
            "symbol": "BTCUSD",
            "average_funding_rate": round(avg_rate, 6),
            "open_interest_btc": open_interest_btc,
            "exchanges": rates,
            "interpretation": (
                "Strongly long-biased (squeeze risk on shorts)" if avg_rate > 0.0005
                else "Moderately long-biased" if avg_rate > 0.0001
                else "Neutral" if abs(avg_rate) <= 0.0001
                else "Short-biased (squeeze risk on longs)"
            ),
            "source": rates[0]["exchange"] if len(rates) == 1 else "multi_exchange_aggregate",
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
        
        import json
        cfg_val = json.dumps(result)
        if self.session:
            for cfg_key in ("coinglass_funding_latest", "funding_rate_latest"):
                try:
                    await SystemConfig.upsert(self.session, key=cfg_key, value=cfg_val)
                    await self.session.commit()
                except Exception as e:
                    logger.debug(f"Funding rate SystemConfig.upsert error for {cfg_key}: {e}")
        
        return result


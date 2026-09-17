# ==============================================================================
# File: scrapers/sentiment/binance_sentiment.py
# ==============================================================================

"""
Binance Futures Global Long/Short Ratio — Data posisi trader ritel/pasar.
API Gratis: https://fapi.binance.com/futures/data/globalLongShortAccountRatio
Berguna untuk sentimen Kripto (BTCUSDT, ETHUSDT) sebagai proksi sentimen risiko.
"""
import logging
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.BinanceSentiment")

class BinanceSentimentFetcher:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
        self.symbols = ["BTCUSDT", "ETHUSDT"]
        self.period = "1d"
        
    async def fetch(self) -> dict:
        """Mengambil sentimen ritel (rasio long/short) dari Binance."""
        result = {"error": "API request failed or data unavailable"}
        ratios = {}
        
        try:
            logger.info("Fetching Binance Global Long/Short Ratio...")
            
            for symbol in self.symbols:
                params = {
                    "symbol": symbol,
                    "period": self.period,
                    "limit": 1
                }
                
                data = await fetch_with_retry(self.url, params=params, timeout=10)
                
                if data and isinstance(data, list) and len(data) > 0:
                    latest = data[-1]
                    ratios[symbol] = {
                        "long_percent": float(latest.get("longAccount", 0)) * 100,
                        "short_percent": float(latest.get("shortAccount", 0)) * 100,
                        "long_short_ratio": float(latest.get("longShortRatio", 0))
                    }
                else:
                    logger.warning(f"No valid data returned for {symbol}")
                    
            if not ratios:
                result = {"error": "No retail sentiment data could be extracted from Binance API"}
            else:
                result = {
                    "source": "binance_futures",
                    "ratios": ratios,
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                }

        except Exception as e:
            logger.error(f"Error fetching Binance Sentiment: {e}")
            result = {"error": str(e)}
            
        # Simpan ke DB jika session tersedia
        if self.session:
            cfg_key = "binance_sentiment_latest"
            existing = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key)
            )).scalar_one_or_none()
            
            if existing:
                existing.value = json.dumps(result)
            else:
                self.session.add(SystemConfig(key=cfg_key, value=json.dumps(result)))
            await self.session.commit()
        
        return result

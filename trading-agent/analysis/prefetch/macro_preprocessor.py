# ==============================================================================
# File: analysis/prefetch/macro_preprocessor.py
# ==============================================================================

"""
Modul Macro Preprocessor.

Melakukan komputasi awal (pre-compute) dan peringkasan data mentah makro (COT, Kejutan Ekonomi, Positioning)
menggunakan model LLM terkonfigurasi. Bertujuan menekan jumlah token input dan mempermudah beban analisis tahap berikutnya.
"""

import collections
import hashlib
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.providers.llm_factory import get_client_for_task
from database.models import COTReport, TechnicalIndicator, EconomicCalendar, SystemConfig
import utils.clock as clock

logger = logging.getLogger("TradingAgent.MacroPreprocessor")

_PREPROCESSOR_CACHE = collections.OrderedDict()
_GEMINI_CACHE = _PREPROCESSOR_CACHE  # Backward compatibility alias
_MAX_CACHE_SIZE = 100

MARKET_CODE_TO_SYMBOL = {
    '088691': 'XAUUSD',
    '099741': 'EURUSD',
    '096742': 'GBPUSD',
    '097741': 'USDJPY',
    '232741': 'AUDUSD',
    '067651': 'XTIUSD',
}

SYMBOL_USD_DIRECTION = {
    'XAUUSD': {'bullish': 'USD_WEAK', 'bearish': 'USD_STRONG'},
    'EURUSD': {'bullish': 'USD_WEAK', 'bearish': 'USD_STRONG'},
    'GBPUSD': {'bullish': 'USD_WEAK', 'bearish': 'USD_STRONG'},
    'USDJPY': {'bullish': 'USD_STRONG', 'bearish': 'USD_WEAK'},
    'AUDUSD': {'bullish': 'USD_WEAK', 'bearish': 'USD_STRONG'},
    'XTIUSD': {'bullish': 'USD_WEAK', 'bearish': 'USD_STRONG'},
}


import hashlib

def _check_cache(prompt: str) -> Optional[dict]:
    key = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if key in _PREPROCESSOR_CACHE:
        ts, result = _PREPROCESSOR_CACHE[key]
        if (datetime.now(timezone.utc) - ts).total_seconds() < 3600:
            _PREPROCESSOR_CACHE.move_to_end(key)
            return result
        else:
            del _PREPROCESSOR_CACHE[key]
    return None


def clear_cache():
    """Clear in-memory preprocessor cache upon breaking news or market shifts."""
    _PREPROCESSOR_CACHE.clear()


def _set_cache(prompt: str, result: dict):
    key = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    _PREPROCESSOR_CACHE[key] = (datetime.now(timezone.utc), result)
    _PREPROCESSOR_CACHE.move_to_end(key)
    if len(_PREPROCESSOR_CACHE) > _MAX_CACHE_SIZE:
        _PREPROCESSOR_CACHE.popitem(last=False)

def clear_macro_cache():
    """Invalidate all cached macro preprocessor outputs on breaking news."""
    _PREPROCESSOR_CACHE.clear()


class MacroPreprocessor:
    def __init__(self, api_key: Optional[str] = None, settings: Optional[dict] = None):
        self.settings: dict = settings or {}
        # Menggunakan LLMFactory untuk precompute
        self.client = get_client_for_task("cot_precompute", self.settings)
        self.client_low = get_client_for_task("cot_precompute", self.settings)

    async def _validate_cot_signals_against_price(
        self,
        session: AsyncSession,
        cot_signals: dict
    ) -> dict:
        """
        Cross-validate COT interpretation against actual price momentum.
        
        If COT says 'bullish' but 5-day price change is strongly bearish,
        mark the signal as LOW CONFIDENCE rather than blocking it entirely.
        """
        from database.models import PriceOHLCV
        from sqlalchemy import select

        validated = {}
        SIGNIFICANT_MOVE_PCT = 0.005  # 0.5% move over 5 days = significant

        for market_code, signal in cot_signals.items():
            if not isinstance(signal, dict):
                validated[market_code] = signal
                continue

            symbol = MARKET_CODE_TO_SYMBOL.get(market_code)
            if not symbol:
                validated[market_code] = signal
                continue

            # Get 5-day price direction
            bars = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == 'D1')
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(5)
            )).scalars().all()

            if len(bars) < 3:
                validated[market_code] = {**signal, '_confidence': 'unverified'}
                continue

            bars = list(reversed(bars))
            price_change_pct = (bars[-1].close - bars[0].close) / bars[0].close

            if abs(price_change_pct) < SIGNIFICANT_MOVE_PCT:
                validated[market_code] = {**signal, '_confidence': 'high'}
                continue

            price_direction = 'bullish' if price_change_pct > 0 else 'bearish'
            signal_direction = signal.get('signal', 'neutral')
            
            cot_usd = SYMBOL_USD_DIRECTION.get(symbol, {}).get(signal_direction, 'unknown')
            price_usd = SYMBOL_USD_DIRECTION.get(symbol, {}).get(price_direction, 'unknown')

            if cot_usd != 'unknown' and price_usd != 'unknown' and cot_usd != price_usd:
                logger.warning(
                    f"[MacroPreprocessor] COT signal for {symbol} ({market_code}) "
                    f"implies {cot_usd} but price action ({price_change_pct:+.2%}) implies {price_usd}. "
                    f"Marking signal as LOW CONFIDENCE."
                )
                validated[market_code] = {
                    **signal,
                    '_confidence': 'low',
                    '_conflict': True,
                    '_conflict_detail': (
                        f"COT implies {cot_usd} but {symbol} 5-day price "
                        f"implies {price_usd} ({price_change_pct:+.2%})"
                    )
                }
            else:
                validated[market_code] = {**signal, '_confidence': 'high'}

        return validated

    async def _synthesize_cot_narrative(self, cot_signals: dict) -> str:
        """Membuat ringkasan naratif 2-3 kalimat dari data COT terkomputasi."""
        if not cot_signals:
            return ''
        try:
            prompt = (
                f"Computed COT (Commitment of Traders) data:\n{json.dumps(cot_signals)}\n\n"
                f"Produce a concise 2-3 sentence summary of current institutional positioning "
                f"across markets, highlighting extreme/overcrowded positions and their implications for reversal risk. "
                f"Do not invent new figures, synthesize strictly from the data above."
            )
            narrative = await self.client.generate_content(
                system_prompt='You are a concise institutional positioning analyst.',
                user_message=prompt
            )
            if isinstance(narrative, str):
                return narrative
            return ''
        except Exception as e:
            logger.debug(f'COT narrative synthesis failed (non-fatal): {e}')
            return ''

    async def compute_cot_signals(self, session: AsyncSession) -> dict:
        """Menghitung posisi net COT secara deterministik."""
        from sqlalchemy import select, desc
        from collections import defaultdict
        
        q = select(COTReport).order_by(COTReport.market_code, desc(COTReport.report_date))
        reports = (await session.execute(q)).scalars().all()
        
        if not reports:
            return {}
            
        history_by_market = defaultdict(list)
        for r in reports:
            if len(history_by_market[r.market_code]) < 4:
                history_by_market[r.market_code].append(r)
                
        result = {}
        for m_code, reps in history_by_market.items():
            if not reps:
                continue
                
            reps.sort(key=lambda x: x.report_date)  # Chronological
            latest = reps[-1]
            
            asset_mgr_net = latest.asset_mgr_long - latest.asset_mgr_short
            leveraged_net = latest.leveraged_long - latest.leveraged_short
            
            total_lev = latest.leveraged_long + latest.leveraged_short
            lev_long_pct = (latest.leveraged_long / total_lev * 100) if total_lev > 0 else 50.0
            
            # 4wk avg
            lev_nets = [r.leveraged_long - r.leveraged_short for r in reps]
            lev_net_4wk_avg = sum(lev_nets) / len(lev_nets)
            
            # Trends
            if len(lev_nets) >= 2:
                recent_change = lev_nets[-1] - lev_nets[-2]
                if recent_change > 1000:
                    trend = 'getting_more_bullish'
                elif recent_change < -1000:
                    trend = 'getting_more_bearish'
                else:
                    trend = 'flat'
            else:
                recent_change = 0
                trend = 'flat'
            
            trend_strength = min(10, max(1, abs(recent_change) // 2000 + 1)) if len(lev_nets) >= 2 else 1
            
            # Thresholds
            symbol = MARKET_CODE_TO_SYMBOL.get(m_code, '')
            ext_long_th = 85.0
            ext_short_th = 15.0
            if symbol in ('USDJPY', 'EURUSD'):
                ext_long_th = 80.0
                ext_short_th = 20.0
                
            flag = 'none'
            if lev_long_pct > ext_long_th:
                flag = 'extreme_long'
            elif lev_long_pct < ext_short_th:
                flag = 'extreme_short'
                
            signal = 'neutral'
            if lev_long_pct > 60.0:
                signal = 'bullish'
            elif lev_long_pct < 40.0:
                signal = 'bearish'
                
            cot_entry = {
                "asset_mgr_net": asset_mgr_net,
                "leveraged_net": leveraged_net,
                "leveraged_net_4wk_avg": int(lev_net_4wk_avg),
                "signal": signal,
                "flag": flag,
                "trend": trend,
                "trend_strength": int(trend_strength),
                "market_code": m_code,
                "symbol": symbol,
            }
            result[m_code] = cot_entry
            if symbol:
                sym_entry = dict(cot_entry)
                # Invert for USDJPY since CME 097741 is JPY futures (Long JPY = Bearish USDJPY)
                if symbol == 'USDJPY':
                    if signal == 'bullish':
                        sym_entry['signal'] = 'bearish'
                    elif signal == 'bearish':
                        sym_entry['signal'] = 'bullish'
                    if flag == 'extreme_long':
                        sym_entry['flag'] = 'extreme_short'
                    elif flag == 'extreme_short':
                        sym_entry['flag'] = 'extreme_long'
                    sym_entry['pair_signal'] = sym_entry['signal']
                result[symbol] = sym_entry
            
        return result

    async def compute_surprise_summary(self, session: AsyncSession) -> dict:
        """Mengagregasi sentimen kalender ekonomi (surprise score) secara deterministik."""
        two_weeks_ago = clock.now() - timedelta(days=14)
        
        q = select(EconomicCalendar).where(
            EconomicCalendar.event_time >= two_weeks_ago,
            EconomicCalendar.surprise_score != None
        )
        events = (await session.execute(q)).scalars().all()
        
        if not events:
            return {}
            
        currency_scores = {}
        for e in events:
            cur = e.currency
            if cur not in currency_scores:
                currency_scores[cur] = 0.0
            
            # Simple weighting based on impact
            weight = 1.0
            if e.impact == 'high':
                weight = 2.0
            elif e.impact == 'low':
                weight = 0.5
            
            currency_scores[cur] += float(e.surprise_score or 0.0) * weight
            
        result = {}
        for cur, score in currency_scores.items():
            if score > 2.0:
                trend = 'positive'
                label = 'data_beating_expectations'
            elif score < -2.0:
                trend = 'negative'
                label = 'data_missing_expectations'
            else:
                trend = 'neutral'
                label = 'data_mixed'
                
            result[cur] = {
                'score': round(score, 2),
                'trend': trend,
                'label': label
            }
            
        return result

    async def run_all_and_save(self, session: AsyncSession, symbols: Optional[list[str]] = None, timeframes: Optional[list[str]] = None):
        """Menjalankan seluruh rutin pre-komputasi dan menyimpannya di DB (SystemConfig)."""
        logger.info("Running Macro pre-computations...")
        
        # Periksa apakah data COT berubah sejak pra-komputasi terakhir
        should_recompute_cot = await self._should_recompute_cot(session)
        
        if should_recompute_cot:
            try:
                cot = await self.compute_cot_signals(session)
                if self.settings and self.settings.get('ssvp', {}).get('validate_precomputed_signals', True):
                    if cot:
                        cot = await self._validate_cot_signals_against_price(session, cot)
                        logger.info('COT signals validated against price action')
                logger.info("COT signals recomputed (data changed)")
            except Exception as e:
                logger.error(f"Macro pre-computation (COT) failed: {e}")
                cot = {}
        else:
            # Gunakan ulang sinyal COT dari komputasi sebelumnya
            existing_cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"]))
            )).scalars().first()
            existing_data = {}
            if existing_cfg and existing_cfg.value:
                try:
                    existing_data = json.loads(existing_cfg.value)
                except Exception:
                    pass
            cot = existing_data.get("cot_signals", {})
            logger.info("COT signals reused (no COT data change since last precompute)")
        
        # Update summary ekonomi hanya jika ada event baru yang terskor
        should_recompute_surprise = await self._should_recompute_surprise(session)
        if should_recompute_surprise:
            try:
                surprises = await self.compute_surprise_summary(session)
                logger.info("Surprise summary recomputed")
            except Exception as e:
                logger.error(f"Macro pre-computation (Surprise) failed: {e}")
                surprises = {}
        else:
            existing_cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"]))
            )).scalars().first()
            existing_data = {}
            if existing_cfg and existing_cfg.value:
                try:
                    existing_data = json.loads(existing_cfg.value)
                except Exception:
                    pass
            surprises = existing_data.get("surprise_summary", {})
            logger.info("Surprise summary reused (no new surprise scores)")
        
        # === SANITY CHECK COT SIGNALS ===
        if cot:
            for market_code, signal_data in cot.items():
                if not isinstance(signal_data, dict):
                    continue
                signal = signal_data.get('signal', '')
                if signal not in ('bullish', 'bearish', 'neutral', 'extreme_long', 'extreme_short'):
                    logger.warning(
                        f'Macro COT signal for {market_code} has unexpected value: {signal}. '
                        f'Setting to neutral.'
                    )
                    cot[market_code]['signal'] = 'neutral'
                    cot[market_code]['_quality'] = 'corrected'
        
        cot_narrative = await self._synthesize_cot_narrative(cot) if cot else ''
        combined = {
            "cot_signals": cot,
            "surprise_summary": surprises,
            "cot_narrative": cot_narrative,
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
        
        payload_str = json.dumps(combined)
        for key in ("llm_preprocessed_latest", "gemini_preprocessed_latest"):
            cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
            if cfg:
                cfg.value = payload_str
            else:
                session.add(SystemConfig(key=key, value=payload_str))
        await session.commit()
        logger.info("Macro pre-computations saved.")

    async def _should_recompute_cot(self, session: AsyncSession) -> bool:
        """Cek apakah data COT ter-update sejak pre-komputasi terakhir."""
        latest_cot_date = (await session.execute(
            select(func.max(COTReport.report_date))
        )).scalar_one_or_none()
        
        if not latest_cot_date:
            return True
        
        latest_date_str = str(latest_cot_date.date())
        should_recompute = False

        for last_precompute_key in ("cot_last_report_date", "gemini_cot_last_report_date"):
            last_cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == last_precompute_key)
            )).scalar_one_or_none()
            
            if not last_cfg or not last_cfg.value or last_cfg.value != latest_date_str:
                should_recompute = True
                if not last_cfg:
                    session.add(SystemConfig(key=last_precompute_key, value=latest_date_str))
                else:
                    last_cfg.value = latest_date_str

        if should_recompute:
            await session.commit()
            return True
        
        return False

    async def _should_recompute_surprise(self, session: AsyncSession) -> bool:
        """Cek apakah terdapat data surprise ekonomi baru sejak pre-komputasi terakhir."""
        primary_key = "surprise_last_recompute"
        last_cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == primary_key)
        )).scalar_one_or_none()
        
        now_str = datetime.now(timezone.utc).isoformat()
        if not last_cfg or not last_cfg.value:
            for k in (primary_key, "gemini_surprise_last_recompute"):
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == k))).scalar_one_or_none()
                if not cfg:
                    session.add(SystemConfig(key=k, value=now_str))
                else:
                    cfg.value = now_str
            await session.commit()
            return True
        
        last_time = datetime.fromisoformat(last_cfg.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
            
        new_surprises = (await session.execute(
            select(func.count(EconomicCalendar.id))
            .where(EconomicCalendar.fetched_at > last_time)
            .where(EconomicCalendar.surprise_score.is_not(None))
        )).scalar_one_or_none() or 0
        
        if new_surprises > 0:
            for k in (primary_key, "gemini_surprise_last_recompute"):
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == k))).scalar_one_or_none()
                if cfg:
                    cfg.value = now_str
                else:
                    session.add(SystemConfig(key=k, value=now_str))
            await session.commit()
            return True
        
        return False


# Backward compatibility alias
GeminiPreprocessor = MacroPreprocessor

# ==============================================================================
# File: analysis/tools/handlers/macro_tools.py
# ==============================================================================

"""
Macroeconomic tool handlers and self-registration.
Handles DXY, VIX, FedWatch, yield curves, COT reports, economic calendars,
market sessions, market regimes, funding rates, and economic surprises.
Direct execution without circular trampolines.
"""

import json
import logging
import html as _html
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import (
    EconomicCalendar, TechnicalIndicator, TreasuryYield, BondYieldData,
    InterestRate, FedWatchProbability, CentralBankRateExpectation, COTReport, VIXData, SystemConfig, DXYData
)
from analysis.tools.registry import ToolRegistry, ToolDefinition

logger = logging.getLogger("TradingAgent.Tools.Macro")


def _get_macro_context(args: dict, ctx: dict) -> Tuple[Optional[AsyncSession], Optional[Any], dict]:
    executor = ctx.get("executor")
    session = ctx.get("session") or getattr(executor, "session", None)
    settings = ctx.get("settings") or getattr(executor, "settings", {}) or {}
    return session, executor, settings


async def _safe_execute(session: Optional[AsyncSession], stmt: Any, max_retries: int = 2) -> Any:
    """Execute a query on session, synchronizing with session._session_lock if present and handling transient interface contention."""
    if not session:
        return None
    lock = getattr(session, "_session_lock", None)
    import asyncio as _asyncio
    _cur_task = _asyncio.current_task()
    for attempt in range(max_retries):
        try:
            if lock and getattr(lock, "_owner_task", None) is not _cur_task:
                async with lock:
                    return await session.execute(stmt)
            else:
                # No lock, or current task already holds it (executor reentrancy).
                return await session.execute(stmt)
        except Exception as e:
            err_str = str(e).lower()
            if ("another operation is in progress" in err_str or "cannot perform operation" in err_str) and attempt < max_retries - 1:
                try:
                    await session.rollback()
                except Exception:
                    pass
                import asyncio
                await asyncio.sleep(0.05)
                continue
            raise


async def handle_get_market_session(args: dict, **ctx) -> dict:
    now = clock.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # DST-aware time zones
    tokyo_tz = ZoneInfo("Asia/Tokyo")
    london_tz = ZoneInfo("Europe/London")
    ny_tz = ZoneInfo("America/New_York")

    tokyo_now = now.astimezone(tokyo_tz)
    london_now = now.astimezone(london_tz)
    ny_now = now.astimezone(ny_tz)

    sessions = []
    if 9 <= tokyo_now.hour < 18:
        sessions.append("Tokyo")
    if 8 <= london_now.hour < 16 or (london_now.hour == 16 and london_now.minute <= 30):
        sessions.append("London")
    if 8 <= ny_now.hour < 17:
        sessions.append("New York")

    overlap = "London-NY" if ("London" in sessions and "New York" in sessions) else None
    if not sessions:
        sessions = ["Off-peak"]

    return {
        "utc_time": now.strftime("%H:%M UTC"),
        "active_sessions": sessions,
        "overlap": overlap,
        "highest_liquidity": overlap is not None,
        "local_times": {
            "Tokyo": tokyo_now.strftime("%H:%M JST"),
            "London": london_now.strftime("%H:%M %Z"),
            "New_York": ny_now.strftime("%H:%M %Z"),
        },
        "recommendation": (
            "Highest volatility and liquidity — prefer breakout / trend continuation strategies" if overlap
            else f"Active {'/'.join(sessions)} session liquidity"
        )
    }


async def handle_get_volatility_regime(args: dict, **ctx) -> dict:
    """Per-symbol volatility/regime classification (consumed by Stage2 prefetcher and specialist pipeline)."""
    session, _, settings = _get_macro_context(args, ctx)
    symbol = args.get("symbol", "")
    if not session:
        return {"error": "Database session required for get_volatility_regime"}
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    try:
        from analysis.calculators.regime_classifier import classify_market_regime
        return await classify_market_regime(session, symbol, settings)
    except Exception as e:
        logger.warning(f"get_volatility_regime failed for {symbol}: {e}")
        return {"error": f"volatility regime calculation failed: {str(e)[:200]}"}


async def handle_get_macro_bias_score(args: dict, **ctx) -> dict:
    """Macro bias alignment score per symbol (consumed by Stage2 prefetcher)."""
    session, _, settings = _get_macro_context(args, ctx)
    symbol = args.get("symbol", "")
    direction = args.get("direction")
    if not session:
        return {"error": "Database session required for get_macro_bias_score"}
    if not symbol:
        return {"error": "Missing required parameter 'symbol'"}
    try:
        from analysis.calculators.macro_bias_filter import evaluate_macro_alignment
        return await evaluate_macro_alignment(session, symbol, direction, settings)
    except Exception as e:
        logger.warning(f"get_macro_bias_score failed for {symbol}: {e}")
        return {"error": f"macro bias calculation failed: {str(e)[:200]}"}


async def handle_get_market_regime(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_market_regime"}

    symbols_input = args.get("symbols", [])
    if not symbols_input:
        single = args.get("symbol", "")
        if single:
            symbols_input = [single]

    symbols = symbols_input
    timeframe = args.get("timeframe", "D1")

    regimes = {}
    for symbol in symbols:
        adx_row = (await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.indicator_name == "ADX_14")
            .where(TechnicalIndicator.timestamp <= clock.now())
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()

        if not adx_row:
            regimes[symbol] = {
                "regime": "unknown",
                "adx": None,
                "implication": (
                    "ADX data not available. This means technical indicators haven't been computed yet. "
                    "MANDATORY: Use conservative threshold of 9/14 for this cycle. "
                    "Do NOT enter BUY/SELL without exceptional confluence when regime is unknown."
                )
            }
            continue

        try:
            adx_data = json.loads(adx_row.value_json)
            adx_val = adx_data.get("adx", 0) if isinstance(adx_data, dict) else float(adx_data)

            if adx_val > 40:
                regime = "strong_trend"
            elif adx_val > 25:
                regime = "trending"
            elif adx_val > 15:
                regime = "weak_trend"
            else:
                regime = "ranging"

            regimes[symbol] = {
                "regime": regime,
                "adx": round(adx_val, 1),
                "plus_di": adx_data.get("plus_di") if isinstance(adx_data, dict) else None,
                "minus_di": adx_data.get("minus_di") if isinstance(adx_data, dict) else None,
                "trend_direction": (
                    "bullish" if isinstance(adx_data, dict) and
                    adx_data.get("plus_di", 0) > adx_data.get("minus_di", 0) else "bearish"
                ) if adx_val > 20 else "none",
                "implication": (
                    "Strong trend — prefer trend-following. Avoid counter-trend entries."
                    if adx_val > 35 else
                    "Mild trend — SMC setups work well."
                    if adx_val > 20 else
                    "Ranging market — be extra selective. FVG/OB entries prone to fake breakouts."
                )
            }
        except Exception as e:
            regimes[symbol] = {"regime": "unknown", "error": str(e)}

    return {
        "timeframe": timeframe,
        "regimes": regimes,
        "trading_implication": (
            "Trending assets: confirm entry aligns with trend. "
            "Ranging assets: increase confluence threshold by +2 before trading."
        )
    }


async def handle_get_economic_calendar(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"count": 0, "events": [], "status": "no_session"}

    impact_filter = args.get("impact_filter", "high_and_medium")
    currency_filter = args.get("currency_filter", "")
    hours_ahead = args.get("hours_ahead", 48)
    hours_behind = args.get("hours_behind", 24)

    now = clock.now()
    since = now - timedelta(hours=hours_behind)
    until = now + timedelta(hours=hours_ahead)

    query = (
        select(EconomicCalendar)
        .where(EconomicCalendar.event_time >= since)
        .where(EconomicCalendar.event_time <= until)
        .order_by(EconomicCalendar.event_time.asc())
        .limit(100)
    )

    if impact_filter == "high":
        query = query.where(EconomicCalendar.impact == "high")
    elif impact_filter == "medium":
        query = query.where(EconomicCalendar.impact == "medium")
    elif impact_filter == "high_and_medium":
        query = query.where(EconomicCalendar.impact.in_(["high", "medium"]))

    if currency_filter:
        currencies = [c.strip() for c in currency_filter.split(",")]
        query = query.where(EconomicCalendar.currency.in_(currencies))

    rows = (await session.execute(query)).scalars().all()

    def _is_past_event(r_time, curr_now):
        if isinstance(r_time, datetime) and isinstance(curr_now, datetime):
            if r_time.tzinfo is None and curr_now.tzinfo is not None:
                r_time = r_time.replace(tzinfo=timezone.utc)
            elif r_time.tzinfo is not None and curr_now.tzinfo is None:
                curr_now = curr_now.replace(tzinfo=timezone.utc)
            return r_time <= curr_now
        return False

    return {
        "count": len(rows),
        "events": [
            {
                "event_name": f"<untrusted_external_content>{_html.escape(r.event_name or '')}</untrusted_external_content>",
                "currency": r.currency,
                "country": getattr(r, "country", ""),
                "impact": r.impact,
                "actual": r.actual if _is_past_event(r.event_time, now) else None,
                "forecast": r.forecast,
                "previous": r.previous,
                "event_time": r.event_time.isoformat() if r.event_time is not None else None,
            }
            for r in rows
        ],
    }


async def handle_get_economic_surprise(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for economic surprise"}

    currency = args.get("currency", "USD")
    days_back = args.get("days_back", 14)
    since = clock.now() - timedelta(days=days_back)

    query = (
        select(EconomicCalendar)
        .where(EconomicCalendar.currency == currency.upper())
        .where(EconomicCalendar.event_time >= since)
        .where(EconomicCalendar.surprise_score != None)
        .order_by(EconomicCalendar.event_time.desc())
    )
    rows = (await session.execute(query)).scalars().all()

    return {
        "currency": currency.upper(),
        "days_back": days_back,
        "count": len(rows),
        "events": [
            {
                "event_name": f"<untrusted_external_content>{_html.escape(r.event_name or '')}</untrusted_external_content>",
                "event_time": r.event_time.isoformat() if r.event_time is not None else None,
                "impact": r.impact,
                "actual": r.actual,
                "forecast": r.forecast,
                "surprise_score": r.surprise_score,
            }
            for r in rows
        ],
    }


async def handle_get_precomputed_cot_signals(args: dict, **ctx) -> dict:
    session, _, settings = _get_macro_context(args, ctx)
    cot_data = {}
    if session:
        try:
            stmt = select(SystemConfig).where(
                SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"])
            )
            cfg = (await session.execute(stmt)).scalars().first()
            if cfg and cfg.value:
                parsed = json.loads(cfg.value)
                if isinstance(parsed, dict) and "cot_signals" in parsed:
                    cot_data = parsed["cot_signals"]
        except Exception as e:
            logger.debug(f"Failed fetching precomputed COT from SystemConfig: {e}")

        if not cot_data:
            try:
                from analysis.prefetch.macro_preprocessor import MacroPreprocessor
                preprocessor = MacroPreprocessor(settings=settings)
                cot_data = await preprocessor.compute_cot_signals(session)
            except Exception as e:
                logger.warning(f"On-the-fly compute_cot_signals failed: {e}")

    return {
        "status": "success" if cot_data else "empty",
        "cot_signals": cot_data,
        "count": len(cot_data) if isinstance(cot_data, dict) else 0,
    }


async def handle_get_surprise_summary(args: dict, **ctx) -> dict:
    session, _, settings = _get_macro_context(args, ctx)
    surprise_data = {}
    if session:
        try:
            stmt = select(SystemConfig).where(
                SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"])
            )
            cfg = (await session.execute(stmt)).scalars().first()
            if cfg and cfg.value:
                parsed = json.loads(cfg.value)
                if isinstance(parsed, dict) and "surprise_summary" in parsed:
                    surprise_data = parsed["surprise_summary"]
        except Exception as e:
            logger.debug(f"Failed fetching precomputed surprise summary from SystemConfig: {e}")

        if not surprise_data:
            try:
                from analysis.prefetch.macro_preprocessor import MacroPreprocessor
                preprocessor = MacroPreprocessor(settings=settings)
                surprise_data = await preprocessor.compute_surprise_summary(session)
            except Exception as e:
                logger.warning(f"On-the-fly compute_surprise_summary failed: {e}")

    return {
        "status": "success" if surprise_data else "empty",
        "surprise_summary": surprise_data,
        "count": len(surprise_data) if isinstance(surprise_data, dict) else 0,
    }


async def handle_get_treasury_yields(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for treasury yields"}

    days_back = args.get("days_back", 5)
    since = clock.now() - timedelta(days=days_back)
    rows = (await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.tenor, TreasuryYield.date.desc())
    )).scalars().all()

    by_tenor: dict[str, list] = {}
    for r in rows:
        by_tenor.setdefault(r.tenor, []).append({"date": r.date.strftime("%Y-%m-%d"), "yield_pct": r.yield_percent})

    spread = None
    if "2Y" in by_tenor and "10Y" in by_tenor:
        try:
            spread = round(by_tenor["10Y"][0]["yield_pct"] - by_tenor["2Y"][0]["yield_pct"], 3)
        except (IndexError, TypeError):
            pass

    latest_date = None
    for tenor_rows in by_tenor.values():
        if tenor_rows:
            date_val = tenor_rows[0].get("date") if isinstance(tenor_rows[0], dict) else None
            d = None
            if isinstance(date_val, str):
                try:
                    d = datetime.strptime(date_val, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    d = None
            elif isinstance(date_val, datetime):
                d = date_val.replace(tzinfo=timezone.utc) if date_val.tzinfo is None else date_val
            if d is not None and (latest_date is None or d > latest_date):
                latest_date = d

    data_age_hours = round((clock.now() - latest_date).total_seconds() / 3600, 1) if latest_date else None
    return {
        "yields_by_tenor": by_tenor,
        "2y_10y_spread": spread,
        "curve_status": "inverted" if spread is not None and spread < 0 else "normal" if spread is not None and spread > 0 else "unknown",
        "data_age_hours": data_age_hours,
        "staleness_note": f"Data berumur {data_age_hours}h (bisa juga dari cache hingga 6h)." if data_age_hours and data_age_hours > 24 else None,
    }


async def handle_get_bond_yield_spreads(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for bond yield spreads"}

    days_back = args.get("days_back", 10)
    since = clock.now() - timedelta(days=days_back)

    # 1. Ambil US 10Y & 2Y Treasury
    us_10y_rows = (await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.tenor == "10Y", TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.date.desc())
    )).scalars().all()
    us_10y_by_date = {r.date.strftime("%Y-%m-%d"): r.yield_percent for r in us_10y_rows}

    us_2y_rows = (await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.tenor == "2Y", TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.date.desc())
    )).scalars().all()
    us_2y_by_date = {r.date.strftime("%Y-%m-%d"): r.yield_percent for r in us_2y_rows}

    # 2. Ambil yield internasional (10Y dan 2Y)
    intl_since = clock.now() - timedelta(days=max(days_back, 60))
    intl_rows = (await _safe_execute(
        session,
        select(BondYieldData)
        .where(and_(BondYieldData.date >= intl_since, BondYieldData.date <= clock.now()))
        .order_by(BondYieldData.country_tenor, BondYieldData.date.desc())
    )).scalars().all()

    intl_by_country: dict[str, dict[str, float]] = {}
    for r in intl_rows:
        intl_by_country.setdefault(r.country_tenor, {})[r.date.strftime("%Y-%m-%d")] = r.yield_percent

    # Fallback US 2Y jika tidak ada di TreasuryYield tapi ada di BondYieldData
    if not us_2y_by_date and "US_2Y" in intl_by_country:
        us_2y_by_date = dict(intl_by_country["US_2Y"])

    # Helper hitung spread per tenor
    async def _compute_spreads(mapping: dict, us_dict: dict, tenor_suffix: str) -> dict:
        spreads_out = {}
        for code, meta in mapping.items():
            country_yields = dict(intl_by_country.get(code, {}))
            if not country_yields:
                latest_rows = (await _safe_execute(
                    session,
                    select(BondYieldData)
                    .where(BondYieldData.country_tenor == code)
                    .order_by(BondYieldData.date.desc())
                    .limit(5)
                )).scalars().all()
                for r in latest_rows:
                    country_yields[r.date.strftime("%Y-%m-%d")] = r.yield_percent

            common_dates = sorted(set(us_dict.keys()) & set(country_yields.keys()), reverse=True)
            spread_series = []
            if common_dates:
                for dt in common_dates:
                    u_val = us_dict[dt]
                    i_val = country_yields[dt]
                    spread_val = round(u_val - i_val, 3)
                    spread_series.append({"date": dt, f"us_{tenor_suffix}": u_val, f"intl_{tenor_suffix}": i_val, "spread_us_minus_intl": spread_val})
            elif us_dict and country_yields:
                sorted_intl_dates = sorted(country_yields.keys())
                for us_dt in sorted(us_dict.keys(), reverse=True):
                    candidate_dates = [d for d in sorted_intl_dates if d <= us_dt]
                    if candidate_dates:
                        matched_intl_dt = candidate_dates[-1]
                        u_val = us_dict[us_dt]
                        i_val = country_yields[matched_intl_dt]
                        spread_val = round(u_val - i_val, 3)
                        spread_series.append({"date": us_dt, "intl_date": matched_intl_dt, f"us_{tenor_suffix}": u_val, f"intl_{tenor_suffix}": i_val, "spread_us_minus_intl": spread_val})
                if not spread_series:
                    latest_us = next(iter(us_dict.values()))
                    latest_intl = next(iter(country_yields.values()))
                    latest_dt = next(iter(us_dict.keys()))
                    latest_intl_dt = next(iter(country_yields.keys()))
                    spread_series.append({"date": latest_dt, "intl_date": latest_intl_dt, f"us_{tenor_suffix}": latest_us, f"intl_{tenor_suffix}": latest_intl, "spread_us_minus_intl": round(latest_us - latest_intl, 3)})

            latest_spread = spread_series[0]["spread_us_minus_intl"] if spread_series else None
            oldest_spread = spread_series[-1]["spread_us_minus_intl"] if len(spread_series) > 1 else latest_spread

            momentum = "stable"
            if latest_spread is not None and oldest_spread is not None:
                delta = latest_spread - oldest_spread
                if delta > 0.05:
                    momentum = "widening"
                elif delta < -0.05:
                    momentum = "narrowing"

            spreads_out[code] = {
                "country": meta["name"],
                "target_pair": meta["fx_pair"],
                "current_spread": latest_spread,
                "5d_momentum": momentum,
                "fx_macro_implication": meta["direction_impact"],
                "history": spread_series[:5],
            }
        return spreads_out

    # Mapping 10Y (Economic Benchmark)
    COUNTRY_MAPPING_10Y = {
        "DE_10Y": {"name": "Germany (Bund 10Y)", "fx_pair": "EURUSD", "direction_impact": "Widening US-DE spread = Bearish EURUSD, Narrowing = Bullish EURUSD"},
        "UK_10Y": {"name": "United Kingdom (Gilt 10Y)", "fx_pair": "GBPUSD", "direction_impact": "Widening US-UK spread = Bearish GBPUSD, Narrowing = Bullish GBPUSD"},
        "JP_10Y": {"name": "Japan (JGB 10Y)", "fx_pair": "USDJPY", "direction_impact": "Widening US-JP spread = Bullish USDJPY, Narrowing = Bearish USDJPY"},
        "AU_10Y": {"name": "Australia (ACGB 10Y)", "fx_pair": "AUDUSD", "direction_impact": "Widening US-AU spread = Bearish AUDUSD, Narrowing = Bullish AUDUSD"},
    }

    # Mapping 2Y (Short-End Monetary Policy Divergence)
    COUNTRY_MAPPING_2Y = {
        "DE_2Y": {"name": "Germany (Bund 2Y)", "fx_pair": "EURUSD", "direction_impact": "Widening US-DE 2Y spread = Bearish EURUSD (short-end policy advantage to USD)"},
        "UK_2Y": {"name": "United Kingdom (Gilt 2Y)", "fx_pair": "GBPUSD", "direction_impact": "Widening US-UK 2Y spread = Bearish GBPUSD"},
        "JP_2Y": {"name": "Japan (JGB 2Y)", "fx_pair": "USDJPY", "direction_impact": "Widening US-JP 2Y spread = Bullish USDJPY (carry trade funding incentive)"},
        "AU_2Y": {"name": "Australia (ACGB 2Y)", "fx_pair": "AUDUSD", "direction_impact": "Widening US-AU 2Y spread = Bearish AUDUSD"},
    }

    spreads_10y = await _compute_spreads(COUNTRY_MAPPING_10Y, us_10y_by_date, "10y")
    spreads_2y = await _compute_spreads(COUNTRY_MAPPING_2Y, us_2y_by_date, "2y") if us_2y_by_date else {}

    return {
        "days_back": days_back,
        "us_10y_current": next(iter(us_10y_by_date.values()), None),
        "us_2y_current": next(iter(us_2y_by_date.values()), None),
        "yield_spreads_10y": spreads_10y,
        "yield_spreads_2y": spreads_2y,
        "yield_spreads": spreads_10y,  # Backward-compatible alias
        "macro_guidance": (
            "Short-end 2Y spreads drive monetary policy expectations. "
            "10Y benchmark spreads drive long-term capital flows. "
            "Widening US yield advantage = Bearish EURUSD/GBPUSD/AUDUSD, Bullish USDJPY."
        )
    }


async def handle_get_interest_rates(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for interest rates"}

    rows = (await session.execute(
        select(InterestRate)
        .where(InterestRate.effective_date <= clock.now())
        .order_by(InterestRate.bank, InterestRate.effective_date.desc())
    )).scalars().all()

    # Ambil ekspektasi suku bunga terbaru dari CentralBankRateExpectation
    exp_rows = (await session.execute(
        select(CentralBankRateExpectation)
        .order_by(CentralBankRateExpectation.bank, CentralBankRateExpectation.fetched_at.desc(), CentralBankRateExpectation.id.desc())
    )).scalars().all()
    latest_exp = {}
    for er in exp_rows:
        eb = getattr(er, "bank", "").upper()
        if eb and eb not in latest_exp:
            latest_exp[eb] = {
                "meeting_date": getattr(er, "meeting_date", None),
                "current_rate_pct": getattr(er, "current_rate", None),
                "prob_hike": getattr(er, "prob_hike", 0.0),
                "prob_hold": getattr(er, "prob_hold", 0.0),
                "prob_cut": getattr(er, "prob_cut", 0.0),
            }

    seen_banks = set()
    rates = []
    for r in rows:
        bank_name = getattr(r, "bank", None)
        if bank_name and bank_name not in seen_banks:
            seen_banks.add(bank_name)
            eff_dt = getattr(r, "effective_date", None)
            eff_str = eff_dt.strftime("%Y-%m-%d") if eff_dt is not None and hasattr(eff_dt, "strftime") else str(eff_dt or "")
            nxt_dt = getattr(r, "next_meeting_date", None)
            nxt_str = nxt_dt.strftime("%Y-%m-%d") if nxt_dt is not None and hasattr(nxt_dt, "strftime") else (str(nxt_dt) if nxt_dt else None)

            # Jika next_meeting_date kosong, coba lengkapi dari latest_exp
            b_up = bank_name.upper()
            if not nxt_str and b_up in latest_exp:
                nxt_str = latest_exp[b_up].get("meeting_date")

            exp_data = latest_exp.get(b_up)
            rates.append({
                "bank": bank_name,
                "rate_pct": getattr(r, "rate_percent", None),
                "effective_date": eff_str,
                "next_meeting_date": nxt_str,
                "market_expectations": exp_data,
            })

    valid_eff_dates = [r.effective_date for r in rows if isinstance(getattr(r, "effective_date", None), (datetime, date))]
    latest_eff = max(valid_eff_dates, default=None)
    data_age_days = None
    if isinstance(latest_eff, (datetime, date)):
        if isinstance(latest_eff, datetime):
            eff_dt = latest_eff.replace(tzinfo=timezone.utc) if latest_eff.tzinfo is None else latest_eff
        else:
            eff_dt = datetime(latest_eff.year, latest_eff.month, latest_eff.day, tzinfo=timezone.utc)
        now_dt = clock.now()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        data_age_days = (now_dt - eff_dt).days

    # Map bank rates by key for differential computation
    bank_rates = {r["bank"].upper(): r["rate_pct"] for r in rates if r.get("rate_pct") is not None}
    differentials = {}
    if "ECB" in bank_rates and "FED" in bank_rates:
        differentials["EURUSD"] = {
            "base": "EUR (ECB)", "quote": "USD (FED)",
            "spread_pct": round(bank_rates["ECB"] - bank_rates["FED"], 2),
            "advantage": "EUR" if bank_rates["ECB"] > bank_rates["FED"] else "USD"
        }
    if "BOE" in bank_rates and "FED" in bank_rates:
        differentials["GBPUSD"] = {
            "base": "GBP (BOE)", "quote": "USD (FED)",
            "spread_pct": round(bank_rates["BOE"] - bank_rates["FED"], 2),
            "advantage": "GBP" if bank_rates["BOE"] > bank_rates["FED"] else "USD"
        }
    if "RBA" in bank_rates and "FED" in bank_rates:
        differentials["AUDUSD"] = {
            "base": "AUD (RBA)", "quote": "USD (FED)",
            "spread_pct": round(bank_rates["RBA"] - bank_rates["FED"], 2),
            "advantage": "AUD" if bank_rates["RBA"] > bank_rates["FED"] else "USD"
        }
    if "FED" in bank_rates and "BOJ" in bank_rates:
        differentials["USDJPY"] = {
            "base": "USD (FED)", "quote": "JPY (BOJ)",
            "spread_pct": round(bank_rates["FED"] - bank_rates["BOJ"], 2),
            "advantage": "USD",
            "carry_trade_context": "JPY acts as primary funding currency; wide spread incentivizes carry trade until risk-off unwind occurs."
        }

    mandate_profiles = {
        "FED": {"mandate": "Dual (Max Employment + Price Stability 2% Core PCE)", "key_focus": "Core PCE vs NFP/Claims"},
        "ECB": {"mandate": "Single (Price Stability 2% HICP medium-term)", "key_focus": "HICP & Two-Pillar M3 credit"},
        "BOE": {"mandate": "Tiered (Price Stability 2% CPI remit primary; growth secondary)", "key_focus": "MPC voting split & Gilt sensitivity"},
        "BOJ": {"mandate": "Deflation Exit / Sound Economic Development", "key_focus": "Shunto wage growth & Core-core CPI"},
        "RBA": {"mandate": "Triple (2-3% range, Full Employment, Public Welfare)", "key_focus": "Trimmed Mean CPI & Iron Ore terms of trade"}
    }

    return {
        "count": len(rates),
        "rates": rates,
        "rate_differentials": differentials,
        "mandate_profiles": mandate_profiles,
        "data_age_days": data_age_days
    }


async def handle_get_central_bank_expectations(args: dict, **ctx) -> dict:
    """
    Mengembalikan ekspektasi keputusan suku bunga pasar untuk FED, ECB, BOE, BOJ, RBA.
    Mencakup probabilitas Hike %, Hold %, Cut %, tanggal rapat, dan derajat priced-in (1-10).
    """
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for central bank rate expectations"}

    target_bank = (args.get("bank") or "").strip().upper()
    query = select(CentralBankRateExpectation).order_by(
        CentralBankRateExpectation.bank,
        CentralBankRateExpectation.fetched_at.desc(),
        CentralBankRateExpectation.id.desc()
    )
    if target_bank:
        query = query.where(CentralBankRateExpectation.bank == target_bank)

    rows = (await _safe_execute(session, query.limit(50))).scalars().all()
    if not rows:
        return {
            "expectations": {},
            "fallback_tool": "web_search",
            "suggested_queries": {
                "ECB": "ECB rate expectations OIS Euribor futures upcoming meeting",
                "BOE": "Bank of England rate expectations SONIA futures upcoming MPC",
                "BOJ": "Bank of Japan rate expectations OIS TONA upcoming meeting",
                "RBA": "RBA cash rate expectations ASX 30-Day Interbank futures",
            },
            "note": "Belum ada rekaman ekspektasi di database. Jalankan scraper atau gunakan web_search."
        }

    latest_by_bank = {}
    for r in rows:
        b = r.bank.upper()
        if b not in latest_by_bank:
            probs = {
                "hike": float(r.prob_hike or 0.0),
                "hold": float(r.prob_hold or 0.0),
                "cut": float(r.prob_cut or 0.0),
            }
            dom_action = max(probs, key=lambda k: probs[k])
            dom_prob = probs[dom_action]

            # Hitung Priced-In Score (1-10)
            if dom_prob >= 90:
                pi_score = 9; pi_label = "Fully Priced In"
            elif dom_prob >= 75:
                pi_score = 7; pi_label = "Largely Priced In"
            elif dom_prob >= 55:
                pi_score = 5; pi_label = "Partially Priced In"
            elif dom_prob >= 35:
                pi_score = 4; pi_label = "Weakly Priced In"
            else:
                pi_score = 2; pi_label = "NOT Priced In (Surprise Risk)"

            latest_by_bank[b] = {
                "bank": b,
                "current_rate_pct": r.current_rate,
                "next_meeting_date": r.meeting_date,
                "probabilities": probs,
                "dominant_expected_action": dom_action,
                "dominant_probability_pct": dom_prob,
                "priced_in_score": pi_score,
                "priced_in_label": pi_label,
                "source": r.source,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }

    return {
        "count": len(latest_by_bank),
        "expectations": latest_by_bank,
        "interpretation_guide": (
            "Probabilitas > 80% = LARGELY/FULLY PRICED IN (risiko sell-the-news tinggi). "
            "Probabilitas 50-80% = PARTIALLY PRICED IN (moderate uncertainty). "
            "Probabilitas < 50% = NOT PRICED IN (potensi kejutan besar jika terealisasi)."
        )
    }


async def handle_get_fedwatch_probabilities(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {
            "error": "Database session required for fedwatch",
            "fallback_tool": "web_search",
            "suggested_query": "CME FedWatch target rate probabilities upcoming FOMC meeting",
            "note": (
                "Database session tidak tersedia untuk fedwatch. "
                "SARAN TINDAKAN: Gunakan tool 'web_search' dengan kueri: "
                "'CME FedWatch target rate probabilities upcoming FOMC meeting' untuk mendapatkan probabilitas terkini."
            ),
        }

    limit = args.get("limit", 4)
    rows = (await session.execute(
        select(FedWatchProbability)
        .where(FedWatchProbability.fetched_at <= clock.now())
        .order_by(FedWatchProbability.fetched_at.desc(), FedWatchProbability.id.desc())
        .limit(limit * 2)
    )).scalars().all()

    meetings_by_date = {}
    for r in rows:
        if r.meeting_date not in meetings_by_date:
            try:
                probs = json.loads(r.probabilities_json)
            except Exception:
                probs = {"error": "Malformed JSON in database"}
            fetched_tz = r.fetched_at.replace(tzinfo=timezone.utc) if r.fetched_at.tzinfo is None else r.fetched_at
            age_hours = round((clock.now() - fetched_tz).total_seconds() / 3600, 1)
            meetings_by_date[r.meeting_date] = {
                "meeting_date": r.meeting_date,
                "probabilities": probs,
                "fetched_at": r.fetched_at.isoformat(),
                "data_age_hours": age_hours
            }

    meetings = list(meetings_by_date.values())
    meetings.sort(key=lambda m: str(m.get("meeting_date", "")))
    meetings = meetings[:limit]

    result = {
        "count": len(meetings),
        "meetings": meetings,
    }

    if not meetings:
        result["note"] = (
            "Data lokal CME FedWatch tidak tersedia di database. "
            "SARAN TINDAKAN OTOMATIS: Gunakan tool 'web_search' dengan kueri: "
            "'CME FedWatch target rate probabilities upcoming FOMC meeting' atau "
            "'FedWatch tool probabilities' untuk mendapatkan probabilitas terkini."
        )
        result["fallback_tool"] = "web_search"
        result["suggested_query"] = "CME FedWatch target rate probabilities upcoming FOMC meeting"

    return result


async def handle_get_cot_report(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for cot report"}

    market_codes = args.get("market_codes", [])
    query = select(COTReport).where(COTReport.report_date <= clock.now()).order_by(COTReport.market_code, COTReport.report_date.desc())

    if market_codes:
        query = query.where(COTReport.market_code.in_(market_codes))

    rows = (await session.execute(query)).scalars().all()

    seen = set()
    reports = []
    now = clock.now()

    for r in rows:
        if r.market_code not in seen:
            seen.add(r.market_code)
            lev_net = r.leveraged_long - r.leveraged_short
            am_net = r.asset_mgr_long - r.asset_mgr_short

            report_date_tz = r.report_date
            if report_date_tz.tzinfo is None:
                report_date_tz = report_date_tz.replace(tzinfo=timezone.utc)

            days_old = (now - report_date_tz).days

            if days_old <= 3:
                reliability = "high"
                confluence_weight = 1.0
                reliability_note = "Current week data — high confidence"
            elif days_old <= 7:
                reliability = "medium"
                confluence_weight = 0.5
                reliability_note = f"{days_old} days old — secondary confirmation only (weight: 0.5)"
            elif days_old <= 10:
                reliability = "low"
                confluence_weight = 0.1
                reliability_note = f"{days_old} days old — minimal value (weight: 0.1)"
            else:
                reliability = "very_low"
                confluence_weight = 0.0
                reliability_note = f"{days_old} days old — DO NOT use for confluence scoring"

            reports.append({
                "market_code": r.market_code,
                "report_date": r.report_date.strftime("%Y-%m-%d"),
                "days_since_report": days_old,
                "data_reliability": reliability,
                "confluence_scoring_weight": confluence_weight,
                "cot_factor_eligible": confluence_weight >= 0.5,
                "system_instruction": (
                    "COT data INELIGIBLE for confluence scoring. Weight = 0. "
                    "Do NOT include 'cot_aligned' in confluence_factors."
                    if confluence_weight == 0.0 else
                    f"COT eligible with weight {confluence_weight}. "
                    f"Max COT contribution = {confluence_weight} point (not full +1)."
                ),
                "interpretation_note": (
                    f"⚠️ COT data (Tue position, Fri release). {reliability_note}. "
                    f"If weight < 1.0, do NOT award the full +1 confluence point for COT. "
                    f"Pro-rate: weight={confluence_weight} means max COT contribution = {confluence_weight} point."
                ),
                "leveraged_funds": {
                    "long": r.leveraged_long,
                    "short": r.leveraged_short,
                    "net": lev_net,
                    "bias": "net_long" if lev_net > 0 else "net_short",
                },
                "asset_managers": {
                    "long": r.asset_mgr_long,
                    "short": r.asset_mgr_short,
                    "net": am_net,
                    "bias": "net_long" if am_net > 0 else "net_short",
                },
                "dealers": {
                    "long": r.dealer_long,
                    "short": r.dealer_short,
                    "net": r.dealer_long - r.dealer_short,
                },
            })

    return {"count": len(reports), "reports": reports}


async def handle_get_vix(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_vix"}

    days_back = args.get("days_back", 10)
    since = clock.now() - timedelta(days=days_back)

    rows = (await session.execute(
        select(VIXData)
        .where(and_(VIXData.date >= since, VIXData.date <= clock.now()))
        .order_by(VIXData.date.desc())
    )).scalars().all()

    latest = rows[0] if rows else None
    sentiment = "unknown"
    warning = None
    if latest is None:
        return {
            "error": "VIX data unavailable. Treat as defensive/high-risk.",
            "latest": None,
            "sentiment": "unknown",
            "history": [],
        }

    now = clock.now()
    close_val_vix = 0.0
    if latest:
        try:
            close_val_vix = float(getattr(latest, "close", 0.0) or 0.0)
        except (TypeError, ValueError):
            close_val_vix = 0.0

        if close_val_vix > 30:
            sentiment = "high_fear_risk_off"
        elif close_val_vix > 20:
            sentiment = "elevated_uncertainty"
        elif close_val_vix > 15:
            sentiment = "moderate"
        else:
            sentiment = "complacency_risk_on"

        from datetime import date as _dt_date
        vix_date = getattr(latest, "date", None)
        if isinstance(vix_date, datetime):
            if vix_date.tzinfo is None:
                vix_date = vix_date.replace(tzinfo=timezone.utc)
        elif isinstance(vix_date, _dt_date):
            vix_date = datetime(vix_date.year, vix_date.month, vix_date.day, tzinfo=timezone.utc)
        else:
            vix_date = now

        age_days = (now - vix_date).days if isinstance(vix_date, datetime) else 0
        if now.weekday() >= 5 and age_days <= 3:
            warning = f"VIX data is {age_days} days old, but this is expected during the weekend. Proceeding normally."

    latest_date_str = latest.date.strftime("%Y-%m-%d") if latest and latest.date is not None and hasattr(latest.date, "strftime") else (str(latest.date) if latest and latest.date is not None else None)
    history_list = []
    for r in rows:
        r_dt_str = r.date.strftime("%Y-%m-%d") if r.date is not None and hasattr(r.date, "strftime") else str(r.date or "")
        try:
            r_close = float(r.close)
        except (TypeError, ValueError):
            r_close = 0.0
        history_list.append({"date": r_dt_str, "close": r_close})

    return {
        "latest": {"date": latest_date_str, "close": close_val_vix} if latest else None,
        "sentiment": sentiment,
        "warning": warning,
        "history": history_list,
    }


async def handle_get_funding_rate(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for funding rate"}

    # 1. Cek cache SystemConfig
    cfg_rows = (await session.execute(
        select(SystemConfig).where(SystemConfig.key.in_(["coinglass_funding_latest", "funding_rate_latest"]))
    )).scalars().all()

    for cfg in cfg_rows:
        if cfg and cfg.value:
            try:
                data = json.loads(cfg.value)
                if isinstance(data, dict) and not data.get("error") and ("average_funding_rate" in data or "rate" in data or "exchanges" in data):
                    return data
            except Exception:
                pass

    # 2. Live On-Demand Fallback via CoinglasFundingFetcher
    try:
        from data_sources.coinglass_funding import CoinglasFundingFetcher
        fetcher = CoinglasFundingFetcher(session)
        live_data = await fetcher.fetch()
        if live_data and isinstance(live_data, dict) and not live_data.get("error"):
            return live_data
    except Exception as fetch_err:
        logger.debug(f"Live funding rate on-demand fetch error: {fetch_err}")

    # 3. Structured baseline fallback jika offline / mock test environment
    return {
        "symbol": "BTCUSD",
        "average_funding_rate": 0.0001,
        "interpretation": "Neutral (baseline neutral rate fallback)",
        "source": "fallback_baseline",
        "warning": "Live funding rate feed currently initializing; returning baseline neutral rate 0.01% / 8h."
    }


async def handle_get_fear_greed_index(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for fear greed index"}

    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == "fear_greed_latest")
    )).scalar_one_or_none()

    if not cfg or not cfg.value:
        return {
            "error": "Fear & Greed data not available. Ensure data refresh has run.",
            "fallback": "Use VIX as primary sentiment gauge instead."
        }
    try:
        return json.loads(cfg.value)
    except Exception as e:
        return {"error": f"Parse error: {e}"}


async def handle_get_eia_oil_inventory(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for eia inventory"}

    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == "eia_oil_inventory_latest")
    )).scalar_one_or_none()

    if not cfg or not cfg.value:
        return {"status": "unavailable", "message": "EIA crude oil inventory data not yet fetched."}
    try:
        return json.loads(cfg.value)
    except Exception as e:
        return {"error": f"Parse error: {e}"}


async def handle_get_dxy(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_dxy"}

    days_back = args.get("days_back", 10)
    is_weekend = clock.now().weekday() >= 5
    now_dt = clock.now()
    since = now_dt - timedelta(days=days_back)

    # Tier 1: Query window days_back
    rows = (await _safe_execute(
        session,
        select(DXYData)
        .where(and_(DXYData.date >= since, DXYData.date <= now_dt))
        .order_by(DXYData.date.desc())
    )).scalars().all()

    staleness_note = None
    if is_weekend:
        staleness_note = "Weekend: using last Friday close as reference"

    # Tier 2: Fallback to latest available records in DXYData if window is empty
    if not rows:
        rows = (await _safe_execute(
            session,
            select(DXYData)
            .order_by(DXYData.date.desc())
            .limit(10)
        )).scalars().all()
        if rows:
            latest_dt_str = rows[0].date.strftime("%Y-%m-%d") if hasattr(rows[0].date, "strftime") else str(rows[0].date)
            staleness_note = f"DXY data fallback from {latest_dt_str} (outside {days_back}d window)"

    # Tier 3: Fallback to synthetic USD strength proxy from basket if DXYData is empty
    if not rows:
        try:
            from utils.market.usd_strength_proxy import compute_usd_strength_proxy
            proxy_res = await compute_usd_strength_proxy(session, lookback_bars=20, timeframe="H4")
            if proxy_res and proxy_res.get("method") == "basket_proxy":
                trend = proxy_res.get("direction", "unknown")
                weighted_change = float(proxy_res.get("weighted_usd_change_pct", 0.0) or 0.0)
                latest_val = round(100.0 + weighted_change, 3)
                return {
                    "latest": {"date": now_dt.strftime("%Y-%m-%d"), "close": latest_val},
                    "trend_5d": trend,
                    "history": [{"date": now_dt.strftime("%Y-%m-%d"), "close": latest_val}],
                    "is_weekend": is_weekend,
                    "source": "synthetic_basket_proxy",
                    "staleness_note": "DXY feed unavailable; calculated from multi-currency basket proxy.",
                    "interpretation": (
                        f"Synthetic USD Basket index ~{latest_val:.3f}, {trend} ({weighted_change:+.2f}%). "
                        f"{'USD strength suppresses gold and non-USD pairs.' if trend == 'strengthening' else 'USD weakness supports gold and non-USD pairs.'}"
                    ).strip()
                }
        except Exception as e:
            logger.debug(f"USD strength proxy fallback failed: {e}")

        return {
            "error": "No DXY data available. Run DXY fetcher or price sync first.",
            "latest": None,
            "trend_5d": "unknown",
            "history": []
        }

    latest = rows[0]
    try:
        latest_close = float(getattr(latest, "close", 0.0) or 0.0)
    except (TypeError, ValueError):
        latest_close = 0.0

    trend = "unknown"
    if len(rows) >= 5:
        older = rows[4]
        try:
            older_close = float(getattr(older, "close", 0.0) or 0.0)
            diff = latest_close - older_close
            trend = "strengthening" if diff > 0 else "weakening"
        except (TypeError, ValueError):
            trend = "unknown"
    elif len(rows) >= 2:
        older = rows[-1]
        try:
            older_close = float(getattr(older, "close", 0.0) or 0.0)
            diff = latest_close - older_close
            trend = "strengthening" if diff > 0 else "weakening"
        except (TypeError, ValueError):
            trend = "unknown"

    latest_dxy_date = latest.date.strftime("%Y-%m-%d") if hasattr(latest.date, "strftime") else str(latest.date)
    dxy_history = []
    for r in rows:
        r_dxy_dt = r.date.strftime("%Y-%m-%d") if hasattr(r.date, "strftime") else str(r.date or "")
        try:
            rc = round(float(r.close), 3)
        except (TypeError, ValueError):
            rc = 0.0
        dxy_history.append({"date": r_dxy_dt, "close": rc})

    return {
        "latest": {"date": latest_dxy_date, "close": round(latest_close, 3)},
        "trend_5d": trend,
        "history": dxy_history,
        "is_weekend": is_weekend,
        "staleness_note": staleness_note,
        "interpretation": (
            f"DXY at {latest_close:.3f}, {trend} over 5 days. "
            f"{'USD strength suppresses gold and non-USD pairs.' if trend == 'strengthening' else 'USD weakness supports gold and non-USD pairs.'} "
            f"{'[Weekend - last close data]' if is_weekend else ''}"
        ).strip()
    }


def register_macro_tools():
    registry = ToolRegistry.get_instance()
    tools = [
        ToolDefinition(
            name="get_market_session",
            description="Fetch current global Forex session activity, overlap status, and session modifier.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_market_session,
            toolset="macro",
            requires_db=False,
        ),
        ToolDefinition(
            name="get_market_regime",
            description="Detect market regime (trending vs ranging) via ADX for given symbols.",
            parameters={"type": "object", "properties": {"symbols": {"type": "array", "items": {"type": "string"}}, "timeframe": {"type": "string"}}},
            handler=handle_get_market_regime,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_volatility_regime",
            description="Classify per-symbol volatility regime (trending/ranging/volatile) from ADX and volatility indicators.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"}}},
            handler=handle_get_volatility_regime,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_macro_bias_score",
            description="Compute macro alignment bias score for a symbol from yields, rates, and macro reality data.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "direction": {"type": "string"}}},
            handler=handle_get_macro_bias_score,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_dxy",
            description="Fetch US Dollar Index (DXY) price, daily change, and trend direction.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_dxy,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_vix",
            description="Fetch CBOE Volatility Index (VIX) and regime classification.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_vix,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_funding_rate",
            description="Fetch perpetual futures funding rate for crypto assets (BTCUSD).",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
            handler=handle_get_funding_rate,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fear_greed_index",
            description="Fetch Crypto Fear & Greed sentiment index.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_fear_greed_index,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_eia_oil_inventory",
            description="Fetch EIA crude oil inventories weekly report data.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_eia_oil_inventory,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_fedwatch_probabilities",
            description="Fetch CME FedWatch interest rate meeting target probabilities.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}}},
            handler=handle_get_fedwatch_probabilities,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_central_bank_expectations",
            description="Fetch market-implied rate decision expectations (probabilities of Rate Hike, Hold, Rate Cut) across FED, ECB, BOE, BOJ, RBA.",
            parameters={"type": "object", "properties": {"bank": {"type": "string"}}},
            handler=handle_get_central_bank_expectations,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_yield_data",
            description="Fetch US Treasury yield curve and 10Y-2Y / 10Y-3M spreads.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_treasury_yields,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_treasury_yields",
            description="Fetch US Treasury yield curve and 10Y-2Y / 10Y-3M spreads.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_treasury_yields,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_bond_yield_spreads",
            description="Fetch international 10Y sovereign bond yield spreads vs US 10Y.",
            parameters={"type": "object", "properties": {"days_back": {"type": "integer"}}},
            handler=handle_get_bond_yield_spreads,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_cot_report",
            description="Fetch CFTC Commitments of Traders (COT) institutional positioning.",
            parameters={"type": "object", "properties": {"symbol": {"type": "string"}, "market_codes": {"type": "array"}}},
            handler=handle_get_cot_report,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_economic_calendar",
            description="Fetch high and medium impact economic events from the calendar.",
            parameters={"type": "object", "properties": {"hours_back": {"type": "integer"}, "hours_ahead": {"type": "integer"}}},
            handler=handle_get_economic_calendar,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_economic_surprise",
            description="Fetch historical economic data surprise scores.",
            parameters={"type": "object", "properties": {"currency": {"type": "string"}, "days_back": {"type": "integer"}}},
            handler=handle_get_economic_surprise,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_interest_rates",
            description="Fetch central bank policy interest rates (Fed, ECB, BOE, BOJ, RBA).",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_interest_rates,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_precomputed_cot_signals",
            description="Fetch pre-computed COT signals showing institutional positioning and sentiment flags.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_precomputed_cot_signals,
            toolset="macro",
            requires_db=True,
        ),
        ToolDefinition(
            name="get_surprise_summary",
            description="Fetch aggregated economic surprise scores per currency for the last 2 weeks.",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_surprise_summary,
            toolset="macro",
            requires_db=True,
        ),
    ]
    for t in tools:
        registry.register(t)


register_macro_tools()

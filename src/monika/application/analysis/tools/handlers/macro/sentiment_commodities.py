# ==============================================================================
# File: analysis/tools/handlers/macro/sentiment_commodities.py
# ==============================================================================

"""
COT report, VIX, funding rate, Fear & Greed index, EIA oil inventories, DXY, and weekly macro summary handlers.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import and_, select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.macro.base import _get_macro_context, _safe_execute, logger
from monika.infrastructure.database.models import COTReport, DXYData, SystemConfig, VIXData


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
                from monika.application.analysis.prefetch.macro_preprocessor import MacroPreprocessor

                preprocessor = MacroPreprocessor(settings=settings)
                cot_data = await preprocessor.compute_cot_signals(session)
            except Exception as e:
                logger.warning(f"On-the-fly compute_cot_signals failed: {e}")

    return {
        "status": "success" if cot_data else "empty",
        "cot_signals": cot_data,
        "count": len(cot_data) if isinstance(cot_data, dict) else 0,
    }


async def handle_get_cot_report(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for cot report"}

    SYMBOL_TO_COT = {
        "EUR": "099741",
        "EURUSD": "099741",
        "EURO": "099741",
        "EURO_FX": "099741",
        "JPY": "097741",
        "USDJPY": "097741",
        "YEN": "097741",
        "JAPANESE_YEN": "097741",
        "GBP": "096742",
        "GBPUSD": "096742",
        "POUND": "096742",
        "BRITISH_POUND": "096742",
        "AUD": "232741",
        "AUDUSD": "232741",
        "AUST_DOLLAR": "232741",
        "CAD": "090741",
        "USDCAD": "090741",
        "CANADIAN_DOLLAR": "090741",
        "CHF": "092741",
        "USDCHF": "092741",
        "SWISS_FRANC": "092741",
        "GOLD": "088691",
        "XAU": "088691",
        "XAUUSD": "088691",
        "OIL": "067651",
        "CRUDE": "067651",
        "XTIUSD": "067651",
        "CL": "067651",
        "BTC": "133741",
        "BITCOIN": "133741",
        "BTCUSD": "133741",
    }

    raw_codes = args.get("market_codes") or args.get("symbol") or args.get("currency") or []
    if isinstance(raw_codes, str):
        raw_codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
    elif not isinstance(raw_codes, list):
        raw_codes = [str(raw_codes)]

    market_codes = []
    for c in raw_codes:
        upper_c = str(c).upper().strip().replace("/", "")
        market_codes.append(SYMBOL_TO_COT.get(upper_c, upper_c))

    weeks_back = int(args.get("weeks_back", 4))
    query = (
        select(COTReport)
        .where(COTReport.report_date <= clock.now())
        .order_by(COTReport.market_code, COTReport.report_date.desc())
    )

    if market_codes:
        query = query.where(COTReport.market_code.in_(market_codes))

    rows = (await session.execute(query)).scalars().all()

    seen_counts: Dict[str, int] = {}
    reports = []
    now = clock.now()

    for r in rows:
        cnt = seen_counts.get(r.market_code, 0)
        if cnt < weeks_back:
            seen_counts[r.market_code] = cnt + 1
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

            reports.append(
                {
                    "market_code": r.market_code,
                    "report_date": r.report_date.strftime("%Y-%m-%d"),
                    "days_since_report": days_old,
                    "data_reliability": reliability,
                    "confluence_scoring_weight": confluence_weight,
                    "cot_factor_eligible": confluence_weight >= 0.5,
                    "system_instruction": (
                        "COT data INELIGIBLE for confluence scoring. Weight = 0. "
                        "Do NOT include 'cot_aligned' in confluence_factors."
                        if confluence_weight == 0.0
                        else f"COT eligible with weight {confluence_weight}. "
                        f"Max COT contribution = {confluence_weight} point (not full +1)."
                    ),
                    "interpretation_note": (
                        f"[PERINGATAN] COT data (Tue position, Fri release). {reliability_note}. "
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
                }
            )

    return {"count": len(reports), "reports": reports}


async def handle_get_vix(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_vix"}

    days_back = args.get("days_back", 10)
    since = clock.now() - timedelta(days=days_back)

    rows = (
        (
            await session.execute(
                select(VIXData)
                .where(and_(VIXData.date >= since, VIXData.date <= clock.now()))
                .order_by(VIXData.date.desc())
            )
        )
        .scalars()
        .all()
    )

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

    latest_date_str = (
        latest.date.strftime("%Y-%m-%d")
        if latest and latest.date is not None and hasattr(latest.date, "strftime")
        else (str(latest.date) if latest and latest.date is not None else None)
    )
    history_list = []
    for r in rows:
        r_dt_str = (
            r.date.strftime("%Y-%m-%d") if r.date is not None and hasattr(r.date, "strftime") else str(r.date or "")
        )
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
    cfg_rows = (
        (
            await session.execute(
                select(SystemConfig).where(SystemConfig.key.in_(["coinglass_funding_latest", "funding_rate_latest"]))
            )
        )
        .scalars()
        .all()
    )

    for cfg in cfg_rows:
        if cfg and cfg.value:
            try:
                data = json.loads(cfg.value)
                if (
                    isinstance(data, dict)
                    and not data.get("error")
                    and ("average_funding_rate" in data or "rate" in data or "exchanges" in data)
                ):
                    return data
            except Exception:
                pass

    # 2. Live On-Demand Fallback via CoinglasFundingFetcher
    try:
        from monika.infrastructure.data_ingestion.sources.coinglass_funding import CoinglasFundingFetcher

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
        "warning": "Live funding rate feed currently initializing; returning baseline neutral rate 0.01% / 8h.",
    }


async def handle_get_fear_greed_index(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    market = str(args.get("market") or "crypto").lower()

    if market in ("cnn", "stock", "stocks", "sp500"):
        # CNN Stock Market Fear & Greed Index
        try:
            import aiohttp

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8), headers=headers) as c_sess:
                async with c_sess.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        fg = data.get("fear_and_greed", {})
                        score = round(float(fg.get("score", 50.0)), 1)
                        rating = fg.get("rating", "neutral")
                        prev_close = round(float(fg.get("previous_close", score)), 1)
                        return {
                            "market": "US_STOCKS_CNN",
                            "score": score,
                            "rating": rating,
                            "previous_close": prev_close,
                            "status": "success",
                        }
        except Exception as cnn_err:
            logger.debug(f"CNN Fear & Greed API note: {cnn_err}")

        # Web search fallback for CNN Fear & Greed
        try:
            import re

            from monika.infrastructure.data_ingestion.sources.web_search import WebSearch

            ws = WebSearch()
            search_res = await ws.search("CNN Fear and Greed Index score today", max_results=2)
            results = search_res.get("results", []) if isinstance(search_res, dict) else []
            for r in results:
                snip = r.get("snippet", "") + " " + r.get("title", "")
                m = re.search(
                    r"(\d{1,2})\s*(?:out of 100|%|points)?\s*(?:Extreme Fear|Fear|Neutral|Greed|Extreme Greed)",
                    snip,
                    re.IGNORECASE,
                )
                if m:
                    return {
                        "market": "US_STOCKS_CNN",
                        "score": float(m.group(1)),
                        "source": r.get("url"),
                        "snippet": snip[:120],
                        "status": "fallback_web_search",
                    }
        except Exception:
            pass

    if not session:
        return {"error": "Database session required for fear greed index"}

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "fear_greed_latest"))
    ).scalar_one_or_none()

    if cfg and cfg.value:
        try:
            return json.loads(cfg.value)
        except Exception:
            pass

    # On-demand fetch fallback
    try:
        from monika.infrastructure.data_ingestion.sources.fear_greed import FearGreedFetcher

        fetcher = FearGreedFetcher(session)
        return await fetcher.fetch()
    except Exception as e:
        return {"error": f"Fear & Greed fetch failed: {e}", "fallback": "Use VIX as primary sentiment gauge instead."}


async def handle_get_eia_oil_inventory(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for eia inventory"}

    cfg = (
        await session.execute(select(SystemConfig).where(SystemConfig.key == "eia_oil_inventory_latest"))
    ).scalar_one_or_none()

    if cfg and cfg.value:
        try:
            return json.loads(cfg.value)
        except Exception as e:
            logger.debug(f"[EIA] Parse error on cached config: {e}")

    # Fallback 1: Query recent EconomicCalendar records for EIA Crude Oil Inventories
    try:
        from monika.infrastructure.database.models import EconomicCalendar

        cal_query = (
            select(EconomicCalendar)
            .where(EconomicCalendar.event_name.ilike("%Crude Oil Inventories%"))
            .order_by(EconomicCalendar.event_time.desc())
            .limit(1)
        )
        row = (await session.execute(cal_query)).scalar_one_or_none()
        if row:
            actual = float(row.actual) if row.actual is not None else None
            forecast = float(row.forecast) if row.forecast is not None else None
            previous = float(row.previous) if row.previous is not None else None
            surprise = round(actual - forecast, 2) if (actual is not None and forecast is not None) else None
            direction = (
                "build" if (actual is not None and actual > 0) else ("draw" if actual is not None else "unknown")
            )
            return {
                "source": "economic_calendar_fallback",
                "event_name": row.event_name,
                "date": row.event_time.isoformat() if row.event_time else None,
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "surprise": surprise,
                "inventory_change": direction,
                "status": "available",
                "unit": "Million Barrels",
            }
    except Exception as fb_err:
        logger.debug(f"[EIA] Calendar fallback failed: {fb_err}")

    # Fallback 2: Direct EIA Open Data fetcher
    try:
        from monika.infrastructure.data_ingestion.sources.eia_oil_inventory import EIAInventoryFetcher

        fetcher = EIAInventoryFetcher(session)
        live_res = await fetcher.fetch()
        if live_res and not live_res.get("error"):
            return live_res
    except Exception as eia_err:
        logger.debug(f"[EIA] Direct fetch failed: {eia_err}")

    return {
        "status": "unavailable",
        "message": "EIA crude oil inventory data not yet fetched. Use EconomicCalendar or check EIA_API_KEY.",
    }


async def handle_get_dxy(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for get_dxy"}

    days_back = args.get("days_back", 10)
    is_weekend = clock.now().weekday() >= 5
    now_dt = clock.now()
    since = now_dt - timedelta(days=days_back)

    # Tier 1: Query window days_back
    rows = (
        (
            await _safe_execute(
                session,
                select(DXYData)
                .where(and_(DXYData.date >= since, DXYData.date <= now_dt))
                .order_by(DXYData.date.desc()),
            )
        )
        .scalars()
        .all()
    )

    staleness_note = None
    if is_weekend:
        staleness_note = "Weekend: using last Friday close as reference"

    # Tier 2: Fallback to latest available records in DXYData if window is empty
    if not rows:
        rows = (await _safe_execute(session, select(DXYData).order_by(DXYData.date.desc()).limit(10))).scalars().all()
        if rows:
            latest_dt_str = (
                rows[0].date.strftime("%Y-%m-%d") if hasattr(rows[0].date, "strftime") else str(rows[0].date)
            )
            staleness_note = f"DXY data fallback from {latest_dt_str} (outside {days_back}d window)"

    # Tier 3: Fallback to synthetic USD strength proxy from basket if DXYData is empty
    if not rows:
        try:
            from monika.domain.market.usd_strength_proxy import compute_usd_strength_proxy

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
                    ).strip(),
                }
        except Exception as e:
            logger.debug(f"USD strength proxy fallback failed: {e}")

        return {
            "error": "No DXY data available. Run DXY fetcher or price sync first.",
            "latest": None,
            "trend_5d": "unknown",
            "history": [],
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
        ).strip(),
    }


async def handle_get_weekly_macro_summary(args: dict, **ctx) -> dict:
    """Menghasilkan ringkasan komprehensif lanskap makro ekonomi untuk 7 hari ke depan."""
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for weekly macro summary."}

    from monika.application.analysis.tools.handlers.macro.calendar import handle_get_economic_calendar
    from monika.application.analysis.tools.handlers.macro.central_banks import handle_get_fedwatch_probabilities
    from monika.application.analysis.tools.handlers.macro.fixed_income import handle_get_treasury_yields

    days_ahead = int(args.get("days_ahead", 7))
    curr_filter = args.get("currencies")

    # 1. Economic Calendar upcoming events
    hours_ahead = days_ahead * 24
    cal_args = {"hours_ahead": hours_ahead, "hours_back": 12, "impact": "high"}
    if curr_filter:
        cal_args["currency_filter"] = curr_filter
    cal_data = await handle_get_economic_calendar(cal_args, **ctx)
    events = cal_data.get("events", []) if isinstance(cal_data, dict) else []

    # 2. DXY Status
    dxy_data = await handle_get_dxy({"days_back": 7}, **ctx)
    dxy_close = None
    dxy_trend = "unknown"
    if isinstance(dxy_data, dict) and "latest" in dxy_data:
        dxy_close = dxy_data["latest"].get("close")
        dxy_trend = dxy_data.get("trend_5d", "flat")

    # 3. VIX Status
    vix_data = await handle_get_vix({}, **ctx)
    vix_level = vix_data.get("vix_close") or vix_data.get("current_level")
    vix_regime = vix_data.get("regime", "normal")

    # 4. FedWatch Probabilities
    fed_data = await handle_get_fedwatch_probabilities({}, **ctx)
    fed_summary = fed_data.get("formatted", "") if isinstance(fed_data, dict) else ""
    next_meeting = fed_data.get("next_meeting_date", "N/A") if isinstance(fed_data, dict) else "N/A"

    # 5. Treasury Yields
    yield_data = await handle_get_treasury_yields({}, **ctx)
    us10y = None
    curve_inverted = False
    if isinstance(yield_data, dict):
        us10y = yield_data.get("10Y") or yield_data.get("US10Y")
        curve_inverted = yield_data.get("inverted_2y10y", False)

    # Format text telegraphic slip
    now_str = clock.now().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "```",
        "================================================",
        "     MONIKA DISPATCH // WEEKLY MACRO OUTLOOK    ",
        "================================================",
        f"TIMESTAMP      : {now_str}",
        f"HORIZON        : Next {days_ahead} Days",
        "------------------------------------------------",
        "GLOBAL MACRO DRIVERS:",
        f"  DXY (Dollar) : {dxy_close or 'N/A'} (Trend: {str(dxy_trend).upper()})",
        f"  VIX Index    : {vix_level or 'N/A'} (Regime: {str(vix_regime).upper()})",
        f"  US 10Y Yield : {us10y or 'N/A'}% | Curve Inversion: {'YES' if curve_inverted else 'NO'}",
        f"  Fed FOMC Next: {next_meeting}",
        "------------------------------------------------",
        f"HIGH-IMPACT ECONOMIC EVENTS ({len(events)} Total):",
    ]
    if events:
        for ev in events[:8]:
            dt = ev.get("datetime") or ev.get("time") or ev.get("date") or ""
            curr = ev.get("currency", "ALL")
            name = ev.get("event_name") or ev.get("name") or ev.get("event") or ""
            prev = ev.get("previous", "-")
            fc = ev.get("forecast", "-")
            lines.append(f"  [{curr}] {str(dt)[:16]}: {name[:28]} (Prev: {prev}, Fc: {fc})")
        if len(events) > 8:
            lines.append(f"  ... +{len(events) - 8} additional high-impact releases")
    else:
        lines.append("  No critical high-impact releases scheduled in window.")
    lines.extend(["================================================", "```"])
    formatted_summary = "\n".join(lines)

    return {
        "success": True,
        "days_ahead": days_ahead,
        "high_impact_event_count": len(events),
        "events": events[:15],
        "dxy": {"close": dxy_close, "trend": dxy_trend},
        "vix": {"level": vix_level, "regime": vix_regime},
        "treasury_10y": us10y,
        "curve_inverted": curve_inverted,
        "next_fomc": next_meeting,
        "fedwatch_summary": fed_summary,
        "formatted_summary": formatted_summary,
    }


async def handle_get_macro_priced_in_score(args: dict, **ctx) -> dict:
    from monika.application.analysis.calculators.stage1_priced_in import calculate_stage1_priced_in_baseline

    symbol = str(args.get("symbol", "EURUSD")).upper().strip()
    cot_percentile = float(args.get("cot_percentile", 50.0))
    retail_sentiment = args.get("retail_sentiment")
    if retail_sentiment is not None:
        retail_sentiment = float(retail_sentiment)
    fedwatch_dominant_prob = args.get("fedwatch_dominant_prob")
    if fedwatch_dominant_prob is not None:
        fedwatch_dominant_prob = float(fedwatch_dominant_prob)
    eurusd_run_up_vs_atr = args.get("eurusd_run_up_vs_atr")
    if eurusd_run_up_vs_atr is not None:
        eurusd_run_up_vs_atr = float(eurusd_run_up_vs_atr)
    fedwatch_repricing_delta = args.get("fedwatch_repricing_delta")
    if fedwatch_repricing_delta is not None:
        fedwatch_repricing_delta = float(fedwatch_repricing_delta)

    res = calculate_stage1_priced_in_baseline(
        symbol=symbol,
        cot_percentile=cot_percentile,
        retail_sentiment=retail_sentiment,
        fedwatch_dominant_prob=fedwatch_dominant_prob,
        eurusd_run_up_vs_atr=eurusd_run_up_vs_atr,
        fedwatch_repricing_delta=fedwatch_repricing_delta,
    )
    return {
        "symbol": symbol,
        "score": res["score"],
        "is_priced_in": res["is_priced_in"],
        "reasons": res["reasons"],
        "parameters": {
            "cot_percentile": cot_percentile,
            "retail_sentiment": retail_sentiment,
            "fedwatch_dominant_prob": fedwatch_dominant_prob,
            "eurusd_run_up_vs_atr": eurusd_run_up_vs_atr,
            "fedwatch_repricing_delta": fedwatch_repricing_delta,
        },
    }

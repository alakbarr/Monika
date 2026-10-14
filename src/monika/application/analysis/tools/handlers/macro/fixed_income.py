# ==============================================================================
# File: analysis/tools/handlers/macro/fixed_income.py
# ==============================================================================

"""
US Treasury yields, international sovereign bond yield spreads, and treasury auction handlers.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.macro.base import _get_macro_context, _safe_execute
from monika.infrastructure.database.models import BondYieldData, TreasuryYield


async def handle_get_treasury_yields(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for treasury yields"}

    days_back = args.get("days_back", 5)
    since = clock.now() - timedelta(days=days_back)
    raw_res = await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.tenor, TreasuryYield.date.desc()),
    )
    rows = raw_res.scalars().all() if raw_res is not None else []

    by_tenor: dict[str, list] = {}
    for r in rows:
        by_tenor.setdefault(r.tenor, []).append({"date": r.date.strftime("%Y-%m-%d"), "yield_pct": r.yield_percent})

    spread = None
    if "2Y" in by_tenor and "10Y" in by_tenor:
        try:
            spread = round(by_tenor["10Y"][0]["yield_pct"] - by_tenor["2Y"][0]["yield_pct"], 3)
        except IndexError, TypeError:
            pass

    # Fed Net Liquidity calculation: Total Assets (WALCL in Millions/1000) - TGA (WTREGEN in Billions) - Reverse Repo (RRPONTSYD in Billions)
    fed_net_liquidity = None
    if "FED_TOTAL_ASSETS" in by_tenor and "TGA_BALANCE" in by_tenor and "REVERSE_REPO" in by_tenor:
        try:
            walcl_b = (
                by_tenor["FED_TOTAL_ASSETS"][0]["yield_pct"] / 1000.0
                if by_tenor["FED_TOTAL_ASSETS"][0]["yield_pct"] > 50000
                else by_tenor["FED_TOTAL_ASSETS"][0]["yield_pct"]
            )
            tga_b = (
                by_tenor["TGA_BALANCE"][0]["yield_pct"] / 1000.0
                if by_tenor["TGA_BALANCE"][0]["yield_pct"] > 50000
                else by_tenor["TGA_BALANCE"][0]["yield_pct"]
            )
            rrp_b = (
                by_tenor["REVERSE_REPO"][0]["yield_pct"] / 1000.0
                if by_tenor["REVERSE_REPO"][0]["yield_pct"] > 50000
                else by_tenor["REVERSE_REPO"][0]["yield_pct"]
            )
            fed_net_liquidity = round(walcl_b - tga_b - rrp_b, 2)
        except Exception:
            fed_net_liquidity = None

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
        "fed_net_liquidity_billions": fed_net_liquidity,
        "curve_status": "inverted"
        if spread is not None and spread < 0
        else "normal"
        if spread is not None and spread > 0
        else "unknown",
        "data_age_hours": data_age_hours,
        "staleness_note": f"Data berumur {data_age_hours}h (bisa juga dari cache hingga 6h)."
        if data_age_hours and data_age_hours > 24
        else None,
    }


async def handle_get_bond_yield_spreads(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for bond yield spreads"}

    days_back = args.get("days_back", 10)
    since = clock.now() - timedelta(days=days_back)

    # 1. Ambil US 10Y & 2Y Treasury
    raw_10y = await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.tenor == "10Y", TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.date.desc()),
    )
    us_10y_rows = raw_10y.scalars().all() if raw_10y is not None else []
    us_10y_by_date = {r.date.strftime("%Y-%m-%d"): r.yield_percent for r in us_10y_rows}

    raw_2y = await _safe_execute(
        session,
        select(TreasuryYield)
        .where(and_(TreasuryYield.tenor == "2Y", TreasuryYield.date >= since, TreasuryYield.date <= clock.now()))
        .order_by(TreasuryYield.date.desc()),
    )
    us_2y_rows = raw_2y.scalars().all() if raw_2y is not None else []
    us_2y_by_date = {r.date.strftime("%Y-%m-%d"): r.yield_percent for r in us_2y_rows}

    # 2. Ambil yield internasional (10Y dan 2Y)
    intl_since = clock.now() - timedelta(days=max(days_back, 60))
    raw_intl = await _safe_execute(
        session,
        select(BondYieldData)
        .where(and_(BondYieldData.date >= intl_since, BondYieldData.date <= clock.now()))
        .order_by(BondYieldData.country_tenor, BondYieldData.date.desc()),
    )
    intl_rows = raw_intl.scalars().all() if raw_intl is not None else []

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
                latest_res = await _safe_execute(
                    session,
                    select(BondYieldData)
                    .where(BondYieldData.country_tenor == code)
                    .order_by(BondYieldData.date.desc())
                    .limit(5),
                )
                latest_rows = latest_res.scalars().all() if latest_res is not None else []
                for r in latest_rows:
                    country_yields[r.date.strftime("%Y-%m-%d")] = r.yield_percent

            common_dates = sorted(set(us_dict.keys()) & set(country_yields.keys()), reverse=True)
            spread_series = []
            if common_dates:
                for dt in common_dates:
                    u_val = us_dict[dt]
                    i_val = country_yields[dt]
                    spread_val = round(u_val - i_val, 3)
                    spread_series.append(
                        {
                            "date": dt,
                            f"us_{tenor_suffix}": u_val,
                            f"intl_{tenor_suffix}": i_val,
                            "spread_us_minus_intl": spread_val,
                        }
                    )
            elif us_dict and country_yields:
                sorted_intl_dates = sorted(country_yields.keys())
                for us_dt in sorted(us_dict.keys(), reverse=True):
                    candidate_dates = [d for d in sorted_intl_dates if d <= us_dt]
                    if candidate_dates:
                        matched_intl_dt = candidate_dates[-1]
                        u_val = us_dict[us_dt]
                        i_val = country_yields[matched_intl_dt]
                        spread_val = round(u_val - i_val, 3)
                        spread_series.append(
                            {
                                "date": us_dt,
                                "intl_date": matched_intl_dt,
                                f"us_{tenor_suffix}": u_val,
                                f"intl_{tenor_suffix}": i_val,
                                "spread_us_minus_intl": spread_val,
                            }
                        )
                if not spread_series:
                    latest_us = next(iter(us_dict.values()))
                    latest_intl = next(iter(country_yields.values()))
                    latest_dt = next(iter(us_dict.keys()))
                    latest_intl_dt = next(iter(country_yields.keys()))
                    spread_series.append(
                        {
                            "date": latest_dt,
                            "intl_date": latest_intl_dt,
                            f"us_{tenor_suffix}": latest_us,
                            f"intl_{tenor_suffix}": latest_intl,
                            "spread_us_minus_intl": round(latest_us - latest_intl, 3),
                        }
                    )

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
        "DE_10Y": {
            "name": "Germany (Bund 10Y)",
            "fx_pair": "EURUSD",
            "direction_impact": "Widening US-DE spread = Bearish EURUSD, Narrowing = Bullish EURUSD",
        },
        "UK_10Y": {
            "name": "United Kingdom (Gilt 10Y)",
            "fx_pair": "GBPUSD",
            "direction_impact": "Widening US-UK spread = Bearish GBPUSD, Narrowing = Bullish GBPUSD",
        },
        "JP_10Y": {
            "name": "Japan (JGB 10Y)",
            "fx_pair": "USDJPY",
            "direction_impact": "Widening US-JP spread = Bullish USDJPY, Narrowing = Bearish USDJPY",
        },
        "AU_10Y": {
            "name": "Australia (ACGB 10Y)",
            "fx_pair": "AUDUSD",
            "direction_impact": "Widening US-AU spread = Bearish AUDUSD, Narrowing = Bullish AUDUSD",
        },
    }

    # Mapping 2Y (Short-End Monetary Policy Divergence)
    COUNTRY_MAPPING_2Y = {
        "DE_2Y": {
            "name": "Germany (Bund 2Y)",
            "fx_pair": "EURUSD",
            "direction_impact": "Widening US-DE 2Y spread = Bearish EURUSD (short-end policy advantage to USD)",
        },
        "UK_2Y": {
            "name": "United Kingdom (Gilt 2Y)",
            "fx_pair": "GBPUSD",
            "direction_impact": "Widening US-UK 2Y spread = Bearish GBPUSD",
        },
        "JP_2Y": {
            "name": "Japan (JGB 2Y)",
            "fx_pair": "USDJPY",
            "direction_impact": "Widening US-JP 2Y spread = Bullish USDJPY (carry trade funding incentive)",
        },
        "AU_2Y": {
            "name": "Australia (ACGB 2Y)",
            "fx_pair": "AUDUSD",
            "direction_impact": "Widening US-AU 2Y spread = Bearish AUDUSD",
        },
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
        ),
    }


async def handle_get_treasury_auction_results(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer

    analyzer = UniversalLiquidityAnalyzer(session)
    tenor = args.get("tenor", "10Y")
    limit = int(args.get("limit", 5))
    return await analyzer.analyze_treasury_auction_demand(tenor=tenor, limit=limit)

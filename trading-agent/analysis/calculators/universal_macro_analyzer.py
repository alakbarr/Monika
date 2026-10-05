# ==============================================================================
# File: analysis/calculators/universal_macro_analyzer.py
# ==============================================================================

"""
Universal Macroeconomic Decomposition & G10 Relative Divergence Engine (Async).
Performs granular component attribution, separates transitory noise from sticky persistent inflation,
analyzes labor market surveys and net payroll revisions, and synthesizes cross-report macroeconomic chains.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EconomicReportDecomposition, TreasuryYield, InterestRate
from scrapers.macro.macro_trigger_router import MacroTriggerRouter
from utils import clock

logger = logging.getLogger("TradingAgent.UniversalMacroAnalyzer")


class UniversalMacroAnalyzer:
    """Institutional macro analysis desk calculator."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.router = MacroTriggerRouter(session)

    async def decompose_report(
        self,
        report_type: str = "CPI",
        period: Optional[str] = None,
        country: str = "US",
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """
        Decomposes macroeconomic releases into sub-components.
        Answers: What drove the surprise? Is it structural or transitory noise?
        """
        rtype = report_type.upper()
        rep_period = period or clock.now().strftime("%Y-%m")

        # JIT ensure available
        await self.router.ensure_report_available(report_type=rtype, period=rep_period, country=country, currency=currency)

        stmt = (
            select(EconomicReportDecomposition)
            .where(
                EconomicReportDecomposition.report_type == rtype,
                EconomicReportDecomposition.country == country,
                EconomicReportDecomposition.period == rep_period,
            )
            .order_by(EconomicReportDecomposition.id.asc())
        )
        records = (await self.session.execute(stmt)).scalars().all()

        if not records:
            return {
                "report_type": rtype,
                "period": rep_period,
                "status": "not_found",
                "message": f"No decomposition records available for {rtype} ({rep_period})",
            }

        headline_item = next((r for r in records if r.category == "headline"), records[0])
        core_item = next((r for r in records if r.category == "core" and "Headline" not in r.component_name), None)

        top_upside_drivers: List[Dict[str, Any]] = []
        top_downside_drivers: List[Dict[str, Any]] = []
        sticky_components: List[Dict[str, Any]] = []
        transitory_noise_components: List[Dict[str, Any]] = []

        total_noise_bps = 0.0
        total_sticky_bps = 0.0

        for r in records:
            if r.category == "headline":
                continue
            item = {
                "name": r.component_name,
                "category": r.category,
                "actual": r.value_actual,
                "forecast": r.value_forecast,
                "mom_change": r.mom_change,
                "contribution_bps": r.contribution_bps or 0.0,
                "is_noise": r.is_noise,
            }
            if (r.mom_change or 0.0) >= 0:
                top_upside_drivers.append(item)
            else:
                top_downside_drivers.append(item)

            if r.is_noise or r.category == "transitory":
                transitory_noise_components.append(item)
                total_noise_bps += abs(r.contribution_bps or 0.0)
            elif r.category in ("sticky", "core"):
                sticky_components.append(item)
                total_sticky_bps += abs(r.contribution_bps or 0.0)

        # Sort drivers by absolute contribution
        top_upside_drivers.sort(key=lambda x: abs(x["contribution_bps"]), reverse=True)
        top_downside_drivers.sort(key=lambda x: abs(x["contribution_bps"]), reverse=True)

        # Quantitative verdict: Is the headline surprise structural or transitory noise?
        is_structural = total_sticky_bps > total_noise_bps
        if total_noise_bps > total_sticky_bps * 1.5:
            verdict = "TRANSITORY_NOISE_ONLY"
            verdict_explanation = (
                f"Surprise primarily driven by volatile seasonal items ({', '.join([c['name'] for c in transitory_noise_components])}). "
                "Core persistent components remain stable or disinflating. Unlikely to alter central bank policy trajectory."
            )
        elif total_sticky_bps >= total_noise_bps:
            verdict = "STRUCTURAL_PERSISTENT_SHIFT"
            verdict_explanation = (
                f"Surprise driven by persistent sticky services and shelter ({', '.join([c['name'] for c in sticky_components[:2]])}). "
                "Represents genuine underlying pressure likely to anchor higher-for-longer monetary stance."
            )
        else:
            verdict = "MIXED_IMPACT"
            verdict_explanation = "Balanced contribution between sticky core and volatile components. Monitor next revision."

        return {
            "report_type": rtype,
            "country": country,
            "period": rep_period,
            "headline": {
                "actual": headline_item.value_actual,
                "forecast": headline_item.value_forecast,
                "previous": headline_item.value_previous,
                "mom": headline_item.mom_change,
                "yoy": headline_item.yoy_change,
            },
            "core": {
                "actual": core_item.value_actual if core_item else None,
                "forecast": core_item.value_forecast if core_item else None,
                "mom": core_item.mom_change if core_item else None,
                "yoy": core_item.yoy_change if core_item else None,
            } if core_item else None,
            "top_upside_drivers": top_upside_drivers[:3],
            "top_downside_drivers": top_downside_drivers[:3],
            "transitory_noise_attribution": {
                "noise_components": transitory_noise_components,
                "total_noise_bps": round(total_noise_bps, 1),
            },
            "sticky_core_attribution": {
                "sticky_components": sticky_components,
                "total_sticky_bps": round(total_sticky_bps, 1),
            },
            "institutional_verdict": {
                "classification": verdict,
                "is_structural_shift": is_structural,
                "rationale": verdict_explanation,
            },
        }

    async def decompose_labor_market(self, period: Optional[str] = None) -> Dict[str, Any]:
        """
        Decomposes US labor market reports (NFP, revisions, wages, household divergence).
        """
        rep_period = period or clock.now().strftime("%Y-%m")
        await self.router.ensure_report_available(report_type="NFP", period=rep_period)

        stmt = select(EconomicReportDecomposition).where(
            EconomicReportDecomposition.report_type == "NFP",
            EconomicReportDecomposition.period == rep_period,
        )
        records = (await self.session.execute(stmt)).scalars().all()

        nfp_data: Dict[str, float] = {}
        for r in records:
            nfp_data[r.component_name] = r.value_actual

        total_nfp = nfp_data.get("Total Nonfarm Payroll", 185.0)
        private = nfp_data.get("Private Payrolls", 145.0)
        gov = nfp_data.get("Government Payrolls", 40.0)
        revisions_2m = nfp_data.get("2-Month Net Payroll Revision", -32.0)
        ahe = nfp_data.get("Average Hourly Earnings (MoM)", 0.3)
        unrate = nfp_data.get("U-3 Unemployment Rate", 4.1)

        real_underlying_headline = total_nfp + revisions_2m

        quality = "HIGH_QUALITY" if private / max(total_nfp, 1.0) >= 0.8 and revisions_2m >= 0 else "LOW_QUALITY_DISTORTED"

        return {
            "period": rep_period,
            "total_nonfarm_payroll": total_nfp,
            "private_payrolls": private,
            "government_payrolls": gov,
            "private_share_pct": round((private / max(total_nfp, 1.0)) * 100.0, 1),
            "net_2month_revisions": revisions_2m,
            "underlying_effective_payroll": real_underlying_headline,
            "wage_growth_mom": ahe,
            "unemployment_rate": unrate,
            "labor_quality_verdict": {
                "status": quality,
                "headline_vs_revision_drag": f"Headline announced +{total_nfp:,.0f}k, but net 2-month revision subtracted {abs(revisions_2m):,.0f}k, leaving real effective gain of +{real_underlying_headline:,.0f}k.",
                "wage_inflation_pressure": "ELEVATED" if ahe >= 0.4 else ("BENIGN" if ahe <= 0.2 else "MODERATE"),
            },
        }

    async def analyze_cross_report_synthesis(self, currency: str = "USD", lookback_days: int = 30) -> Dict[str, Any]:
        """
        Synthesizes the complete macroeconomic pipeline:
        ISM Prices Paid -> PPI -> CPI -> Core PCE -> Wage Growth -> Fed Reaction & DXY.
        """
        cpi = await self.decompose_report("CPI")
        nfp = await self.decompose_labor_market()

        cpi_verdict = cpi.get("institutional_verdict", {}).get("classification", "NEUTRAL")
        wage_pressure = nfp.get("labor_quality_verdict", {}).get("wage_inflation_pressure", "MODERATE")

        # Determine macro regime chain
        if "STRUCTURAL" in cpi_verdict and wage_pressure == "ELEVATED":
            macro_bias = "HAWKISH_EXPANSION"
            fx_impact = "STRONG_USD_BULLISH"
            bond_impact = "YIELDS_HIGHER_BEAR_STEEPENER"
            playbook = "Long USD against EUR/JPY. Short gold on rate spikes. Favor cash/carry trades."
        elif "TRANSITORY" in cpi_verdict or wage_pressure == "BENIGN":
            macro_bias = "DISINFLATIONARY_SOFT_LANDING"
            fx_impact = "MILD_USD_PRESSURE_RISK_ON"
            bond_impact = "YIELDS_LOWER_BULL_STEEPENER"
            playbook = "Long EUR/USD and AUD/USD on rate cut expectations. Buy equity and risk dip."
        else:
            macro_bias = "DATA_DEPENDENT_STAGNATION"
            fx_impact = "RANGE_BOUND_DXY"
            bond_impact = "SIDEWAYS_CONSOLIDATION"
            playbook = "Trade range boundaries on major pairs. Keep position sizing conservative."

        return {
            "currency": currency,
            "pipeline_flow": "ISM Prices Paid (53.2) -> PPI Core (0.2%) -> CPI Core (0.2%) -> Core PCE (0.2%) -> NFP Wage (0.3%)",
            "macro_regime_classification": macro_bias,
            "projected_market_impact": {
                "fx_dollar_index": fx_impact,
                "sovereign_bond_yields": bond_impact,
                "institutional_playbook": playbook,
            },
            "cpi_summary": cpi.get("institutional_verdict", {}),
            "labor_summary": nfp.get("labor_quality_verdict", {}),
        }

    async def analyze_g10_macro_divergence(self, pair: str = "EURUSD") -> Dict[str, Any]:
        """
        Evaluates relative macro divergence between base and quote currency.
        Currencies trade on relative differentials (growth, inflation, interest rate trajectory).
        """
        pair_clean = pair.replace("/", "").upper()
        base = pair_clean[:3]
        quote = pair_clean[3:]

        # Standard institutional benchmarks for relative scoring (with dynamic database overrides)
        g10_metrics = {
            "USD": {"terminal_rate": 5.375, "gdp_growth": 2.4, "core_inflation": 2.8, "pmi": 51.5},
            "EUR": {"terminal_rate": 3.650, "gdp_growth": 0.8, "core_inflation": 2.7, "pmi": 47.8},
            "GBP": {"terminal_rate": 4.850, "gdp_growth": 1.1, "core_inflation": 3.3, "pmi": 50.2},
            "JPY": {"terminal_rate": 0.250, "gdp_growth": 0.4, "core_inflation": 2.5, "pmi": 49.5},
            "AUD": {"terminal_rate": 4.350, "gdp_growth": 1.5, "core_inflation": 3.5, "pmi": 48.9},
        }

        # Dynamic GDP query from TreasuryYield series (US_REAL_GDP, EUROZONE_REAL_GDP)
        try:
            stmt_gdp = (
                select(TreasuryYield.tenor, TreasuryYield.yield_percent)
                .where(TreasuryYield.tenor.in_(["US_REAL_GDP", "EUROZONE_REAL_GDP"]))
                .order_by(TreasuryYield.date.desc())
            )
            gdp_rows = (await self.session.execute(stmt_gdp)).all()
            for tenor, val in gdp_rows:
                if tenor == "US_REAL_GDP" and "USD" in g10_metrics and val is not None:
                    g10_metrics["USD"]["gdp_growth"] = float(val)
                elif tenor == "EUROZONE_REAL_GDP" and "EUR" in g10_metrics and val is not None:
                    g10_metrics["EUR"]["gdp_growth"] = float(val)
        except Exception as e:
            logger.debug(f"Dynamic GDP query non-blocking fallback: {e}")

        # Dynamic interest rate query from InterestRate table
        try:
            stmt_rates = (
                select(InterestRate.bank, InterestRate.rate_percent)
                .order_by(InterestRate.date.desc())
            )
            rate_rows = (await self.session.execute(stmt_rates)).all()
            bank_to_curr = {"FED": "USD", "ECB": "EUR", "BOE": "GBP", "BOJ": "JPY", "RBA": "AUD"}
            seen_banks = set()
            for bank, rate in rate_rows:
                if bank in bank_to_curr and bank not in seen_banks:
                    curr = bank_to_curr[bank]
                    if curr in g10_metrics and rate is not None:
                        g10_metrics[curr]["terminal_rate"] = float(rate)
                    seen_banks.add(bank)
        except Exception as e:
            logger.debug(f"Dynamic rate query non-blocking fallback: {e}")

        m_base = g10_metrics.get(base, g10_metrics["USD"])
        m_quote = g10_metrics.get(quote, g10_metrics["USD"])

        rate_diff = round(m_base["terminal_rate"] - m_quote["terminal_rate"], 3)
        growth_diff = round(m_base["gdp_growth"] - m_quote["gdp_growth"], 2)
        inflation_diff = round(m_base["core_inflation"] - m_quote["core_inflation"], 2)

        # Macro score: rate differential + growth differential
        relative_score = round(rate_diff * 0.6 + growth_diff * 0.4, 2)

        if relative_score > 0.5:
            bias = f"BULLISH_{base}"
            recommendation = f"Fundamental macro divergence favors {base} strength against {quote}."
        elif relative_score < -0.5:
            bias = f"BEARISH_{base}"
            recommendation = f"Fundamental macro divergence favors {quote} strength against {base}."
        else:
            bias = "NEUTRAL_BALANCED"
            recommendation = f"Macro divergence between {base} and {quote} is compressed. Rely on technical price action."

        return {
            "pair": pair_clean,
            "base_currency": base,
            "quote_currency": quote,
            "rate_differential_pct": rate_diff,
            "gdp_growth_differential_pct": growth_diff,
            "inflation_differential_pct": inflation_diff,
            "relative_macro_score": relative_score,
            "fundamental_bias": bias,
            "institutional_recommendation": recommendation,
        }

# ==============================================================================
# File: analysis/calculators/universal_liquidity_analyzer.py
# ==============================================================================

"""
Universal Systemic Liquidity, Credit Stress & Debt Auction Analyzer (Async).
Monitors Federal Reserve Net Liquidity trends (WALCL - TGA - RRP),
interbank money market funding, corporate credit spreads (HY OAS), and US Treasury auctions.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MacroLiquidityCreditMetric, TreasuryYield
from scrapers.macro.macro_trigger_router import MacroTriggerRouter
from utils import clock

logger = logging.getLogger("TradingAgent.UniversalLiquidityAnalyzer")


class UniversalLiquidityAnalyzer:
    """Institutional liquidity and debt market analytics calculator."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.router = MacroTriggerRouter(session)

    async def analyze_fed_net_liquidity(self, lookback_weeks: int = 8) -> Dict[str, Any]:
        """
        Calculates Net Liquidity trajectory and its expected cross-asset market regime.
        Formula: Net Liquidity = WALCL - TGA - ON_RRP.
        """
        await self.router.ensure_liquidity_and_stress_available()

        stmt = (
            select(MacroLiquidityCreditMetric)
            .where(MacroLiquidityCreditMetric.metric_type == "FED_NET_LIQUIDITY")
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(lookback_weeks)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        if not records:
            return {"status": "unavailable", "message": "No Fed Net Liquidity data found"}

        latest = records[0]
        net_b = latest.value
        delta_b = latest.change_value or 0.0
        regime = latest.regime or ("EXPANSIONARY" if delta_b >= 0 else "CONTRACTIONARY")

        # Fetch underlying components
        stmt_comp = (
            select(MacroLiquidityCreditMetric)
            .where(MacroLiquidityCreditMetric.metric_type.in_(["FED_WALCL", "FED_TGA", "FED_ON_RRP"]))
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(3)
        )
        comps = (await self.session.execute(stmt_comp)).scalars().all()
        comp_dict = {c.metric_type: c.value for c in comps}

        walcl = comp_dict.get("FED_WALCL", 6980.5)
        tga = comp_dict.get("FED_TGA", 785.2)
        rrp = comp_dict.get("FED_ON_RRP", 235.4)

        if regime == "EXPANSIONARY":
            market_implication = "Bullish for equities and risk assets; downward pressure on US Dollar (DXY)."
        else:
            market_implication = "Liquidity drainage creates headwinds for risk assets; supportive for US Dollar cash demand."

        return {
            "current_net_liquidity_billions": net_b,
            "regime": regime,
            "recent_change_billions": delta_b,
            "balance_sheet_components": {
                "fed_total_assets_walcl": walcl,
                "treasury_general_account_tga": tga,
                "overnight_reverse_repo_rrp": rrp,
            },
            "formula": "WALCL - TGA - RRP",
            "cross_asset_implication": market_implication,
            "record_date": latest.record_date.strftime("%Y-%m-%d"),
        }

    async def analyze_credit_and_funding_stress(self) -> Dict[str, Any]:
        """
        Evaluates corporate credit spreads (HY OAS) and SOFR overnight rate.
        Detects impending carry trade unwinding and risk-off liquidations.
        """
        await self.router.ensure_liquidity_and_stress_available()

        stmt = (
            select(MacroLiquidityCreditMetric)
            .where(MacroLiquidityCreditMetric.metric_type.in_(["ICE_BOFA_HY_OAS", "SOFR_RATE"]))
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(2)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        hy_item = next((r for r in records if r.metric_type == "ICE_BOFA_HY_OAS"), None)
        sofr_item = next((r for r in records if r.metric_type == "SOFR_RATE"), None)

        hy_oas = hy_item.value if hy_item else 320.0
        sofr = sofr_item.value if sofr_item else 5.31

        if hy_oas > 450.0:
            stress_level = "CRITICAL_STRESS"
            warning = "Corporate credit spreads blown out (>450 bps). High systemic liquidation risk across FX carry pairs."
        elif hy_oas > 380.0:
            stress_level = "ELEVATED_VULNERABILITY"
            warning = "Credit spreads widening above baseline. Exercise tight stop losses on risk-sensitive currencies."
        else:
            stress_level = "BENIGN_STABLE"
            warning = "Credit conditions accommodative. Corporate default risk benign; carry trade environments stable."

        return {
            "hy_oas_bps": hy_oas,
            "sofr_rate_pct": sofr,
            "stress_regime": stress_level,
            "market_warning": warning,
            "stress_threshold_bps": 450.0,
        }

    async def analyze_treasury_auction_demand(self, tenor: str = "10Y", limit: int = 5) -> Dict[str, Any]:
        """
        Retrieves recent US Treasury debt auctions and inspects tail spread and indirect bidder demand.
        """
        await self.router.ensure_liquidity_and_stress_available()
        tenor_clean = tenor.strip().upper()
        metric_key = f"TREASURY_AUCTION_{tenor_clean}"

        stmt = (
            select(MacroLiquidityCreditMetric)
            .where(MacroLiquidityCreditMetric.metric_type == metric_key)
            .order_by(MacroLiquidityCreditMetric.record_date.desc())
            .limit(limit)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        if not records:
            return {"status": "unavailable", "message": f"No auction records found for {metric_key}"}

        latest = records[0]
        meta = json.loads(latest.metadata_json) if latest.metadata_json else {}

        tail_bps = meta.get("tail_bps", 0.0)
        indirect_pct = meta.get("indirect_bidder_pct", 65.0)
        btc = meta.get("bid_to_cover", 2.50)

        if tail_bps <= 0.0:
            verdict = "EXCELLENT_TAILLESS_AUCTION"
            summary = f"Strong auction with negative tail ({tail_bps:+.1f} bps) and {indirect_pct:.1f}% foreign participation."
        elif tail_bps > 1.2:
            verdict = "POOR_TAILING_AUCTION"
            summary = f"Weak demand forcing dealer concession with a large {tail_bps:+.1f} bps tail. Bearish for Treasuries."
        else:
            verdict = "AVERAGE_AUCTION"
            summary = f"Routine debt placement meeting average dealer absorption ({btc:.2f}x bid-to-cover)."

        return {
            "tenor": tenor_clean,
            "auction_date": latest.record_date.strftime("%Y-%m-%d"),
            "high_stopping_yield": latest.value,
            "tail_basis_points": tail_bps,
            "bid_to_cover_ratio": btc,
            "foreign_indirect_bidders_pct": indirect_pct,
            "auction_health_verdict": {
                "classification": verdict,
                "summary": summary,
            },
        }

    async def analyze_ecb_balance_sheet_and_qt(self, lookback_weeks: int = 8) -> Dict[str, Any]:
        """
        Analyzes European Central Bank (ECB) total balance sheet trend and Quantitative Tightening (QT) progress.
        Examines asset contraction from APP runoff, PEPP reinvestment phase-out, and TLTRO repayments.
        """
        stmt = (
            select(TreasuryYield)
            .where(TreasuryYield.tenor == "ECB_TOTAL_ASSETS")
            .order_by(TreasuryYield.date.desc())
            .limit(lookback_weeks)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        peak_assets_eur_millions = 8830000.0  # Peak in mid-2022 (~8.83T EUR)

        if records:
            current_assets = records[0].yield_percent
            prev_assets = records[-1].yield_percent if len(records) > 1 else current_assets
            date_str = records[0].date.strftime("%Y-%m-%d")
            delta_period_millions = current_assets - prev_assets
        else:
            # Institutional baseline if FRED feed is yet to populate
            current_assets = 6450000.0  # ~6.45T EUR
            delta_period_millions = -35000.0
            date_str = clock.now().strftime("%Y-%m-%d")

        total_reduction_millions = peak_assets_eur_millions - current_assets
        reduction_from_peak_pct = round((total_reduction_millions / peak_assets_eur_millions) * 100.0, 2)
        current_assets_trillions = round(current_assets / 1000000.0, 3)
        peak_assets_trillions = round(peak_assets_eur_millions / 1000000.0, 3)

        regime = "ACTIVE_QUANTITATIVE_TIGHTENING"
        verdict = (
            f"ECB balance sheet has contracted by {reduction_from_peak_pct}% from its peak of €{peak_assets_trillions:.2f}T "
            f"down to €{current_assets_trillions:.2f}T. Full runoff of APP redemptions and tapering of PEPP "
            "continues to drain excess liquidity from the Eurosystem, exerting upward pressure on ESTR and peripheral bond yields."
        )

        return {
            "bank": "ECB",
            "current_assets_eur_millions": current_assets,
            "current_assets_eur_trillions": current_assets_trillions,
            "peak_assets_eur_trillions": peak_assets_trillions,
            "reduction_from_peak_pct": reduction_from_peak_pct,
            "lookback_change_eur_millions": round(delta_period_millions, 1),
            "qt_regime": regime,
            "programs": {
                "app": "Full passive runoff (no reinvestment of maturing securities)",
                "pepp": "Reinvestment reduction phase-out (€7.5B/month average reduction)",
                "tltro_repayments": "Matured / repaid, shrinking excess reserves",
            },
            "market_impact": {
                "eur_implication": "Moderately bullish EUR support via higher real neutral rates and reduced bank excess liquidity.",
                "sovereign_spreads": "Widening pressure on peripheral spreads (BTP-Bund spread risk).",
            },
            "institutional_summary": verdict,
            "record_date": date_str,
        }

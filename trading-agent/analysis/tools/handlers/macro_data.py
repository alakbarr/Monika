# ==============================================================================
# File: analysis/tools/handlers/macro_data.py
# ==============================================================================

"""
Macro data tool handlers delegating directly to modular macro handlers.
Direct execution without circular trampolines.
"""

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from analysis.tools.handlers.macro_tools import (
    handle_get_bond_yield_spreads,
    handle_get_fedwatch_probabilities,
    handle_get_funding_rate,
    handle_get_eia_oil_inventory,
    handle_get_treasury_yields,
    handle_get_interest_rates,
    handle_get_cot_report,
    handle_get_vix,
    handle_get_dxy,
    handle_get_fear_greed_index,
    handle_get_economic_calendar,
    handle_get_economic_surprise,
    handle_get_precomputed_cot_signals,
    handle_get_surprise_summary,
    handle_inspect_economic_report,
    handle_diff_central_bank_documents,
    handle_get_macro_cross_report_synthesis,
    handle_get_g10_macro_divergence,
    handle_get_fed_net_liquidity_and_stress,
    handle_get_treasury_auction_results,
    handle_get_ecb_qt_progress,
    handle_get_global_pmi_trend,
)


@register_tool("get_bond_yield_spreads", aliases=["bond_yield_spreads", "yield_spreads"], category="MACRO", parallel_safe=True)
class GetBondYieldSpreadsHandler(ToolHandler):
    name = "get_bond_yield_spreads"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_bond_yield_spreads(args, session=session, executor=executor, **kwargs)


@register_tool("get_fedwatch_probabilities", aliases=["get_fedwatch", "fedwatch"], category="MACRO", parallel_safe=True)
class GetFedWatchProbabilitiesHandler(ToolHandler):
    name = "get_fedwatch_probabilities"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_fedwatch_probabilities(args, session=session, executor=executor, **kwargs)


@register_tool("get_funding_rate", aliases=["funding_rate"], category="MACRO", parallel_safe=True)
class GetFundingRateHandler(ToolHandler):
    name = "get_funding_rate"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_funding_rate(args, session=session, executor=executor, **kwargs)


@register_tool("get_eia_oil_inventory", aliases=["eia_oil_inventory", "eia_inventory"], category="MACRO", parallel_safe=True)
class GetEiaOilInventoryHandler(ToolHandler):
    name = "get_eia_oil_inventory"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_eia_oil_inventory(args, session=session, executor=executor, **kwargs)


@register_tool("get_treasury_yields", aliases=["get_treasury_yield", "treasury_yields"], category="MACRO", parallel_safe=True)
class GetTreasuryYieldsHandler(ToolHandler):
    name = "get_treasury_yields"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_treasury_yields(args, session=session, executor=executor, **kwargs)


@register_tool("get_interest_rates", aliases=["get_interest_rate", "central_bank_rates"], category="MACRO", parallel_safe=True)
class GetInterestRatesHandler(ToolHandler):
    name = "get_interest_rates"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_interest_rates(args, session=session, executor=executor, **kwargs)


@register_tool("get_cot_report", aliases=["cot_report", "cot"], category="MACRO", parallel_safe=True)
class GetCotReportHandler(ToolHandler):
    name = "get_cot_report"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_cot_report(args, session=session, executor=executor, **kwargs)


@register_tool("get_vix", aliases=["vix", "vix_index"], category="MACRO", parallel_safe=True)
class GetVixHandler(ToolHandler):
    name = "get_vix"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_vix(args, session=session, executor=executor, **kwargs)


@register_tool("get_dxy", aliases=["dxy", "dollar_index"], category="MACRO", parallel_safe=True)
class GetDxyHandler(ToolHandler):
    name = "get_dxy"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_dxy(args, session=session, executor=executor, **kwargs)


@register_tool("get_fear_greed_index", aliases=["fear_greed", "get_fear_greed"], category="MACRO", parallel_safe=True)
class GetFearGreedIndexHandler(ToolHandler):
    name = "get_fear_greed_index"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_fear_greed_index(args, session=session, executor=executor, **kwargs)


@register_tool("get_economic_calendar", aliases=["get_economic_calendars", "get_calendar", "economic_calendar"], category="MACRO", parallel_safe=True)
class GetEconomicCalendarHandler(ToolHandler):
    name = "get_economic_calendar"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_economic_calendar(args, session=session, executor=executor, **kwargs)


@register_tool("get_economic_surprise", aliases=["economic_surprise"], category="MACRO", parallel_safe=True)
class GetEconomicSurpriseHandler(ToolHandler):
    name = "get_economic_surprise"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_economic_surprise(args, session=session, executor=executor, **kwargs)


@register_tool("get_precomputed_cot_signals", aliases=["cot_signals", "precomputed_cot", "get_cot_signals"], category="MACRO", parallel_safe=True)
class GetPrecomputedCotSignalsHandler(ToolHandler):
    name = "get_precomputed_cot_signals"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_precomputed_cot_signals(args, session=session, executor=executor, **kwargs)


@register_tool("get_surprise_summary", aliases=["surprise_summary", "economic_surprise_summary"], category="MACRO", parallel_safe=True)
class GetSurpriseSummaryHandler(ToolHandler):
    name = "get_surprise_summary"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_surprise_summary(args, session=session, executor=executor, **kwargs)


@register_tool("inspect_economic_report", aliases=["inspect_report", "decompose_report", "bedah_cpi", "bedah_nfp"], category="MACRO", parallel_safe=True)
class InspectEconomicReportHandler(ToolHandler):
    name = "inspect_economic_report"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_inspect_economic_report(args, session=session, executor=executor, **kwargs)


@register_tool("diff_central_bank_documents", aliases=["diff_cb_documents", "diff_fomc_minutes", "diff_fomc_statement"], category="MACRO", parallel_safe=True)
class DiffCentralBankDocumentsHandler(ToolHandler):
    name = "diff_central_bank_documents"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_diff_central_bank_documents(args, session=session, executor=executor, **kwargs)


@register_tool("get_macro_cross_report_synthesis", aliases=["macro_synthesis", "cross_report_synthesis"], category="MACRO", parallel_safe=True)
class GetMacroCrossReportSynthesisHandler(ToolHandler):
    name = "get_macro_cross_report_synthesis"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_macro_cross_report_synthesis(args, session=session, executor=executor, **kwargs)


@register_tool("get_g10_macro_divergence", aliases=["g10_divergence", "macro_divergence"], category="MACRO", parallel_safe=True)
class GetG10MacroDivergenceHandler(ToolHandler):
    name = "get_g10_macro_divergence"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_g10_macro_divergence(args, session=session, executor=executor, **kwargs)


@register_tool("get_fed_net_liquidity_and_stress", aliases=["fed_net_liquidity", "systemic_liquidity", "credit_stress"], category="MACRO", parallel_safe=True)
class GetFedNetLiquidityAndStressHandler(ToolHandler):
    name = "get_fed_net_liquidity_and_stress"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_fed_net_liquidity_and_stress(args, session=session, executor=executor, **kwargs)


@register_tool("get_treasury_auction_results", aliases=["treasury_auctions", "us_debt_auctions"], category="MACRO", parallel_safe=True)
class GetTreasuryAuctionResultsHandler(ToolHandler):
    name = "get_treasury_auction_results"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_treasury_auction_results(args, session=session, executor=executor, **kwargs)


@register_tool("get_ecb_qt_progress", aliases=["ecb_qt", "ecb_balance_sheet", "eurozone_qt"], category="MACRO", parallel_safe=True)
class GetECBQTProgressHandler(ToolHandler):
    name = "get_ecb_qt_progress"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_ecb_qt_progress(args, session=session, executor=executor, **kwargs)


@register_tool("get_global_pmi_trend", aliases=["global_pmi", "manufacturing_pmi", "pmi_trend"], category="MACRO", parallel_safe=True)
class GetGlobalPMITrendHandler(ToolHandler):
    name = "get_global_pmi_trend"
    category = "MACRO"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_global_pmi_trend(args, session=session, executor=executor, **kwargs)




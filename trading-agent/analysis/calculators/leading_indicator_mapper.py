# ==============================================================================
# File: analysis/calculators/leading_indicator_mapper.py
# ==============================================================================

"""
Macro Leading Indicator Mapper & Nowcasting Engine.
Maps high-frequency upstream leading indicators to subsequent major macro releases
(e.g., CPI/PPI -> PCE, ADP/Claims/JOLTS -> NFP, GDPNow -> GDP, PMI Sub-indices).
Evaluates nowcast vs consensus, falsification risks, and non-linear multi-asset transmission.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Calculators.LeadingIndicatorMapper")


@dataclass
class EvidencePoint:
    indicator_name: str
    observed_value: float
    benchmark_value: float
    direction: str  # "UPWARD", "DOWNWARD", "NEUTRAL"
    weight: float
    notes: str = ""


@dataclass
class NowcastResult:
    target_event: str
    nowcast_value: float
    consensus_value: float
    delta_vs_consensus: float
    projection_category: str  # "BEAT", "INLINE", "MISS"
    confidence: float  # 0.0 to 1.0
    evidence_chain: List[Dict[str, Any]] = field(default_factory=list)
    falsification_risks: List[str] = field(default_factory=list)
    transmission_map: Dict[str, Dict[str, str]] = field(default_factory=dict)
    nonlinear_context: List[str] = field(default_factory=list)


class LeadingIndicatorMapper:
    """
    Quantitative mapper translating upstream components to macro nowcast predictions.
    Supports inflation (PCE/CPI), labor market (NFP/Unemployment), growth (GDP), and PMI.
    """

    @staticmethod
    def nowcast_pce(
        cpi_core_mom: Optional[float] = None,
        ppi_core_mom: Optional[float] = None,
        ppi_airfares_mom: Optional[float] = None,
        ppi_portfolio_mgmt_mom: Optional[float] = None,
        cpi_shelter_mom: Optional[float] = None,
        consensus_core_pce: float = 0.2,
    ) -> NowcastResult:
        """
        Projects Core PCE MoM from CPI and PPI components.
        Core PCE differs from CPI because healthcare/portfolio mgmt come from PPI,
        and shelter has lower weight (~15-18% vs ~35-40% in CPI).
        """
        evidence = []
        base_estimate = consensus_core_pce
        adjustment = 0.0
        weights_sum = 0.0

        if cpi_core_mom is not None:
            # CPI provides general core goods baseline (weight 0.40)
            diff = cpi_core_mom - consensus_core_pce
            adj = diff * 0.40
            adjustment += adj
            weights_sum += 0.40
            evidence.append(EvidencePoint(
                indicator_name="Core CPI MoM",
                observed_value=cpi_core_mom,
                benchmark_value=consensus_core_pce,
                direction="UPWARD" if diff > 0.02 else ("DOWNWARD" if diff < -0.02 else "NEUTRAL"),
                weight=0.40,
                notes=f"Core goods & basic services input (diff: {diff:+.2f}%)"
            ))

        if ppi_core_mom is not None:
            # PPI core provides wholesale price pressures (weight 0.25)
            diff = ppi_core_mom - consensus_core_pce
            adj = diff * 0.25
            adjustment += adj
            weights_sum += 0.25
            evidence.append(EvidencePoint(
                indicator_name="Core PPI MoM",
                observed_value=ppi_core_mom,
                benchmark_value=consensus_core_pce,
                direction="UPWARD" if diff > 0.02 else ("DOWNWARD" if diff < -0.02 else "NEUTRAL"),
                weight=0.25,
                notes="Wholesale transmission to consumer prices"
            ))

        if ppi_airfares_mom is not None and ppi_portfolio_mgmt_mom is not None:
            # High-beta PCE specific PPI components (weight 0.20)
            ppi_specific_avg = (ppi_airfares_mom + ppi_portfolio_mgmt_mom) / 2.0
            diff = ppi_specific_avg - 0.0
            adj = diff * 0.20 * 0.1  # dampened beta
            adjustment += adj
            weights_sum += 0.20
            evidence.append(EvidencePoint(
                indicator_name="PPI PCE-Specific Components (Airfare & Portfolio Mgmt)",
                observed_value=round(ppi_specific_avg, 2),
                benchmark_value=0.0,
                direction="UPWARD" if ppi_specific_avg > 0.5 else ("DOWNWARD" if ppi_specific_avg < -0.5 else "NEUTRAL"),
                weight=0.20,
                notes="Direct inputs into BEA PCE computation with high variance"
            ))

        if cpi_shelter_mom is not None:
            # Shelter weighting dampener (weight 0.15)
            # If shelter is hot in CPI, PCE is relatively lower due to lower shelter weighting
            shelter_drag = (cpi_shelter_mom - 0.3) * -0.05
            adjustment += shelter_drag
            weights_sum += 0.15
            evidence.append(EvidencePoint(
                indicator_name="CPI Shelter Relative Weight Difference",
                observed_value=cpi_shelter_mom,
                benchmark_value=0.3,
                direction="DOWNWARD" if cpi_shelter_mom > 0.3 else "NEUTRAL",
                weight=0.15,
                notes="PCE gives only ~16% weight to housing vs ~35% in CPI"
            ))

        projected = round(base_estimate + adjustment, 2)
        delta = round(projected - consensus_core_pce, 2)

        if delta > 0.05:
            cat = "BEAT"
        elif delta < -0.05:
            cat = "MISS"
        else:
            cat = "INLINE"

        conf = min(0.92, max(0.40, weights_sum))

        risks = [
            "BEA seasonal residual adjustments in January/mid-year updates",
            "Non-market service imputations (financial services without explicit fees)",
            "Revision to previous month's personal income and disposable spending"
        ]

        trans = {
            "USD (DXY)": {
                "impact": "BULLISH / UPWARD" if cat == "BEAT" else ("BEARISH / DOWNWARD" if cat == "MISS" else "NEUTRAL / RANGEBOUND"),
                "rationale": "Hot PCE delays Fed rate cuts, keeping real rate differential high."
            },
            "XAUUSD (Gold)": {
                "impact": "BEARISH / DROP" if cat == "BEAT" else ("BULLISH / RALLY" if cat == "MISS" else "CHOPPY / VOLATILE"),
                "rationale": "High PCE increases US 10Y real yields, increasing gold opportunity cost."
            },
            "EURUSD": {
                "impact": "BEARISH / DOWNWARD" if cat == "BEAT" else ("BULLISH / UPWARD" if cat == "MISS" else "NEUTRAL"),
                "rationale": "Transatlantic policy divergence widens in favor of USD."
            },
            "US 10Y Yield": {
                "impact": "RISE / SPIKE" if cat == "BEAT" else ("FALL / RETRACE" if cat == "MISS" else "STEADY"),
                "rationale": "Bond market reprices terminal Fed Funds rate."
            }
        }

        nonlinear = [
            "If market already fully priced in a hot print (>85% Fed pause probability), a minor beat may trigger 'sell the fact' on USD.",
            "If PCE beats but Personal Spending MoM drops sharply into contraction (< -0.2%), stagflation fears may paradoxically pump Gold despite rising yields."
        ]

        return NowcastResult(
            target_event="Core PCE Deflator MoM",
            nowcast_value=projected,
            consensus_value=consensus_core_pce,
            delta_vs_consensus=delta,
            projection_category=cat,
            confidence=conf,
            evidence_chain=[e.__dict__ for e in evidence],
            falsification_risks=risks,
            transmission_map=trans,
            nonlinear_context=nonlinear
        )

    @staticmethod
    def nowcast_nfp(
        adp_change_k: Optional[float] = None,
        jobless_claims_4w_avg_k: Optional[float] = None,
        continuing_claims_k: Optional[float] = None,
        ism_mfg_employment: Optional[float] = None,
        ism_services_employment: Optional[float] = None,
        consensus_nfp_k: float = 175.0,
    ) -> NowcastResult:
        """
        Projects Non-Farm Payrolls (NFP) print from labor market leading indicators.
        """
        evidence = []
        base = consensus_nfp_k
        adjustment = 0.0
        weights_sum = 0.0

        if adp_change_k is not None:
            diff = (adp_change_k - consensus_nfp_k) * 0.35
            adjustment += diff
            weights_sum += 0.35
            evidence.append(EvidencePoint(
                indicator_name="ADP Private Employment",
                observed_value=adp_change_k,
                benchmark_value=consensus_nfp_k,
                direction="UPWARD" if adp_change_k > consensus_nfp_k else "DOWNWARD",
                weight=0.35,
                notes="Private payroll gauge (often directionally aligned, noisy on magnitude)"
            ))

        if jobless_claims_4w_avg_k is not None:
            # Normal baseline ~220k. Higher claims = lower payrolls
            claims_diff = (220.0 - jobless_claims_4w_avg_k) * 1.5
            adjustment += claims_diff
            weights_sum += 0.30
            evidence.append(EvidencePoint(
                indicator_name="Initial Jobless Claims (4-Week Moving Average)",
                observed_value=jobless_claims_4w_avg_k,
                benchmark_value=220.0,
                direction="UPWARD" if jobless_claims_4w_avg_k < 220.0 else "DOWNWARD",
                weight=0.30,
                notes="High-frequency layoff barometer during the survey reference week"
            ))

        if ism_services_employment is not None:
            # 50.0 is breakeven
            pmi_diff = (ism_services_employment - 50.0) * 4.0
            adjustment += pmi_diff
            weights_sum += 0.20
            evidence.append(EvidencePoint(
                indicator_name="ISM Services Employment Sub-Index",
                observed_value=ism_services_employment,
                benchmark_value=50.0,
                direction="UPWARD" if ism_services_employment > 50.0 else "DOWNWARD",
                weight=0.20,
                notes="Services sector represents ~80% of US employment base"
            ))

        projected = round(base + adjustment, 1)
        delta = round(projected - consensus_nfp_k, 1)

        if delta > 25.0:
            cat = "BEAT"
        elif delta < -25.0:
            cat = "MISS"
        else:
            cat = "INLINE"

        conf = min(0.90, max(0.35, weights_sum))

        risks = [
            "Net birth-death model seasonal distortions by BLS",
            "Severe weather disruptions or strike actions during reference week (week containing the 12th)",
            "Downside revisions to previous 2 months overshadowing current headline"
        ]

        trans = {
            "USD (DXY)": {
                "impact": "BULLISH" if cat == "BEAT" else ("BEARISH" if cat == "MISS" else "NEUTRAL"),
                "rationale": "Strong employment reduces immediate rate cut expectations."
            },
            "XAUUSD (Gold)": {
                "impact": "BEARISH / DROP" if cat == "BEAT" else ("BULLISH / SPIKE" if cat == "MISS" else "CHOP"),
                "rationale": "Gold suffers when real yields rally post-strong employment report."
            },
            "EURUSD": {
                "impact": "BEARISH" if cat == "BEAT" else ("BULLISH" if cat == "MISS" else "NEUTRAL"),
                "rationale": "Dollar liquidity demand spikes on labor resilience."
            }
        }

        nonlinear = [
            "Check Unemployment Rate (U3) and Average Hourly Earnings (AHE) MoM simultaneously: A strong headline NFP with rising unemployment (e.g. 4.1% -> 4.3%) and cold wages (< 0.2%) is net DOVISH for USD and BULLISH for Gold.",
            "Look for benchmark revisions: If current headline beats but prior months are revised down by > -50k, the initial algorithmic spike will rapidly reverse within 15 minutes."
        ]

        return NowcastResult(
            target_event="US Non-Farm Payrolls (NFP)",
            nowcast_value=projected,
            consensus_value=consensus_nfp_k,
            delta_vs_consensus=delta,
            projection_category=cat,
            confidence=conf,
            evidence_chain=[e.__dict__ for e in evidence],
            falsification_risks=risks,
            transmission_map=trans,
            nonlinear_context=nonlinear
        )

    @classmethod
    def evaluate_generic_release(
        cls,
        event_name: str,
        consensus_value: float,
        leading_indicators: List[Dict[str, Any]],
        falsification_risks: Optional[List[str]] = None,
        asset_class: str = "FX_METALS"
    ) -> NowcastResult:
        """
        Generic, asset-agnostic nowcasting evaluator for ANY macro release.
        Calculates weighted composite nowcast score, delta vs consensus, and transmission bias.
        """
        if not leading_indicators:
            return NowcastResult(
                target_event=event_name,
                nowcast_value=consensus_value,
                consensus_value=consensus_value,
                delta_vs_consensus=0.0,
                projection_category="INLINE",
                confidence=0.30,
                evidence_chain=[],
                falsification_risks=["No upstream leading indicator data available; consensus baseline used."],
                transmission_map={},
                nonlinear_context=["Market consensus is unhedged."]
            )

        total_weight = 0.0
        weighted_delta = 0.0
        evidence_chain = []

        for item in leading_indicators:
            name = item.get("name", "Unknown")
            obs = float(item.get("observed", 0.0))
            bench = float(item.get("benchmark", 0.0))
            w = float(item.get("weight", 1.0))
            notes = item.get("notes", "")

            diff = obs - bench
            weighted_delta += diff * w
            total_weight += w

            evidence_chain.append(EvidencePoint(
                indicator_name=name,
                observed_value=obs,
                benchmark_value=bench,
                direction="UPWARD" if diff > 0 else ("DOWNWARD" if diff < 0 else "NEUTRAL"),
                weight=w,
                notes=notes
            ).__dict__)

        avg_delta = weighted_delta / total_weight if total_weight > 0 else 0.0
        nowcast_val = round(consensus_value + avg_delta, 3)
        delta_vs_cons = round(nowcast_val - consensus_value, 3)

        tolerance = abs(consensus_value * 0.05) if consensus_value != 0 else 0.05
        if delta_vs_cons > tolerance:
            cat = "BEAT"
        elif delta_vs_cons < -tolerance:
            cat = "MISS"
        else:
            cat = "INLINE"

        confidence = round(min(0.95, max(0.40, total_weight / 3.0)), 2)

        trans = {
            "Target Base Currency": {
                "impact": "BULLISH / APPRECIATION" if cat == "BEAT" else ("BEARISH / DEPRECIATION" if cat == "MISS" else "RANGEBOUND"),
                "rationale": f"Higher {event_name} pushes domestic rate curve higher relative to peers."
            },
            "Gold / Counter Assets": {
                "impact": "BEARISH / RETRACEMENT" if cat == "BEAT" else ("BULLISH / EXTENSION" if cat == "MISS" else "CHOP"),
                "rationale": "Yield sensitivity and opportunity cost dynamics."
            }
        }

        nonlinear = [
            f"Asymmetric reaction risk: If {event_name} is already priced in by speculative futures positions, surprise delta impact will be dampened.",
            "Watch out for multi-speed transmission: Immediate 5-minute algorithmic order flow may violently fade if broader macro narrative contradicts the print."
        ]

        return NowcastResult(
            target_event=event_name,
            nowcast_value=nowcast_val,
            consensus_value=consensus_value,
            delta_vs_consensus=delta_vs_cons,
            projection_category=cat,
            confidence=confidence,
            evidence_chain=evidence_chain,
            falsification_risks=falsification_risks or ["Data revisions", "Seasonal smoothing bias", "Survey sample anomalies"],
            transmission_map=trans,
            nonlinear_context=nonlinear
        )

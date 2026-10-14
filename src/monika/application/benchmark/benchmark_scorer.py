"""
Deterministic Multi-Pillar Benchmark Scorer for Monika Trading Agents.
100% objective, mathematically rigorous, reproducible, zero-cost (no stochastic LLM judge).
Evaluates Stage 1 (Fundamental Brief) and Stage 2 (Per-Asset Execution EURUSD) outputs.
"""

from typing import Any, Dict, List, Optional
import re


def score_stage1_fundamental(payload: Optional[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates Stage 1 Fundamental Brief across 4 objective pillars (0 - 100):
    1. Factual Grounding (0 - 30 pts): Citations of actual data points in prefetch bundle.
    2. Falsifiability & Invalidation (0 - 25 pts): Precision of quantitative invalidation rules.
    3. Priced-In & Counter-Thesis (0 - 25 pts): Depth of market pricing and reversing arguments.
    4. Operational Efficiency (0 - 20 pts): Latency and token expenditure sanity.
    """
    breakdown: Dict[str, Any] = {}
    if not payload:
        return {
            "grounding_score": 0.0,
            "invalidation_score": 0.0,
            "priced_in_score": 0.0,
            "efficiency_score": 0.0,
            "total_score": 0.0,
            "breakdown": {"error": "No captured payload"},
        }

    narrative = str(payload.get("macro_narrative") or "")

    # -------------------------------------------------------------
    # 1. Factual Grounding (30 points)
    # Check citations of core macro indicators from synthetic bundle
    # -------------------------------------------------------------
    grounding_pts = 0.0
    grounding_checks = {
        "cites_dxy": bool(re.search(r"dxy|101\.|102\.|dollar index", narrative, re.I)),
        "cites_nfp_labor": bool(re.search(r"nfp|29k|29,000|non-farm|payrolls|unemployment|4\.2%", narrative, re.I)),
        "cites_treasury_yields": bool(
            re.search(r"10y|treasury|yield|3\.82|us-de|spread|\+144|gilts|4\.18", narrative, re.I)
        ),
        "cites_vix_sentiment": bool(re.search(r"vix|16\.7|fear & greed|sentiment", narrative, re.I)),
        "cites_fedwatch_rates": bool(re.search(r"fedwatch|82%|18%|hold|cut|target range|fomc", narrative, re.I)),
        "cites_energy_geopolitics": bool(
            re.search(r"hormuz|vessel|wti|oil|71\.|brent|opec|middle east", narrative, re.I)
        ),
    }
    for check_name, passed in grounding_checks.items():
        if passed:
            grounding_pts += 5.0
    breakdown["grounding"] = {"points": grounding_pts, "checks": grounding_checks}

    # -------------------------------------------------------------
    # 2. Falsifiability & Invalidation Precision (25 points)
    # Evaluate currency invalidation conditions (>= 40 chars, has numbers/levels)
    # -------------------------------------------------------------
    inval_pts = 0.0
    inval_conditions = payload.get("invalidation_conditions") or {}
    biases = payload.get("currency_bias") or {}

    non_neutral_currencies = [c for c, b in biases.items() if str(b).lower() not in ("neutral", "none")]
    valid_invals = 0
    total_expected = max(1, len(non_neutral_currencies))

    for curr in non_neutral_currencies:
        cond_text = str(inval_conditions.get(curr) or "")
        # Must be >= 40 chars and contain numbers/percentages/dates/levels
        has_min_len = len(cond_text) >= 40
        has_numeric = bool(re.search(r"\d+(\.\d+)?|%|bps", cond_text))
        if has_min_len and has_numeric:
            valid_invals += 1

    inval_ratio = valid_invals / total_expected
    inval_pts = round(inval_ratio * 25.0, 1)
    breakdown["invalidation"] = {
        "points": inval_pts,
        "valid_invalidation_count": valid_invals,
        "total_required": total_expected,
    }

    # -------------------------------------------------------------
    # 3. Priced-In & Counter-Thesis Rigor (25 points)
    # -------------------------------------------------------------
    priced_pts = 0.0
    priced_in = payload.get("priced_in_assessment") or {}
    counter_thesis = str(payload.get("strongest_counter_thesis") or "")

    # Sub-component 3a: Priced-in assessment completeness (12 pts)
    has_dominant_driver = len(str(priced_in.get("dominant_driver") or "")) >= 15
    has_valid_score = (
        isinstance(priced_in.get("priced_in_score"), (int, float)) and 1 <= priced_in["priced_in_score"] <= 10
    )
    has_sell_the_news = str(priced_in.get("sell_the_news_risk") or "").lower() in (
        "high",
        "medium",
        "low",
        "not_applicable",
    )

    if has_dominant_driver:
        priced_pts += 4.0
    if has_valid_score:
        priced_pts += 4.0
    if has_sell_the_news:
        priced_pts += 4.0

    # Sub-component 3b: Strongest counter thesis (13 pts)
    counter_len = len(counter_thesis)
    if counter_len >= 50:
        priced_pts += 7.0
        # Bonus for citing specific reversing level/catalyst in counter thesis
        if re.search(r"\d+(\.\d+)?|close|break|reversal|above|below", counter_thesis, re.I):
            priced_pts += 6.0
    elif counter_len >= 20:
        priced_pts += 4.0

    breakdown["priced_in_and_counter"] = {
        "points": priced_pts,
        "has_dominant_driver": has_dominant_driver,
        "has_valid_score": has_valid_score,
        "counter_thesis_length": counter_len,
    }

    # -------------------------------------------------------------
    # 4. Operational & Cost Efficiency (20 points)
    # -------------------------------------------------------------
    eff_pts = 0.0
    latency_s = float(meta.get("latency_s") or 0.0)
    # Latency: <= 60s -> 10 pts, linear decay to 0 at 600s
    if latency_s <= 60.0:
        lat_pts = 10.0
    elif latency_s >= 600.0:
        lat_pts = 0.0
    else:
        lat_pts = 10.0 * (1.0 - (latency_s - 60.0) / 540.0)
    eff_pts += round(lat_pts, 1)

    # Token sanity: < 40k tokens output/thinking -> 10 pts
    total_tokens = int(meta.get("input_tokens", 0)) + int(meta.get("output_tokens", 0))
    if total_tokens <= 25000:
        tok_pts = 10.0
    elif total_tokens <= 50000:
        tok_pts = 7.0
    else:
        tok_pts = 4.0
    eff_pts += tok_pts

    breakdown["efficiency"] = {
        "points": eff_pts,
        "latency_s": latency_s,
        "latency_points": round(lat_pts, 1),
        "total_tokens": total_tokens,
    }

    total_stage1 = round(grounding_pts + inval_pts + priced_pts + eff_pts, 1)
    return {
        "grounding_score": grounding_pts,
        "invalidation_score": inval_pts,
        "priced_in_score": priced_pts,
        "efficiency_score": eff_pts,
        "total_score": min(100.0, total_stage1),
        "breakdown": breakdown,
    }


def score_stage2_per_asset(
    payload: Optional[Dict[str, Any]], meta: Dict[str, Any], sizing_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates Stage 2 Per-Asset Primary Execution across 4 objective pillars (0 - 100):
    1. Risk & Mathematical Rigor (0 - 35 pts): SL/TP sides, R:R >= 1.3, reasonable ADR bounds.
    2. Structural Grounding & Confluence (0 - 25 pts): Entry tied to market structure, confluence.
    3. Decision Discipline & Invalidation (0 - 20 pts): Substantive rationale, invalidation price.
    4. Execution & Sizing Compliance (0 - 20 pts): Sizing passed RiskGate, latency efficiency.
    """
    breakdown: Dict[str, Any] = {}
    if not payload:
        return {
            "risk_math_score": 0.0,
            "structural_grounding_score": 0.0,
            "decision_discipline_score": 0.0,
            "execution_sizing_score": 0.0,
            "total_score": 0.0,
            "breakdown": {"error": "No captured payload"},
        }

    decision = str(payload.get("decision") or "").lower()

    # -------------------------------------------------------------
    # 1. Risk & Mathematical Rigor (35 points)
    # -------------------------------------------------------------
    risk_pts = 0.0
    risk_checks: Dict[str, Any] = {"decision": decision}

    if decision in ("buy", "sell"):
        entry_cond = payload.get("entry_condition")
        entry = (
            (entry_cond.get("price") if isinstance(entry_cond, dict) else None)
            or payload.get("entry_price")
            or payload.get("entry")
        )
        sl = payload.get("stop_loss")
        tp = payload.get("take_profit")

        # Check entry/SL/TP presence (5 pts)
        if entry is not None and sl is not None and tp is not None:
            risk_pts += 5.0
            entry, sl, tp = float(entry), float(sl), float(tp)

            # SL/TP Correct Side (15 pts)
            correct_side = (decision == "buy" and sl < entry < tp) or (decision == "sell" and tp < entry < sl)
            risk_checks["sl_tp_correct_side"] = correct_side
            if correct_side:
                risk_pts += 15.0

            # R:R Ratio >= 1.3 (10 pts)
            sl_dist = abs(entry - sl)
            tp_dist = abs(entry - tp)
            rr = (tp_dist / sl_dist) if sl_dist > 0 else 0.0
            risk_checks["rr_ratio"] = round(rr, 2)
            if rr >= 1.3:
                risk_pts += 10.0
            elif rr >= 1.0:
                risk_pts += 5.0

            # ADR Sanity (5 pts) - EURUSD standard daily range ~50-120 pips (0.0050 - 0.0120)
            if 0.0005 <= sl_dist <= 0.0150 and 0.0010 <= tp_dist <= 0.0250:
                risk_checks["adr_sanity"] = True
                risk_pts += 5.0
            else:
                risk_checks["adr_sanity"] = False
        else:
            risk_checks["missing_prices"] = True
    elif decision in ("wait", "avoid"):
        # For disciplined WAIT decisions:
        # Full risk credit if non-lazy, substantive rationale provided
        rationale = str(payload.get("rationale") or payload.get("reasoning") or "")
        risk_factors = payload.get("risk_factors") or []
        is_substantive = len(rationale) >= 40
        cites_risk = bool(risk_factors) or any(
            k in rationale.lower()
            for k in ["spread", "volatility", "confluence", "range", "adverse", "liquidity", "choppy", "fvg", "ob"]
        )
        risk_checks["wait_substantive"] = is_substantive
        risk_checks["wait_cites_risk"] = cites_risk

        if is_substantive and cites_risk:
            risk_pts = 35.0  # Full credit for well-justified risk avoidance
        elif is_substantive:
            risk_pts = 25.0
        else:
            risk_pts = 10.0

    breakdown["risk_and_math"] = {"points": risk_pts, "details": risk_checks}

    # -------------------------------------------------------------
    # 2. Structural Grounding & Confluence (25 points)
    # -------------------------------------------------------------
    struct_pts = 0.0
    rationale = str(payload.get("rationale") or payload.get("reasoning") or "")
    confluence = payload.get("confluence_score")

    # Confluence score present & calibrated (10 pts)
    if confluence is not None:
        try:
            c_val = float(confluence)
            if 1 <= c_val <= 10 or 0.0 <= c_val <= 1.0:
                struct_pts += 10.0
        except ValueError, TypeError:
            pass

    # Structural levels cited (OB, FVG, Liquidity, Swing, EMA) (15 pts)
    struct_matches = [
        kw
        for kw in [
            "order block",
            "ob",
            "fvg",
            "fair value",
            "liquidity",
            "swing",
            "ema",
            "break of structure",
            "bos",
            "choch",
            "discount",
            "premium",
        ]
        if kw in rationale.lower()
    ]
    struct_score = min(15.0, len(struct_matches) * 5.0)
    struct_pts += struct_score

    breakdown["structural_grounding"] = {
        "points": struct_pts,
        "confluence_score": confluence,
        "matched_concepts": struct_matches,
    }

    # -------------------------------------------------------------
    # 3. Decision Discipline & Invalidation (20 points)
    # -------------------------------------------------------------
    disc_pts = 0.0
    inval_price = payload.get("invalidation_price")
    inval_dir = payload.get("invalidation_direction")
    reeval = payload.get("reevaluation_trigger")

    if inval_price is not None and inval_dir is not None:
        disc_pts += 10.0
    if reeval:
        disc_pts += 10.0

    breakdown["decision_discipline"] = {
        "points": disc_pts,
        "has_invalidation_level": inval_price is not None,
        "has_reevaluation_trigger": bool(reeval),
    }

    # -------------------------------------------------------------
    # 4. Execution & Sizing Compliance (20 points)
    # -------------------------------------------------------------
    exec_pts = 0.0
    latency_s = float(meta.get("latency_s") or 0.0)
    if latency_s <= 60.0:
        lat_pts = 10.0
    elif latency_s >= 600.0:
        lat_pts = 0.0
    else:
        lat_pts = 10.0 * (1.0 - (latency_s - 60.0) / 540.0)
    exec_pts += round(lat_pts, 1)

    # Sizing success: suggested_lots > 0 or clean wait
    suggested_lots = (sizing_info or {}).get("suggested_lots")
    if decision in ("buy", "sell"):
        if suggested_lots is not None and suggested_lots > 0:
            exec_pts += 10.0
        elif payload.get("stop_loss"):
            exec_pts += 8.0  # Sizing computable
    else:
        exec_pts += 10.0  # Wait decision does not require sizing

    breakdown["execution_and_sizing"] = {
        "points": exec_pts,
        "latency_s": latency_s,
        "suggested_lots": suggested_lots,
    }

    total_stage2 = round(risk_pts + struct_pts + disc_pts + exec_pts, 1)
    return {
        "risk_math_score": risk_pts,
        "structural_grounding_score": struct_pts,
        "decision_discipline_score": disc_pts,
        "execution_sizing_score": exec_pts,
        "total_score": min(100.0, total_stage2),
        "breakdown": breakdown,
    }


def compute_composite_benchmark_score(stage1_score: float, stage2_score: float) -> float:
    """
    Weighted composite benchmark score:
    40% Stage 1 (Macro Framework) + 60% Stage 2 (Per-Asset Execution & Risk Protection).
    """
    return round((0.40 * stage1_score) + (0.60 * stage2_score), 1)


def generate_leaderboard_data(
    stage1_results: List[Dict[str, Any]], stage2_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merges Stage 1 and Stage 2 benchmark outputs and scores each model deterministically.
    Returns ranked leaderboard list from rank 1 to N.
    """
    s1_map = {r.get("name"): r for r in stage1_results}
    s2_map = {r.get("name"): r for r in stage2_results}

    all_names = list(dict.fromkeys(list(s1_map.keys()) + list(s2_map.keys())))
    leaderboard = []

    for name in all_names:
        s1 = s1_map.get(name, {})
        s2 = s2_map.get(name, {})
        disp_name = s1.get("display_name") or s2.get("display_name") or name

        # Compute Stage 1 Score
        s1_eval = score_stage1_fundamental(s1.get("captured_payload"), s1)
        s1_total = s1_eval["total_score"]

        # Compute Stage 2 Score
        s2_payload = s2.get("captured_payload")
        s2_eval = score_stage2_per_asset(s2_payload, s2, s2.get("sizing_result"))
        s2_total = s2_eval["total_score"]

        # Composite Score
        composite = compute_composite_benchmark_score(s1_total, s2_total)

        total_latency = round(float(s1.get("latency_s", 0)) + float(s2.get("latency_s", 0)), 1)
        total_cost = round(float(s1.get("cost_usd", 0)) + float(s2.get("cost_usd", 0)), 4)

        leaderboard.append(
            {
                "name": name,
                "display_name": disp_name,
                "composite_score": composite,
                "stage1_score": s1_total,
                "stage2_score": s2_total,
                "stage1_eval": s1_eval,
                "stage2_eval": s2_eval,
                "decision_s2": (s2_payload or {}).get("decision", "n/a"),
                "total_latency_s": total_latency,
                "total_cost_usd": total_cost,
            }
        )

    # Sort descending by composite score, then total latency ascending
    leaderboard.sort(key=lambda x: (x["composite_score"], -x["total_latency_s"]), reverse=True)

    for rank, entry in enumerate(leaderboard, 1):
        entry["rank"] = rank

    return leaderboard


def generate_leaderboard_markdown(leaderboard: List[Dict[str, Any]]) -> str:
    """Formats the ranked leaderboard into clean GitHub-flavored Markdown."""
    lines = [
        "# Monika Frontier LLM Trading Benchmark — Leaderboard",
        "",
        "> **Methodology**: Deterministic Multi-Pillar Scoring (0 - 100) combining Stage 1 (Macro Framework, 40%) and Stage 2 (Asset Execution & Risk Math, 60%). 100% objective, mathematically verified, zero stochastic LLM bias.",
        "",
        "| Rank | Model | Composite Score | Stage 1 (Macro) | Stage 2 (Execution) | Decision (EURUSD) | Total Latency | Cost (USD) |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for item in leaderboard:
        medal = (
            "🥇 "
            if item["rank"] == 1
            else "🥈 "
            if item["rank"] == 2
            else "🥉 "
            if item["rank"] == 3
            else f"{item['rank']}. "
        )
        lines.append(
            f"| {medal} | **{item['display_name']}** | **{item['composite_score']:.1f}** | {item['stage1_score']:.1f} | {item['stage2_score']:.1f} | `{item['decision_s2'].upper()}` | {item['total_latency_s']}s | ${item['total_cost_usd']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## Scoring Pillar Breakdown",
            "",
            "### Stage 1: Fundamental Macro Analysis (Max 100 pts)",
            "- **Grounding (30 pts)**: Explicit citations of DXY, NFP (+29k), Treasury Yields (10Y 3.82%), VIX (16.7), FedWatch (82% Hold), and Energy Catalysts.",
            "- **Invalidation (25 pts)**: Precision and falsifiability of per-currency invalidation conditions (>= 40 chars with concrete numerical levels/price/dates).",
            "- **Priced-In & Counter-Thesis (25 pts)**: Completeness of 4-method priced-in assessment and substantive contrary thesis (>= 50 chars).",
            "- **Efficiency (20 pts)**: Latency under 600s budget and non-runaway token consumption.",
            "",
            "### Stage 2: Per-Asset Execution EURUSD (Max 100 pts)",
            "- **Risk & Math Compliance (35 pts)**: Mathematically correct SL/TP side relative to entry, R:R >= 1.3, and ADR boundary compliance.",
            "- **Structural Confluence (25 pts)**: Order Block / FVG / Liquidity level citations in rationale and valid confluence score.",
            "- **Decision Discipline (20 pts)**: Quantitative invalidation levels and re-evaluation trigger presence.",
            "- **Execution & Sizing (20 pts)**: Clean lot sizing execution via RiskGate and operational latency efficiency.",
            "",
        ]
    )

    return "\n".join(lines)

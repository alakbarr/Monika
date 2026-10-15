# ==============================================================================
# File: graph/nodes/risk/proposal_notifier.py
# Monika Telegram Proposal Notification Dispatcher Sub-Node
# ==============================================================================

"""
Formats and dispatches top-down trade proposal notifications to Telegram operators
with interactive inline keyboard buttons (Approve/Reject) for human-in-the-loop validation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Graph.Risk.ProposalNotifier")


def _format_proposal_card(sym: str, ana: Any, brief: Optional[Any]) -> str:
    """
    Constructs a top-down structured trade proposal message for Telegram operators.
    Encompasses:
      1. Execution Parameters & Risk:Reward
      2. Macro & Sentiment context (Fundamental Brief)
      3. Technical Triggers & Structure
      4. Quantitative Strategy, Historical Pattern & Backtest Edge
    """
    direction = str(getattr(ana, "decision", "UNKNOWN") or "UNKNOWN").upper()
    dir_emoji = "🟢" if direction == "BUY" else "🔴"
    confidence = float(getattr(ana, "confidence", 0.0) or 0.0)

    # 1. Entry, SL, TP, and Risk:Reward calculation
    entry_raw = getattr(ana, "entry_zone", "market") or "market"
    entry_val: Optional[float] = None
    price_at_ana = getattr(ana, "price_at_analysis", None)
    if price_at_ana is not None:
        try:
            entry_val = float(price_at_ana)
        except ValueError, TypeError:
            pass

    if entry_val is None and isinstance(entry_raw, str) and "price" in entry_raw:
        try:
            ez_dict = json.loads(entry_raw)
            if isinstance(ez_dict, dict) and "price" in ez_dict:
                entry_val = float(ez_dict["price"])
        except Exception:
            pass

    sl_raw = getattr(ana, "stop_loss", None)
    tp_raw = getattr(ana, "take_profit", None)
    sl_val: Optional[float] = float(sl_raw) if sl_raw is not None else None
    tp_val: Optional[float] = float(tp_raw) if tp_raw is not None else None

    rr_str = ""
    pip_factor = 100.0 if "JPY" in sym.upper() else 10000.0
    sl_pips_str = ""
    tp_pips_str = ""

    if entry_val is not None and sl_val is not None:
        risk_dist = abs(entry_val - sl_val)
        sl_pips = risk_dist * pip_factor
        sl_pips_str = f" ({sl_pips:.1f} pips)"
        if tp_val is not None:
            reward_dist = abs(entry_val - tp_val)
            tp_pips = reward_dist * pip_factor
            tp_pips_str = f" ({tp_pips:.1f} pips)"
            if risk_dist > 0:
                rr_ratio = reward_dist / risk_dist
                rr_str = f" | <b>R:R:</b> 1:{rr_ratio:.2f}"

    entry_display = f"{entry_val:.5f}" if entry_val is not None else str(entry_raw)
    sl_display = f"{sl_val:.5f}{sl_pips_str}" if sl_val is not None else "N/A"
    tp_display = f"{tp_val:.5f}{tp_pips_str}" if tp_val is not None else "N/A"

    # 2. Macro & Sentiment context
    macro_lines: List[str] = []
    if brief:
        regime = getattr(brief, "macro_regime", "") or "Mixed / Data Dependent"
        sentiment = (getattr(brief, "risk_sentiment", "") or "Neutral").upper()
        macro_lines.append(f"• <b>Sentimen & Rezim:</b> {sentiment} (<code>{regime}</code>)")

        bias = getattr(brief, "currency_bias", {}) or {}
        if len(sym) >= 6:
            base_cur = sym[:3].upper()
            quote_cur = sym[3:6].upper()
            base_bias = str(bias.get(base_cur, "neutral")).capitalize()
            quote_bias = str(bias.get(quote_cur, "neutral")).capitalize()
            macro_lines.append(f"• <b>Bias Valuta:</b> {base_cur} [{base_bias}] vs {quote_cur} [{quote_bias}]")
        elif bias:
            sym_bias = str(bias.get(sym.upper(), "neutral")).capitalize()
            macro_lines.append(f"• <b>Bias Aset:</b> {sym} [{sym_bias}]")

        narrative = getattr(brief, "macro_narrative", "") or ""
        if narrative:
            first_sentence = narrative.split("\n")[0].split(". ")[0].strip()
            if len(first_sentence) > 160:
                first_sentence = first_sentence[:157] + "..."
            macro_lines.append(f"• <b>Faktor Fundamental:</b> {first_sentence}.")
    else:
        macro_lines.append("• <b>Makro:</b> Sinyal quant intraday (kondisi makro tidak membatasi).")

    macro_section = "\n".join(macro_lines)

    # 3. Technical Trigger & Structure
    tech_lines: List[str] = []
    clean_rationale = (getattr(ana, "rationale", "") or "").strip()
    if clean_rationale:
        parts = clean_rationale.split(" | [Arbitrator:")
        primary_tech = parts[0].strip()
        tech_lines.append(f"• <b>Pemicu Setup:</b> {primary_tech}")

    conf_factors_json = getattr(ana, "confluence_factors_json", None)
    if conf_factors_json:
        try:
            factors = json.loads(conf_factors_json)
            if isinstance(factors, list) and factors:
                tech_lines.append(f"• <b>Konfluensi Indikator:</b> {', '.join(str(f) for f in factors)}")
        except Exception:
            pass

    inval = getattr(ana, "invalidation", None)
    if inval:
        tech_lines.append(f"• <b>Invalidasi Level:</b> <code>{inval}</code>")

    tech_section = "\n".join(tech_lines) if tech_lines else f"• {clean_rationale}"

    # 4. Strategy & Edge Backtest
    strategy_id = getattr(ana, "source_strategy_id", None) or "quant_strategy"
    dec_source = getattr(ana, "decision_source", None) or "SignalArbitrator"
    edge_lines = [
        f"• <b>Model Strategi:</b> <code>{strategy_id}</code>",
        f"• <b>Arbitrase Sinyal:</b> {dec_source}",
        "• <b>Edge & Validasi Pola:</b> Mean-reversion statistik saat harga menembus band ATR ekstrem dengan konfirmasi penolakan sumbu lilin (rejection wick).",
    ]
    edge_section = "\n".join(edge_lines)

    return (
        f"<b>[PROPOSAL TRANSAKSI] {dir_emoji} {sym} — {direction}</b>\n\n"
        f"<b>Eksekusi & Parameter:</b>\n"
        f"• <b>Aksi:</b> {direction} (Keyakinan: {confidence:.0%})\n"
        f"• <b>Entry:</b> <code>{entry_display}</code>\n"
        f"• <b>Stop Loss:</b> <code>{sl_display}</code>\n"
        f"• <b>Take Profit:</b> <code>{tp_display}</code>{rr_str}\n\n"
        f"🏛 <b>Faktor Makro & Sentimen:</b>\n"
        f"{macro_section}\n\n"
        f"📊 <b>Konfirmasi Teknikal:</b>\n"
        f"{tech_section}\n\n"
        f"🧬 <b>Kuantitatif, Pola & Backtest:</b>\n"
        f"{edge_section}\n\n"
        f"<i>Silakan tinjau dan klik tombol di bawah untuk memutuskan.</i>"
    )


async def send_proposal_notifications(actionable: List[Tuple[str, Dict[str, Any]]]) -> None:
    """
    Constructs top-down Telegram HTML cards with interactive inline buttons
    and dispatches trade proposal alerts to operators.
    """
    if not actionable:
        return

    try:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import AssetAnalysis, FundamentalBrief
        from monika.infrastructure.infra.notifier import AgentNotifier

        notifier = AgentNotifier()
        for sym, r in actionable:
            analysis_id = r.get("analysis_id")
            if not analysis_id:
                continue

            async with get_session() as session:
                ana = (
                    await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))
                ).scalar_one_or_none()
                if not ana:
                    continue

                brief = None
                if getattr(ana, "brief_id", None):
                    brief = (
                        await session.execute(select(FundamentalBrief).where(FundamentalBrief.id == ana.brief_id))
                    ).scalar_one_or_none()
                if not brief:
                    brief = (
                        await session.execute(
                            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                        )
                    ).scalar_one_or_none()

            msg = _format_proposal_card(sym, ana, brief)
            keyboard = AgentNotifier.build_trade_proposal_keyboard(analysis_id)
            await notifier.send_proposal(msg, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"[ProposalNotifier] Failed to send trade proposal notification: {e}", exc_info=True)

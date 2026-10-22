import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.graph.nodes.risk.proposal_notifier import (
    _calculate_pip_factor,
    _clean_macro_narrative,
    _format_execution_card,
    _format_proposal_card,
    send_proposal_notifications,
)
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier


def test_calculate_pip_factor():
    """Verify pip scale factors across diverse asset classes."""
    assert _calculate_pip_factor("EURUSD") == 10000.0
    assert _calculate_pip_factor("GBPUSD") == 10000.0
    assert _calculate_pip_factor("USDJPY") == 100.0
    assert _calculate_pip_factor("EURJPY") == 100.0
    assert _calculate_pip_factor("XAUUSD") == 10.0
    assert _calculate_pip_factor("GOLD") == 10.0
    assert _calculate_pip_factor("XAGUSD") == 100.0
    assert _calculate_pip_factor("BTCUSD") == 1.0
    assert _calculate_pip_factor("ETHUSD") == 1.0
    assert _calculate_pip_factor("US30") == 1.0
    assert _calculate_pip_factor("NAS100") == 1.0


def test_clean_macro_narrative():
    """Verify macro narrative cleaner strips Markdown headings and extracts substantive text."""
    # Heading with numbered prefix must not reduce to '### 1.'
    narrative_with_header = (
        "### 1. Macro Regime & Cross-Asset Sentiment\n"
        "US core disinflation stalls while labor prints soft revisions. The Fed remains data-dependent.\n\n"
        "### 2. Monetary Policy\nRates unchanged."
    )
    cleaned = _clean_macro_narrative(narrative_with_header)
    assert cleaned.startswith("US core disinflation stalls while labor prints soft revisions.")
    assert "### 1." not in cleaned
    assert "#" not in cleaned

    # Plain text narrative
    narrative_plain = "Global growth slows with divergent central bank expectations."
    assert _clean_macro_narrative(narrative_plain) == narrative_plain

    # Empty narrative fallback
    assert _clean_macro_narrative("") == "Macro baseline neutral across assets."


def test_format_proposal_card_llm_verbatim_zero_drift():
    """Verify that LLM Stage 2 proposals display institutional English without emojis or drift."""
    mock_brief = MagicMock()
    mock_brief.id = 101
    mock_brief.macro_regime = "DATA_DEPENDENT_STAGNATION"
    mock_brief.risk_sentiment = "mixed"
    mock_brief.currency_bias = {"GBP": "bullish", "USD": "bearish"}
    mock_brief.macro_narrative = "US core disinflation stalls while labor prints soft revisions."

    llm_rationale_text = (
        "1. Macro: BoE hawkish divergence vs Fed supports long bias.\n"
        "2. Technical: H4 FVG filled at 1.3280 with liquidity sweep. H1 rejection confirms entry.\n"
        "3. Edge: 6-factor confluence validating 1:1.62 R:R."
    )

    mock_ana = MagicMock()
    mock_ana.symbol = "GBPUSD"
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.60
    mock_ana.entry_zone = json.dumps({"type": "market", "price": 1.32675})
    mock_ana.price_at_analysis = 1.32675
    mock_ana.stop_loss = 1.32962
    mock_ana.take_profit = 1.32210
    mock_ana.rationale = llm_rationale_text
    mock_ana.confluence_factors_json = json.dumps(["rsi_exhaustion", "h1_atr_band_penetration"])
    mock_ana.invalidation = "Close H1 above 1.32962"
    mock_ana.source_strategy_id = None
    mock_ana.decision_source = "stage2_per_asset"
    mock_ana.debate_verdict = "Consensus reached for short setup on liquidity sweep."
    mock_ana.debate_bear_dissent = None

    card = _format_proposal_card("GBPUSD", mock_ana, mock_brief)

    # Clean institutional English headers
    assert "[TRADE PROPOSAL] GBPUSD — SELL" in card
    assert "<b>Rationale:</b>\n" in card
    assert llm_rationale_text in card
    assert "Debate Consensus:</b> Consensus reached for short setup" in card
    assert "Close H1 above 1.32962" in card

    # No unprofessional emojis or slop
    for banned in ("🟢", "🔴", "🧠", "🏛", "🤖", "🧬", "Analisis Langsung AI"):
        assert banned not in card

    # Macro & Parameters displayed honestly
    assert "<b>Macro & Sentiment Context:</b>" in card
    assert "Sentiment & Regime #101:</b> MIXED (<code>DATA_DEPENDENT_STAGNATION</code>)" in card
    assert "GBP [Bullish] vs USD [Bearish]" in card
    assert "R:R:</b> 1:1.62" in card
    assert "/approve" not in card


def test_format_proposal_card_quant():
    """Verify that quantitative strategy proposals display the strategy signal and factor family."""
    mock_brief = MagicMock()
    mock_brief.id = 326
    mock_brief.macro_regime = "DATA_DEPENDENT_STAGNATION"
    mock_brief.risk_sentiment = "mixed"
    mock_brief.currency_bias = {"GBP": "bullish", "USD": "bearish"}
    mock_brief.macro_narrative = "US core disinflation stalls while labor prints soft revisions."

    mock_ana = MagicMock()
    mock_ana.symbol = "GBPUSD"
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.60
    mock_ana.entry_zone = json.dumps({"type": "market", "price": 1.32675})
    mock_ana.price_at_analysis = 1.32675
    mock_ana.stop_loss = 1.32962
    mock_ana.take_profit = 1.32210
    mock_ana.rationale = (
        "GBPUSD ATR exhaustion sell signal. High (1.32757) penetrated upper band (1.32757) with RSI at 81.75. "
        "Rejection wick confirmed. | [Arbitrator: quant]"
    )
    mock_ana.confluence_factors_json = json.dumps(["rsi_exhaustion", "h1_atr_band_penetration"])
    mock_ana.invalidation = "Close H1 above 1.32962"
    mock_ana.source_strategy_id = "alpha_gbpusd_4947d0"
    mock_ana.decision_source = "SignalArbitrator"

    card = _format_proposal_card("GBPUSD", mock_ana, mock_brief)

    assert "[TRADE PROPOSAL] GBPUSD — SELL" in card
    assert "<b>Rationale:</b>" in card
    assert "Signal Trigger (<code>alpha_gbpusd_4947d0</code>):</b> GBPUSD ATR exhaustion sell signal" in card
    assert "Factor Family:" in card
    assert "R:R:</b> 1:1.62" in card
    assert "/approve" not in card


def test_format_proposal_card_with_banner_notice():
    """Verify that fallback proposals render the bypass reason notice cleanly."""
    mock_ana = MagicMock()
    mock_ana.symbol = "XAUUSD"
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.51
    mock_ana.entry_zone = "market"
    mock_ana.price_at_analysis = 4173.38
    mock_ana.stop_loss = 4204.76
    mock_ana.take_profit = 4110.78
    mock_ana.rationale = "Gold ATR upper band rejection"
    mock_ana.source_strategy_id = "alpha_xauusd_3af460"
    mock_ana.decision_source = "edge_registry"
    mock_ana.confluence_factors_json = None
    mock_ana.invalidation = None

    notice = "Auto-execution bypassed: Confidence (51%) below automated threshold (60%)."
    card = _format_proposal_card("XAUUSD", mock_ana, None, banner_notice=notice)

    assert "[TRADE PROPOSAL] XAUUSD — SELL" in card
    assert f"<i>Notice: {notice}</i>" in card
    assert "Review parameters and select an action below." in card


def test_format_execution_card():
    """Verify that automated execution cards present institutional parameters without buttons."""
    mock_brief = MagicMock()
    mock_brief.id = 335
    mock_brief.macro_regime = "STAGFLATIONARY_PRESSURE"
    mock_brief.risk_sentiment = "risk_off"
    mock_brief.currency_bias = {"XAU": "bullish", "USD": "bearish"}
    mock_brief.macro_narrative = "US core disinflation stalled while labor revisions weakened."

    mock_ana = MagicMock()
    mock_ana.symbol = "XAUUSD"
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.65
    mock_ana.entry_zone = json.dumps({"type": "market", "price": 4173.38})
    mock_ana.price_at_analysis = 4173.38
    mock_ana.stop_loss = 4204.76962
    mock_ana.take_profit = 4110.78
    mock_ana.rationale = "Price exhausted upwards: distance 33.88 > threshold 33.53 | [Arbitrator: quant]"
    mock_ana.confluence_factors_json = json.dumps(["rsi_exhaustion", "h1_atr_band_penetration"])
    mock_ana.invalidation = "Strategy exit: alpha_xauusd_3af460"
    mock_ana.source_strategy_id = "alpha_xauusd_3af460"
    mock_ana.decision_source = "edge_registry"

    mock_exec_res = MagicMock()
    mock_exec_res.executed = True
    mock_exec_res.mt5_ticket = 98765432
    mock_exec_res.executed_lots = 0.05
    mock_exec_res.executed_price = 4173.38
    mock_exec_res.risk_checks_passed = ["drawdown", "exposure", "volatility", "sizing"]
    mock_sizing = MagicMock()
    mock_sizing.risk_pct = 0.8
    mock_exec_res.sizing = mock_sizing

    card = _format_execution_card("XAUUSD", mock_ana, mock_brief, mock_exec_res)

    assert "<b>[AUTO-EXECUTION] XAUUSD — SELL</b>" in card
    assert "Broker Status:</b> Filled on MT5 (Ticket: <code>98765432</code>)" in card
    assert "0.05 lots (Risk: 0.8% equity)" in card
    assert "4173.38000" in card
    # Gold pip calculation: ~31.38 points = 313.9 pips
    assert "313.9 pips" in card
    assert "626.0 pips" in card
    assert "R:R:</b> 1:1.99" in card

    # Sections
    assert "<b>Rationale:</b>" in card
    assert "alpha_xauusd_3af460" in card
    assert "<b>Macro & Sentiment Context:</b>" in card
    assert "Sentiment & Regime #335:</b> RISK_OFF (<code>STAGFLATIONARY_PRESSURE</code>)" in card
    assert "XAU [Bullish] vs USD [Bearish]" in card
    assert "US core disinflation stalled while labor revisions weakened." in card
    assert "<b>RiskGate Safeguards:</b>" in card
    assert "4/4 checks passed" in card
    assert "/close 98765432" in card

    # No emojis
    for banned in ("🟢", "🔴", "🧠", "🏛", "🤖", "🧬"):
        assert banned not in card


def test_build_trade_proposal_keyboard():
    kb = AgentNotifier.build_trade_proposal_keyboard("2126")
    assert kb is not None
    assert len(kb.inline_keyboard) == 1
    row = kb.inline_keyboard[0]
    assert len(row) == 2
    btn_approve = row[0]
    btn_reject = row[1]

    assert "Approve" in btn_approve.text
    assert btn_approve.callback_data == "confirm:2126"
    assert "Reject" in btn_reject.text
    assert btn_reject.callback_data == "reject:2126"


@pytest.mark.asyncio
async def test_send_proposal_notifications_dispatches_with_markup():
    mock_ana = MagicMock()
    mock_ana.id = 2126
    mock_ana.symbol = "GBPUSD"
    mock_ana.decision = "sell"
    mock_ana.confidence = 0.60
    mock_ana.price_at_analysis = 1.32675
    mock_ana.stop_loss = 1.32962
    mock_ana.take_profit = 1.32210
    mock_ana.rationale = "GBPUSD ATR exhaustion sell signal."
    mock_ana.brief_id = None
    mock_ana.confluence_factors_json = None
    mock_ana.invalidation = None
    mock_ana.source_strategy_id = "alpha_gbpusd_4947d0"
    mock_ana.decision_source = "quant"

    mock_session = AsyncMock()
    mock_result_ana = MagicMock()
    mock_result_ana.scalar_one_or_none.return_value = mock_ana

    mock_result_brief = MagicMock()
    mock_result_brief.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [mock_result_ana, mock_result_brief]

    actionable = [("GBPUSD", {"analysis_id": 2126, "decision": "sell", "confidence": 0.60})]

    with (
        patch("monika.infrastructure.database.db.get_session") as mock_get_session,
        patch("monika.infrastructure.notifications.telegram_notifier.AgentNotifier") as mock_notifier_cls,
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        mock_notifier = MagicMock()
        mock_notifier.send_proposal = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier
        mock_notifier_cls.build_trade_proposal_keyboard = AgentNotifier.build_trade_proposal_keyboard

        await send_proposal_notifications(actionable)

        assert mock_notifier.send_proposal.called
        call_args = mock_notifier.send_proposal.call_args
        msg = call_args.args[0]
        reply_markup = call_args.kwargs.get("reply_markup")

        assert "GBPUSD — SELL" in msg
        assert reply_markup is not None
        assert reply_markup.inline_keyboard[0][0].callback_data == "confirm:2126"

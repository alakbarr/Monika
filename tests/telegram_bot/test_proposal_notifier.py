import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.graph.nodes.risk.proposal_notifier import (
    _format_proposal_card,
    send_proposal_notifications,
)
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier


def test_format_proposal_card_llm_verbatim_zero_drift():
    """Verify that LLM Stage 2 proposals display the authentic verbatim rationale without drift."""
    mock_brief = MagicMock()
    mock_brief.id = 101
    mock_brief.macro_regime = "DATA_DEPENDENT_STAGNATION"
    mock_brief.risk_sentiment = "mixed"
    mock_brief.currency_bias = {"GBP": "bullish", "USD": "bearish"}
    mock_brief.macro_narrative = "US core disinflation stalls while labor prints soft revisions."

    llm_rationale_text = (
        "1. Makro: Divergensi BoE hawkish vs Fed dovish mendukung bias long, namun DXY rebound dari support D1.\n"
        "2. Teknikal: H4 FVG terisi di 1.3280 dengan sweep liquidity Asia High. Rejection candle H1 mengonfirmasi entry.\n"
        "3. Edge: Konfluensi 6 faktor dengan validasi rasio R:R 1:1.62."
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

    # Verbatim AI rationale displayed directly under clean Rationale heading
    assert "<b>Rationale:</b>\n" in card
    assert "Analisis Langsung AI" not in card
    assert "🧠" not in card
    assert "🏛" not in card
    assert llm_rationale_text in card
    assert "Konsensus Debat:</b> Consensus reached for short setup" in card
    assert "Close H1 above 1.32962" in card

    # Macro & Parameters displayed honestly
    assert "<b>Konteks Makro & Sentimen:</b>" in card
    assert "Sentimen & Rezim #101:</b> MIXED (<code>DATA_DEPENDENT_STAGNATION</code>)" in card
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

    assert "<b>Rationale:</b>" in card
    assert "Logika Sinyal Kuantitatif" not in card
    assert "🤖" not in card
    assert "🏛" not in card
    assert "Pemicu Sinyal (<code>alpha_gbpusd_4947d0</code>):</b> GBPUSD ATR exhaustion sell signal" in card
    assert "Keluarga Faktor:" in card
    assert "R:R:</b> 1:1.62" in card
    assert "/approve" not in card


def test_build_trade_proposal_keyboard():
    kb = AgentNotifier.build_trade_proposal_keyboard("2126")
    assert kb is not None
    assert len(kb.inline_keyboard) == 1
    row = kb.inline_keyboard[0]
    assert len(row) == 2
    btn_approve = row[0]
    btn_reject = row[1]

    assert "Setujui" in btn_approve.text
    assert btn_approve.callback_data == "confirm:2126"
    assert "Tolak" in btn_reject.text
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
        patch("monika.infrastructure.infra.notifier.AgentNotifier") as mock_notifier_cls,
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
        assert reply_markup.inline_keyboard[0][1].callback_data == "reject:2126"

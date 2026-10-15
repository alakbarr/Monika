import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.graph.nodes.risk.proposal_notifier import (
    _format_proposal_card,
    send_proposal_notifications,
)
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier


def test_format_proposal_card_top_down():
    mock_brief = MagicMock()
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

    # 1. Structure Assertions
    assert "[PROPOSAL TRANSAKSI] 🔴 GBPUSD — SELL" in card
    assert "• <b>Aksi:</b> SELL (Keyakinan: 60%)" in card
    assert "1.32675" in card
    assert "1.32962" in card
    assert "1.32210" in card
    assert "R:R:</b> 1:1.62" in card

    # 2. Top-down Macro & Sentiment
    assert "Faktor Makro & Sentimen:" in card
    assert "MIXED" in card
    assert "DATA_DEPENDENT_STAGNATION" in card
    assert "GBP [Bullish] vs USD [Bearish]" in card
    assert "US core disinflation stalls" in card

    # 3. Technical Confirmation
    assert "Konfirmasi Teknikal:" in card
    assert "Pemicu Setup:</b> GBPUSD ATR exhaustion sell signal" in card
    assert "rsi_exhaustion, h1_atr_band_penetration" in card
    assert "Close H1 above 1.32962" in card

    # 4. Quantitative & Edge Backtest
    assert "Kuantitatif, Pola & Backtest:" in card
    assert "alpha_gbpusd_4947d0" in card
    assert "Mean-reversion statistik" in card

    # 5. No slash commands
    assert "/approve" not in card
    assert "/reject" not in card


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

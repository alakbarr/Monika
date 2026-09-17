# ==============================================================================
# File: tests/telegram_bot/test_chat_agent_tool_understanding.py
# ==============================================================================

import pytest
import re
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_bot.chat_agent import ChatAgent, PendingAction
from skills.loader import load_skill
from database.models import PaperTradeRecord, TradeTrigger, PriceOHLCV
from analysis.tools.tools_definitions import (
    STAGE1_TOOLS,
    STAGE2_TOOLS,
    TELEGRAM_TOOLS,
    PROPOSE_ACTION,
    GET_FUNDING_RATE,
)

class TestChatAgentToolUnderstanding:

    def test_telegram_persona_skill_loading(self):
        """Memastikan persona skill termuat dengan lengkap dan memiliki Master Playbook."""
        persona = load_skill("telegram_persona")
        assert "Master Intent-to-Tool Matrix" in persona
        assert "get_paper_trading_performance" in persona
        assert "get_active_triggers" in persona
        assert "get_system_health" in persona
        assert "get_edge_tracker_status" in persona
        assert "Multi-Tool Chaining Standard Operating Procedures" in persona
        assert "Standard Telegram Output Templates" in persona

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_system_prompt_enrichment(self, mock_get_client):
        """Memastikan system prompt chat agent menyertakan snapshot portofolio dan persona playbook."""
        settings = {
            "trading": {"caveman_mode": False},
            "paper_trading": {"enabled": True},
            "llm": {"models": {"deep": "claude-3-5-sonnet", "fast": "gemini-flash"}}
        }
        agent = ChatAgent(settings, user_id=123)
        
        mock_session = AsyncMock()
        mock_pos_res = MagicMock()
        mock_pos_res.scalars().all.return_value = []
        
        mock_paper_res = MagicMock()
        mock_paper_res.scalars().all.return_value = []
        
        mock_trig_res = MagicMock()
        mock_trig_res.scalars().all.return_value = []
        
        mock_risk_res = MagicMock()
        mock_risk_res.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[
            mock_pos_res,   # Open positions
            mock_paper_res, # Open paper trades
            mock_trig_res,  # Pending triggers
            mock_risk_res   # Risk state
        ])

        with patch("utils.analytics.paper_tracker.PaperTracker.get_statistics", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {"total_trades": 10, "win_rate_pct": 70.0, "total_pnl_pct": 5.4}
            prompt = await agent._build_system_prompt(mock_session)
            full_prompt = "\n".join(prompt) if isinstance(prompt, tuple) else prompt

            assert "Master Intent-to-Tool Matrix" in full_prompt
            assert "Paper Trading & Portfolio Snapshot" in full_prompt
            assert "Anti-Hallucination Rules (MANDATORY)" in full_prompt
            assert "get_paper_trading_performance" in full_prompt

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_classify_query_complexity_domains(self, mock_get_client):
        """Memastikan router mengenali domain query dengan tingkat kompleksitas yang sesuai."""
        settings = {"llm": {}}
        agent = ChatAgent(settings, user_id=123)

        # Simple queries
        assert await agent._classify_query_complexity("Berapa PnL paper trade kita?") == "simple"
        assert await agent._classify_query_complexity("tampilkan posisi terbuka") == "simple"
        assert await agent._classify_query_complexity("status health sistem") == "simple"
        assert await agent._classify_query_complexity("cek active triggers") == "simple"

        # Action / Complex queries
        assert await agent._classify_query_complexity("tutup paper trade XAUUSD") == "complex"
        assert await agent._classify_query_complexity("ubah SL posisi EURUSD ke 1.0850") == "complex"
        assert await agent._classify_query_complexity("batalkan trigger 10") == "complex"
        assert await agent._classify_query_complexity("analisa mendalam setup XAUUSD malam ini") == "complex"

    def test_unfounded_price_claim_detector(self):
        """Memastikan verifikator mendeteksi angka tanpa tool call dan mengabaikan jika tool dipanggil."""
        # Unfounded claim: ada angka & keyword pnl/harga, tapi tool_calls = 0
        price_pattern = r'\b\d{1,3}(?:,\d{3})*(?:\.\d{1,5})?\b'
        keyword_pattern = (
            r'\b(SL|TP|entry|stop\s*loss|take\s*profit|harga|price|resistance|support|'
            r'pnl|p&l|profit|loss|lot|balance|equity|saldo|untung|rugi|margin)\b'
        )

        def check(reply_text: str, tool_calls_made: int) -> bool:
            if tool_calls_made > 0:
                return False
            matches = re.findall(price_pattern, reply_text)
            has_meaningful_number = any(len(m.replace(',', '').replace('.', '')) >= 3 for m in matches)
            return has_meaningful_number and bool(re.search(keyword_pattern, reply_text, re.IGNORECASE))

        # Halusinasi PnL tanpa tool call
        assert check("PnL kita saat ini profit +12.50% dari 25 trade.", tool_calls_made=0) is True
        # Klaim dengan tool call (valid)
        assert check("PnL kita saat ini profit +12.50% dari 25 trade.", tool_calls_made=1) is False
        # Chat biasa tanpa angka harga
        assert check("Halo, saya siap membantu menganalisis pasar.", tool_calls_made=0) is False

    @patch("telegram_bot.chat_agent.get_client_for_task")
    def test_pending_action_creation(self, mock_get_client):
        """Memastikan factory membuat objek PendingAction untuk semua tipe aksi yang didukung."""
        agent = ChatAgent({}, user_id=123)
        
        # Valid actions
        for act_type in ("close_paper_trade", "modify_paper_sl_tp", "cancel_trigger", "pause_trading", "resume_trading"):
            proposed = {"action_type": act_type, "params": {"id": 1}, "description": "test action"}
            pending = agent._create_pending_action(proposed)
            assert pending is not None
            assert pending.action_type == act_type
            assert pending.params == {"id": 1}

        # Invalid action
        invalid_proposed = {"action_type": "delete_all_database", "params": {}}
        assert agent._create_pending_action(invalid_proposed) is None

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_execute_action_paper_trade_close(self, mock_get_client):
        """Memastikan eksekusi close_paper_trade menutup record dan menghitung realized PnL."""
        agent = ChatAgent({}, user_id=123)
        action = PendingAction(
            action_id="act-123",
            action_type="close_paper_trade",
            params={"trade_id": 5},
            description="Close paper trade 5"
        )

        trade = PaperTradeRecord(
            id=5, symbol="XAUUSD", direction="buy", entry_price=2600.0,
            status="open", opened_at=datetime.now(timezone.utc)
        )
        bar = PriceOHLCV(symbol="XAUUSD", close=2650.0, timestamp=datetime.now(timezone.utc))

        mock_session = AsyncMock()
        m_trade_res = MagicMock()
        m_trade_res.scalars().first.return_value = trade

        m_bar_res = MagicMock()
        m_bar_res.scalar_one_or_none.return_value = bar

        mock_session.execute = AsyncMock(side_effect=[m_trade_res, m_bar_res])
        mock_session.commit = AsyncMock()

        with patch("telegram_bot.chat_agent.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            with patch("utils.analytics.paper_tracker.PaperTracker._close_linked_position", new_callable=AsyncMock):
                result = await agent._execute_action(action)
                assert "[OK] Paper trade #5 (XAUUSD) closed manually @ 2650.00000" in result
                assert "Realized PnL: +1.92%" in result
                assert trade.status == "closed"
                assert trade.exit_price == 2650.0

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_execute_action_cancel_trigger(self, mock_get_client):
        """Memastikan eksekusi cancel_trigger mengubah status trigger menjadi cancelled."""
        agent = ChatAgent({}, user_id=123)
        action = PendingAction(
            action_id="act-456",
            action_type="cancel_trigger",
            params={"trigger_id": 12},
            description="Cancel trigger 12"
        )

        trigger = TradeTrigger(id=12, status="pending")

        mock_session = AsyncMock()
        m_trig_res = MagicMock()
        m_trig_res.scalar_one_or_none.return_value = trigger
        mock_session.execute = AsyncMock(return_value=m_trig_res)
        mock_session.commit = AsyncMock()

        with patch("telegram_bot.chat_agent.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            result = await agent._execute_action(action)
            assert "[OK] Trigger #12 cancelled." in result
            assert trigger.status == "cancelled"

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_pending_action_expiry_rejection(self, mock_get_client):
        """Memastikan confirm_action menolak aksi yang telah melewati batas 5 menit."""
        agent = ChatAgent({}, user_id=123)
        action = PendingAction(
            action_id="act-exp-1",
            action_type="cancel_trigger",
            params={"trigger_id": 99},
            description="Cancel trigger 99"
        )
        action.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        agent._pending_actions["act-exp-1"] = action

        ok, msg = await agent.confirm_action("act-exp-1")
        assert ok is False
        assert "expired" in msg.lower()
        assert "act-exp-1" not in agent._pending_actions

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_pending_action_unknown_rejection(self, mock_get_client):
        """Memastikan confirm_action menolak action_id yang tidak ditemukan."""
        agent = ChatAgent({}, user_id=123)
        ok, msg = await agent.confirm_action("nonexistent_id")
        assert ok is False
        assert "not found" in msg.lower()

    def test_propose_action_scoping_isolation(self):
        """Memastikan PROPOSE_ACTION hanya ada di TELEGRAM_TOOLS dan tidak bocor ke STAGE1/STAGE2."""
        assert PROPOSE_ACTION in TELEGRAM_TOOLS
        assert PROPOSE_ACTION not in STAGE1_TOOLS
        assert PROPOSE_ACTION not in STAGE2_TOOLS

    def test_stage1_tools_includes_funding_rate(self):
        """Memastikan GET_FUNDING_RATE tersedia di STAGE1_TOOLS untuk analisis makro komprehensif."""
        assert GET_FUNDING_RATE in STAGE1_TOOLS

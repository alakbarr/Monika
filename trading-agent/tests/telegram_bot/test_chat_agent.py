import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram_bot.chat_agent import ChatAgent, PendingAction, _sanitize_telegram_format, SESSION_TIMEOUT_HOURS
from datetime import datetime, timezone, timedelta

class TestChatAgent:
    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_init(self, mock_get_client):
        settings = {}
        agent = ChatAgent(settings, 123)
        assert agent.user_id == 123
        assert agent.settings == settings
        assert mock_get_client.call_count == 4
        mock_get_client.assert_any_call("chat_telegram", settings)
        mock_get_client.assert_any_call("chat_telegram_medium", settings)
        mock_get_client.assert_any_call("chat_telegram_complex", settings)
        mock_get_client.assert_any_call("deep_research", settings)

    def test_pending_action_expiry(self):
        action = PendingAction("123", "test", {}, "desc")
        assert not action.is_expired()
        
        # Manually expire
        action.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert action.is_expired()

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_session")
    @patch("telegram_bot.chat_agent.get_client_for_task")
    async def test_handle_success(self, mock_get_client, mock_get_session):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        mock_client = mock_get_client.return_value
        mock_client.model = "gemini-3.1-flash-lite"
        mock_client.model_name = "gemini-3.1-flash-lite"
        mock_client.run_chat_loop = AsyncMock(return_value={
            "reply": "Test reply",
            "proposed_action": {
                "action_type": "place_order",
                "params": {"symbol": "XAUUSD"},
                "description": "Buy gold"
            },
            "input_tokens": 100,
            "output_tokens": 50,
        })
        
        agent = ChatAgent({}, 123)
        agent._save_message = AsyncMock()
        agent._load_history = AsyncMock(return_value=[])
        agent._build_system_prompt = AsyncMock(return_value="Prompt")
        
        reply, pending = await agent.handle("Hello")
        
        assert "Test reply" in reply
        assert "_[gemini-3.1-flash-lite | 100 in, 50 out]_" in reply
        assert "⚡" not in reply
        assert "🚀" not in reply
        assert pending is not None
        assert pending.action_type == "place_order"
        assert pending.params == {"symbol": "XAUUSD"}
        assert agent._save_message.call_count == 2 # user and assistant

    @pytest.mark.asyncio
    @patch("execution.execution_service.ExecutionService")
    @patch("telegram_bot.chat_agent.get_session")
    async def test_confirm_action_success(self, mock_get_session, mock_exec_cls):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        mock_exec = mock_exec_cls.return_value
        mock_exec.close_position_by_ticket = AsyncMock(return_value={"success": True, "profit": 100})
        
        agent = ChatAgent({}, 123)
        action = PendingAction("act1", "close_position", {"ticket": 456}, "Close pos")
        agent._pending_actions["act1"] = action
        
        success, msg = await agent.confirm_action("act1")
        assert success
        assert "[OK] Position #456 closed" in msg
        assert "act1" not in agent._pending_actions

    @pytest.mark.asyncio
    async def test_confirm_action_expired(self):
        agent = ChatAgent({}, 123)
        action = PendingAction("act1", "close_position", {}, "desc")
        action.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        agent._pending_actions["act1"] = action
        
        success, msg = await agent.confirm_action("act1")
        assert not success
        assert "expired" in msg

    @pytest.mark.asyncio
    @patch("telegram_bot.chat_agent.get_session")
    async def test_reject_action(self, mock_get_session):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        agent = ChatAgent({}, 123)
        action = PendingAction("act1", "close_position", {}, "desc")
        agent._pending_actions["act1"] = action
        
        msg = await agent.reject_action("act1")
        assert "Action rejected" in msg
        assert "act1" not in agent._pending_actions

    @pytest.mark.asyncio
    @patch("database.models.SystemConfig.upsert", new_callable=AsyncMock)
    @patch("telegram_bot.chat_agent.get_session")
    async def test_pending_action_persistence_and_restore(self, mock_get_session, mock_upsert):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        agent = ChatAgent({}, 123)
        action = PendingAction("act_persist", "place_order", {"symbol": "EURUSD"}, "Buy 0.1 EURUSD")

        # Test persist
        await agent._persist_pending_action(action)
        mock_upsert.assert_awaited_once()

        # Test restore when in-memory cache is empty
        assert "act_persist" not in agent._pending_actions
        mock_cfg = MagicMock()
        import json
        mock_cfg.value = json.dumps(action.to_dict())
        res = MagicMock()
        res.scalar_one_or_none.return_value = mock_cfg
        mock_session.execute = AsyncMock(return_value=res)

        restored = await agent.get_pending_action("act_persist")
        assert restored is not None
        assert restored.action_id == "act_persist"
        assert restored.action_type == "place_order"
        assert restored.params == {"symbol": "EURUSD"}
        assert "act_persist" in agent._pending_actions


class TestTelegramFormatSanitizer:
    def test_heading_conversion(self):
        text = "### 1. Rincian Posisi\nBerikut datanya:\n## 2. Kesimpulan"
        sanitized = _sanitize_telegram_format(text)
        assert "###" not in sanitized
        assert "##" not in sanitized
        assert "*1. Rincian Posisi*" in sanitized
        assert "*2. Kesimpulan*" in sanitized

    def test_emoji_removal(self):
        text = "🚀 gemini-3.7-flash ⚡ gemini-3.1-flash-lite | 22189 in, 412 out\n📊 Status: 🟢 OK ⏸️ PAUSED"
        sanitized = _sanitize_telegram_format(text)
        for emoji in ["🚀", "⚡", "📊", "🟢", "⏸️"]:
            assert emoji not in sanitized

    def test_hallucinated_footer_stripped(self):
        text = "Laporan selesai.\n\n_gemini-3.7-flash | 123 in, 45 out_\ngemini-3.5-flash"
        sanitized = _sanitize_telegram_format(text)
        assert sanitized == "Laporan selesai."


class TestChatAgentHistoryMemory:
    @pytest.mark.asyncio
    async def test_load_history_session_timeout(self):
        agent = ChatAgent({}, 123)
        now = datetime.now(timezone.utc)
        
        row_recent = MagicMock()
        row_recent.role = "user"
        row_recent.message = "Pesan baru"
        row_recent.timestamp = now - timedelta(minutes=5)

        row_old = MagicMock()
        row_old.role = "user"
        row_old.message = "Pesan 13 jam lalu"
        row_old.timestamp = now - timedelta(hours=13)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row_recent, row_old]
        mock_session.execute = AsyncMock(return_value=mock_result)

        history = await agent._load_history(mock_session)
        assert len(history) == 1
        assert history[0]["content"] == "Pesan baru"

    @pytest.mark.asyncio
    async def test_load_history_truncation_preserves_newest(self):
        agent = ChatAgent({}, 123)
        now = datetime.now(timezone.utc)
        
        rows = []
        for i in range(10):
            r = MagicMock()
            r.role = "user"
            r.message = f"Message {i} " + "X" * 1000
            r.timestamp = now - timedelta(minutes=10 - i)
            rows.append(r)
        
        # rows ordered desc (newest first: Message 9 down to Message 0)
        rows_desc = list(reversed(rows))

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows_desc
        mock_session.execute = AsyncMock(return_value=mock_result)

        history = await agent._load_history(mock_session)
        # Verify newest messages (Message 9, 8, etc.) are in history, oldest dropped
        contents = [m["content"] for m in history]
        assert any("Message 9" in c for c in contents)
        assert any("Message 8" in c for c in contents)
        assert not any("Message 0" in c for c in contents)


@pytest.mark.asyncio
@patch("telegram_bot.chat_agent.get_session")
async def test_chat_agent_adhoc_pipeline_routing(mock_get_session):
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_get_session.return_value = mock_ctx

    agent = ChatAgent(settings={}, user_id=123)
    agent._save_message = AsyncMock()

    mock_adhoc_result = {
        "success": True,
        "symbol": "XAUUSD",
        "decision": "BUY",
        "formatted_summary": "🎯 *HASIL ANALISIS AD-HOC: XAUUSD*\n• *Keputusan*: `BUY`",
    }

    with patch("agent.agent_loop.SystemAgentLoop.execute_ad_hoc_analysis", new_callable=AsyncMock) as mock_adhoc:
        mock_adhoc.return_value = mock_adhoc_result

        reply, pending = await agent.handle("Tolong analisa XAUUSD sekarang")

        mock_adhoc.assert_called_once()
        args, kwargs = mock_adhoc.call_args
        assert args[0] == "XAUUSD"
        assert pending is None
        assert "HASIL ANALISIS AD-HOC: XAUUSD" in reply
        assert "SystemAgentLoop" in reply

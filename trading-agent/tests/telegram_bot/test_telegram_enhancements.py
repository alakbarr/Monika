# ==============================================================================
# File: tests/telegram_bot/test_telegram_enhancements.py
# ==============================================================================

"""
Unit tests for Phase 4 Telegram Enhancements:
1. Token Streaming via Edit-Message (throttling, cursor rendering, HTML sanitization).
2. Telegram Forum Topic Mode (TopicManager CRUD, session isolation, routing with message_thread_id).
3. Voice Memo Transcription (VoiceHandler audio download, Gemini transcription, ChatAgent routing).
"""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.models import Base, TelegramConversation, TelegramTopicBinding
from telegram_bot.chat_agent import ChatAgent
from telegram_bot.topic_manager import TopicManager
from telegram_bot.voice_handler import VoiceHandler
from telegram_bot.bot import TelegramBot


# ---------------------------------------------------------------------------
# In-memory async database fixture for testing
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_db_session_factory():
    """Create in-memory SQLite database for testing models and TopicManager."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Token Streaming via Edit-Message Tests
# ---------------------------------------------------------------------------

class TestStreamingMessageEdit:
    """Tests for token streaming, throttling, cursor display, and sanitization."""

    @pytest.mark.asyncio
    async def test_stream_response_throttling_and_cursor(self):
        """Verify stream edits are throttled to >= 500ms and cursor is stripped on completion."""
        agent = ChatAgent(settings={}, user_id=123)

        mock_sent_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_sent_msg)

        # Generator that yields chunks with small delays
        async def mock_generator():
            yield "Halo! "
            await asyncio.sleep(0.05)
            yield "Ini adalah "
            await asyncio.sleep(0.05)
            yield "hasil analisis "
            await asyncio.sleep(0.55)  # Triggers throttle interval
            yield "pasar terkini."

        result = await agent._stream_response(mock_update, None, mock_generator())

        assert "Halo! Ini adalah hasil analisis pasar terkini." in result
        mock_update.message.reply_text.assert_called_once_with("⏳ Thinking...")

        # Intermediate edits should display cursor ▌
        calls = mock_sent_msg.edit_text.call_args_list
        assert len(calls) >= 2  # At least 1 throttled intermediate + 1 final
        intermediate_text = calls[0][0][0]
        assert "▌" in intermediate_text

        # Final edit must NOT contain cursor ▌
        final_call_text = calls[-1][0][0]
        assert "▌" not in final_call_text
        assert calls[-1][1].get("parse_mode") == "HTML"

    @pytest.mark.asyncio
    async def test_stream_response_handles_retry_after(self):
        """Verify RetryAfter exception pauses and retries editing without crashing."""
        from telegram.error import RetryAfter

        agent = ChatAgent(settings={}, user_id=123)
        mock_sent_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_sent_msg)

        # First edit raises RetryAfter, final edit succeeds
        mock_sent_msg.edit_text.side_effect = [
            RetryAfter(0.01),
            AsyncMock(),
            AsyncMock(),
        ]

        async def mock_generator():
            yield "Kalimat pertama panjang yang memenuhi syarat buffer lebih dari 20 karakter."
            await asyncio.sleep(0.55)
            yield " Kalimat kedua."

        result = await agent._stream_response(mock_update, None, mock_generator())
        assert "Kalimat pertama" in result
        assert "Kalimat kedua" in result

    @pytest.mark.asyncio
    async def test_stream_response_handles_bad_request(self):
        """Verify BadRequest (e.g. message unchanged) is safely ignored."""
        from telegram.error import BadRequest

        agent = ChatAgent(settings={}, user_id=123)
        mock_sent_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_sent_msg)

        mock_sent_msg.edit_text.side_effect = [
            BadRequest("Message is not modified"),
            AsyncMock(),
        ]

        async def mock_generator():
            yield "Kalimat dengan panjang lebih dari dua puluh karakter."
            await asyncio.sleep(0.55)
            yield " Lanjutan teks."

        result = await agent._stream_response(mock_update, None, mock_generator())
        assert "Lanjutan teks" in result

    @pytest.mark.asyncio
    async def test_provider_streaming_generators(self):
        """Verify _run_with_gemini and _run_with_claude yield streaming chunks when stream=True."""
        agent = ChatAgent(settings={}, user_id=123)

        # 1. Native generate_content_stream
        async def mock_gemini_stream(*args, **kwargs):
            yield "Respon Gemini "
            yield "berhasil."

        agent._client_lite.generate_content_stream = mock_gemini_stream

        gemini_gen = await agent._run_with_gemini("sys", [], "user msg", stream=True)
        gemini_chunks = []
        async for chunk in gemini_gen:
            gemini_chunks.append(chunk)
        assert "".join(gemini_chunks) == "Respon Gemini berhasil."

        # 2. Native Claude generate_content_stream
        async def mock_claude_stream(*args, **kwargs):
            yield "Respon Claude "
            yield "berhasil."

        agent._client_deep.generate_content_stream = mock_claude_stream

        claude_gen = await agent._run_with_claude("sys", [], "user msg", stream=True)
        claude_chunks = []
        async for chunk in claude_gen:
            claude_chunks.append(chunk)
        assert "".join(claude_chunks) == "Respon Claude berhasil."

        # 3. Fallback when client has no stream methods
        agent._client_lite.generate_content_stream = None
        agent._run_tier_lite = AsyncMock(return_value={"reply": "Fallback Gemini"})
        fallback_gen = await agent._run_with_gemini("sys", [], "user msg", stream=True)
        fb_chunks = []
        async for chunk in fallback_gen:
            fb_chunks.append(chunk)
        assert "".join(fb_chunks) == "Fallback Gemini"

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_handle_with_stream_flag(self, mock_get_session):
        """Verify calling handle(..., stream=True, update=...) delegates to _stream_response."""
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        agent = ChatAgent(settings={}, user_id=123)
        agent._load_history = AsyncMock(return_value=[])
        agent._save_message = AsyncMock()
        agent._build_system_prompt = AsyncMock(return_value="sys prompt")
        agent._stream_response = AsyncMock(return_value="Streamed output selesai.")

        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock()

        reply, pending = await agent.handle(
            "Analisa EURUSD",
            stream=True,
            update=mock_update,
        )

        assert reply == "Streamed output selesai."
        assert pending is None
        agent._stream_response.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Telegram Forum Topic Mode Tests
# ---------------------------------------------------------------------------

class TestTopicManager:
    """Tests for TopicManager CRUD, persistence, and session isolation."""

    @pytest.mark.asyncio
    async def test_topic_manager_crud(self, test_db_session_factory):
        """Verify creating, looking up, listing, and cleaning up topic sessions."""
        tm = TopicManager(session_factory=test_db_session_factory)

        # 1. Non-existent topic returns None
        s0 = await tm.get_session_for_topic(chat_id=1001, topic_id=42)
        assert s0 is None

        # 2. Create topic session
        s1 = await tm.create_topic_session(chat_id=1001, topic_id=42, topic_name="Gold Discussion")
        assert s1 == "tg_topic_1001_42"

        # 3. Lookup returns created session ID
        s2 = await tm.get_session_for_topic(chat_id=1001, topic_id=42)
        assert s2 == "tg_topic_1001_42"

        # 4. Repeated create returns same session ID
        s3 = await tm.create_topic_session(chat_id=1001, topic_id=42, topic_name="Gold Updated")
        assert s3 == "tg_topic_1001_42"

        # 5. List topics for chat
        await tm.create_topic_session(chat_id=1001, topic_id=43, topic_name="Forex")
        await tm.create_topic_session(chat_id=2002, topic_id=99, topic_name="Other Group")

        topics_1001 = await tm.list_topics_for_chat(1001)
        assert len(topics_1001) == 2
        assert {t.topic_id for t in topics_1001} == {42, 43}

        # 6. Cleanup deleted topic
        await tm.cleanup_deleted_topic(chat_id=1001, topic_id=42)
        assert await tm.get_session_for_topic(1001, 42) is None
        assert len(await tm.list_topics_for_chat(1001)) == 1

    @pytest.mark.asyncio
    async def test_chat_agent_session_isolation(self, test_db_session_factory):
        """Verify ChatAgent history is strictly isolated across different topic sessions."""
        agent = ChatAgent(settings={}, user_id=999)

        async with test_db_session_factory() as session:
            # Save messages in Topic A
            await agent._save_message(session, "user", "Pesan di Topik A", session_id="tg_topic_100_1")
            await agent._save_message(session, "assistant", "Jawaban Topik A", session_id="tg_topic_100_1")

            # Save messages in Topic B
            await agent._save_message(session, "user", "Pesan di Topik B", session_id="tg_topic_100_2")

            # Load history for Topic A
            hist_a = await agent._load_history(session, session_id="tg_topic_100_1")
            # Load history for Topic B
            hist_b = await agent._load_history(session, session_id="tg_topic_100_2")
            # Load history for Default User session (no session_id)
            hist_user = await agent._load_history(session, session_id=None)

            assert len(hist_a) == 2
            assert hist_a[0]["content"] == "Pesan di Topik A"
            assert hist_a[1]["content"] == "Jawaban Topik A"

            assert len(hist_b) == 1
            assert hist_b[0]["content"] == "Pesan di Topik B"

            assert len(hist_user) == 0


# ---------------------------------------------------------------------------
# 3. Message Thread ID Routing in Bot Tests
# ---------------------------------------------------------------------------

class TestBotTopicRouting:
    """Tests for routing updates with message_thread_id to topic-specific sessions."""

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_handle_chat_routes_topic_thread_id(self, mock_get_session):
        """Verify updates with message_thread_id create topic session and route to isolated agent."""
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)

        mock_tm = AsyncMock()
        mock_tm.get_session_for_topic = AsyncMock(return_value=None)
        mock_tm.create_topic_session = AsyncMock(return_value="tg_topic_777_88")
        bot.topic_manager = mock_tm

        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_chat.id = 777
        update.message.text = "Analisis di topic 88"
        update.message.message_thread_id = 88
        update.message.reply_text = AsyncMock()
        update.message.chat.send_action = AsyncMock()

        ctx = MagicMock()

        with patch("telegram_bot.chat_agent.ChatAgent.handle", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = ("Jawaban topic", None)
            await bot._handle_chat(update, ctx)

            mock_tm.get_session_for_topic.assert_called_once_with(777, 88)
            mock_tm.create_topic_session.assert_called_once_with(777, 88, topic_name="Topic-88")
            assert "tg_topic_777_88" in bot._chat_agents

            # Handle called with session_id="tg_topic_777_88"
            assert mock_handle.call_args[1].get("session_id") == "tg_topic_777_88"

    @pytest.mark.asyncio
    async def test_send_notification_passes_message_thread_id(self):
        """Verify send_notification forwards message_thread_id when provided."""
        bot = TelegramBot({})
        bot._app = MagicMock()
        bot.admin_chat_id = 123
        bot._is_running = True
        bot._app.bot.send_message = AsyncMock()

        await bot.send_notification("Alert in topic", message_thread_id=999)
        bot._app.bot.send_message.assert_called_once()
        assert bot._app.bot.send_message.call_args[1].get("message_thread_id") == 999


# ---------------------------------------------------------------------------
# 4. Voice Memo Transcription Tests
# ---------------------------------------------------------------------------

class TestVoiceMemoTranscription:
    """Tests for VoiceHandler audio download, Gemini transcription, and ChatAgent forwarding."""

    @pytest.mark.asyncio
    async def test_voice_handler_ignores_messages_without_audio(self):
        """Verify non-audio messages are ignored by VoiceHandler."""
        vh = VoiceHandler()
        update = MagicMock()
        update.message.voice = None
        update.message.audio = None

        await vh.handle_voice(update, MagicMock())
        assert update.message.reply_text.call_count == 0

    @pytest.mark.asyncio
    async def test_voice_handler_rejects_unauthorized(self):
        """Verify unauthorized users are rejected before transcription."""
        mock_bot = MagicMock()
        mock_bot._is_authorized.return_value = False
        mock_bot._reject_unauthorized = AsyncMock()

        vh = VoiceHandler(bot=mock_bot)
        update = MagicMock()
        update.message.voice = MagicMock()

        await vh.handle_voice(update, MagicMock())
        mock_bot._reject_unauthorized.assert_called_once_with(update)

    @pytest.mark.asyncio
    async def test_voice_handler_download_transcribe_and_dispatch(self):
        """Verify VoiceHandler downloads audio, transcribes it, and routes to ChatAgent."""
        mock_agent = MagicMock()
        mock_agent.handle = AsyncMock(return_value=("Order selesai", None))

        vh = VoiceHandler(chat_agent=mock_agent)

        mock_status_msg = AsyncMock()
        update = MagicMock()
        update.message.reply_text = AsyncMock(return_value=mock_status_msg)

        mock_voice = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_audio_bytes"))
        mock_voice.get_file = AsyncMock(return_value=mock_file)
        mock_voice.mime_type = "audio/ogg"

        update.message.voice = mock_voice
        update.message.audio = None
        update.message.message_thread_id = None

        # Mock transcription function
        vh._transcribe = AsyncMock(return_value="tutup semua posisi trading sekarang")

        ctx = MagicMock()
        await vh.handle_voice(update, ctx)

        # 1. Downloaded audio
        mock_voice.get_file.assert_called_once()
        mock_file.download_as_bytearray.assert_called_once()

        # 2. Transcribed
        vh._transcribe.assert_called_once_with(b"fake_audio_bytes", mime_type="audio/ogg")

        # 3. Displayed acknowledgment
        mock_status_msg.edit_text.assert_called_with('🎤 Heard: "tutup semua posisi trading sekarang"')

        # 4. Routed to ChatAgent with override_text
        mock_agent.handle.assert_called_once()
        assert mock_agent.handle.call_args[1].get("override_text") == "tutup semua posisi trading sekarang"

    @pytest.mark.asyncio
    async def test_voice_handler_in_topic_thread(self):
        """Verify VoiceHandler resolves topic session when audio is received inside a topic."""
        mock_bot = MagicMock()
        mock_bot._is_authorized.return_value = True
        mock_bot.settings = {}
        mock_bot._chat_agents = {}

        mock_tm = AsyncMock()
        mock_tm.get_session_for_topic = AsyncMock(return_value="tg_topic_555_12")
        mock_bot.topic_manager = mock_tm

        vh = VoiceHandler(bot=mock_bot)

        mock_status_msg = AsyncMock()
        update = MagicMock()
        update.effective_chat.id = 555
        update.effective_user.id = 111
        update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        update.message.message_thread_id = 12

        mock_voice = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"audio"))
        mock_voice.get_file = AsyncMock(return_value=mock_file)
        update.message.voice = mock_voice
        update.message.audio = None

        vh._transcribe = AsyncMock(return_value="cek balance")

        with patch("telegram_bot.chat_agent.ChatAgent.handle", new_callable=AsyncMock) as mock_handle:
            await vh.handle_voice(update, MagicMock())
            mock_tm.get_session_for_topic.assert_called_once_with(555, 12)
            assert mock_handle.call_args[1].get("session_id") == "tg_topic_555_12"
            assert mock_handle.call_args[1].get("override_text") == "cek balance"

    @pytest.mark.asyncio
    async def test_stream_response_empty_buffer_fallback(self):
        """Verify stream with empty generator does not crash and renders graceful notification."""
        agent = ChatAgent(settings={}, user_id=123)
        mock_sent_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_sent_msg)

        async def empty_gen():
            if False:
                yield ""

        result = await agent._stream_response(mock_update, None, empty_gen())
        assert result == ""
        # Final edit should be fallback text, not empty string
        final_text = mock_sent_msg.edit_text.call_args[0][0]
        assert "Tidak ada respons" in final_text

    @pytest.mark.asyncio
    async def test_stream_response_long_message_chunking(self):
        """Verify streaming responses exceeding 4096 characters are chunked safely."""
        agent = ChatAgent(settings={}, user_id=123)
        mock_sent_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_sent_msg)

        async def long_gen():
            yield "A" * 5000

        result = await agent._stream_response(mock_update, None, long_gen())
        assert len(result) == 5000
        # First chunk edited into existing message
        assert mock_sent_msg.edit_text.called
        # Remaining chunk sent via reply_text
        assert mock_update.message.reply_text.call_count >= 2

    @pytest.mark.asyncio
    async def test_provider_streaming_passes_conversation_history(self):
        """Verify conversation_history is forwarded to generate_content_stream."""
        agent = ChatAgent(settings={}, user_id=123)
        history = [{"role": "user", "content": "Analisa Gold"}]

        captured_kwargs = {}
        async def mock_stream(*args, **kwargs):
            captured_kwargs.update(kwargs)
            yield "Token"

        agent._client_lite.generate_content_stream = mock_stream
        gen = await agent._run_with_gemini("sys", history, "Berapa targetnya?", stream=True)
        async for _ in gen:
            pass

        assert captured_kwargs.get("conversation_history") == history

    @pytest.mark.asyncio
    async def test_cmd_interrupt_and_resume_in_topic(self):
        """Verify /interrupt and /resume_proposals resolve topic session agent."""
        bot = TelegramBot({})
        bot._is_authorized = MagicMock(return_value=True)

        mock_tm = AsyncMock()
        mock_tm.get_session_for_topic = AsyncMock(return_value="tg_topic_100_50")
        bot.topic_manager = mock_tm

        mock_agent = MagicMock()
        mock_agent.interrupt = MagicMock(return_value=True)
        mock_agent.resume_proposals = MagicMock(return_value="Resumed")
        bot._chat_agents["tg_topic_100_50"] = mock_agent

        update = MagicMock()
        update.effective_chat.id = 100
        update.effective_user.id = 999
        update.message.message_thread_id = 50
        update.message.reply_text = AsyncMock()

        ctx = MagicMock()
        ctx.args = []

        await bot._cmd_interrupt(update, ctx)
        mock_agent.interrupt.assert_called_once()
        assert "interrupted" in update.message.reply_text.call_args[0][0]

        await bot._cmd_resume_proposals(update, ctx)
        mock_agent.resume_proposals.assert_called_once()
        assert "Resumed" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_voice_handler_forwards_agent_reply_and_action_keyboard(self):
        """Verify VoiceHandler sends the AI reply and proposal keyboard back to the user."""
        from telegram_bot.chat_agent import PendingAction
        mock_pending = PendingAction("act_123", "place_order", {"symbol": "EURUSD"}, "Buy 0.1 EURUSD")

        mock_agent = MagicMock()
        mock_agent.handle = AsyncMock(return_value=("Analisis selesai. Mengusulkan order.", mock_pending))
        mock_agent.pop_pending_charts = MagicMock(return_value=[])

        vh = VoiceHandler(chat_agent=mock_agent)
        vh._transcribe = AsyncMock(return_value="analisis dan usulkan order eurusd")

        mock_status_msg = AsyncMock()
        update = MagicMock()
        update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        mock_voice = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"audio"))
        mock_voice.get_file = AsyncMock(return_value=mock_file)
        update.message.voice = mock_voice
        update.message.audio = None

        await vh.handle_voice(update, MagicMock())

        # Reply text and pending keyboard must be delivered!
        reply_calls = [c[0][0] for c in update.message.reply_text.call_args_list]
        assert any("Analisis selesai" in c for c in reply_calls)
        assert any("AI Mengusulkan Tindakan" in c for c in reply_calls)


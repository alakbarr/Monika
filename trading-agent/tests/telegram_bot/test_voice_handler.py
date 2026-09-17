"""
Unit test for VoiceHandler header authentication (H-18).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_bot.voice_handler import VoiceHandler


@pytest.mark.asyncio
async def test_voice_handler_passes_x_goog_api_key_header():
    handler = VoiceHandler(settings={
        "api_keys": {"gemini": "test_gemini_key_123"},
        "llm": {"task_roles": {"chat_telegram": {"model": "gemini-2.5-flash"}}}
    })

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "candidates": [{
            "content": {"parts": [{"text": "Hello world from voice"}]}
        }]
    })

    with patch("aiohttp.ClientSession.post") as mock_post, \
         patch("analysis.providers.llm_factory.get_client_for_task", side_effect=Exception("No LLM client")):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_ctx

        result = await handler._transcribe(b"fake_audio_bytes", "audio/ogg")

        assert result == "Hello world from voice"
        assert mock_post.called
        call_args, call_kwargs = mock_post.call_args

        # Verify key is NOT in the URL
        url = call_args[0]
        assert "key=" not in url
        assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

        # Verify key is passed in headers
        headers = call_kwargs.get("headers", {})
        assert headers.get("x-goog-api-key") == "test_gemini_key_123"

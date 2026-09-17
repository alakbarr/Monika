import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import aiohttp
import asyncio
from utils.api.http_retry import fetch_with_retry

class TestHTTPRetry:
    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    @patch("utils.api.http_retry.asyncio.sleep")
    async def test_fetch_success(self, mock_sleep, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"data": "test"})
        
        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp
        
        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        res = await fetch_with_retry("http://test.com")
        assert res == {"data": "test"}
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    @patch("utils.api.http_retry.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_retry_429(self, mock_sleep, mock_session_cls):
        # First call 429, second call 200
        mock_resp_429 = MagicMock()
        mock_resp_429.status = 429
        mock_resp_429.text = AsyncMock(return_value="rate limit")
        
        mock_resp_200 = MagicMock()
        mock_resp_200.status = 200
        mock_resp_200.json = AsyncMock(return_value={"data": "test"})
        mock_resp_200.text = AsyncMock(return_value="ok")
        
        mock_req_ctx_1 = AsyncMock()
        mock_req_ctx_1.__aenter__.return_value = mock_resp_429
        
        mock_req_ctx_2 = AsyncMock()
        mock_req_ctx_2.__aenter__.return_value = mock_resp_200
        
        mock_session = MagicMock()
        mock_session.request.side_effect = [mock_req_ctx_1, mock_req_ctx_2]
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        res = await fetch_with_retry("http://test.com", max_retries=2, base_delay=0)
        assert res == {"data": "test"}
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    @patch("utils.api.http_retry.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_fail_after_retries(self, mock_sleep, mock_session_cls):
        # Always 500
        mock_resp = MagicMock()
        mock_resp.status = 500
        
        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp
        
        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        
        res = await fetch_with_retry("http://test.com", max_retries=2, base_delay=0)
        assert res is None
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    async def test_fetch_raise_429_with_retry_after(self, mock_session_cls):
        from utils.api.http_retry import RateLimitError, _CIRCUIT_BREAKER
        _CIRCUIT_BREAKER.clear()
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.headers = {"Retry-After": "12.5"}
        mock_resp.text = AsyncMock(return_value="Rate limit exceeded")

        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        with pytest.raises(RateLimitError) as exc_info:
            await fetch_with_retry("http://test-429.com", raise_on_429=True, use_circuit_breaker=False)

        assert exc_info.value.retry_after == 12.5
        assert exc_info.value.status == 429
        assert "Rate limit exceeded" in exc_info.value.body

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    async def test_fetch_return_error_info(self, mock_session_cls):
        from utils.api.http_retry import _CIRCUIT_BREAKER
        _CIRCUIT_BREAKER.clear()
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_resp.text = AsyncMock(return_value="Forbidden access")

        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        res = await fetch_with_retry("http://test-403.com", return_error_info=True, use_circuit_breaker=False)
        assert res is not None
        assert res.get("_error") is True
        assert res.get("_status") == 403
        assert res.get("_body") == "Forbidden access"

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    async def test_fetch_with_timeout_seconds_and_kwargs(self, mock_session_cls):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True})
        mock_resp.headers = {}

        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        res = await fetch_with_retry(
            "http://test-kwargs.com",
            timeout_seconds=15,
            extra_custom_kwarg="ignored_safely",
            use_circuit_breaker=False,
        )
        assert res == {"ok": True}

    @pytest.mark.asyncio
    @patch("utils.api.http_retry.aiohttp.ClientSession")
    async def test_fetch_with_default_and_custom_ssl(self, mock_session_cls):
        from utils.api.http_retry import _DEFAULT_SSL_CONTEXT

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ssl": "ok"})
        mock_resp.headers = {}

        mock_req_ctx = AsyncMock()
        mock_req_ctx.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.request.return_value = mock_req_ctx
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        # 1. Default SSL context (certifi)
        res = await fetch_with_retry("https://test-ssl.com", use_circuit_breaker=False)
        assert res == {"ssl": "ok"}
        _, kwargs = mock_session.request.call_args
        assert kwargs.get("ssl") == _DEFAULT_SSL_CONTEXT

        # 2. Custom explicit ssl=False override
        res_custom = await fetch_with_retry("https://test-ssl.com", ssl=False, use_circuit_breaker=False)
        assert res_custom == {"ssl": "ok"}
        _, kwargs_custom = mock_session.request.call_args
        assert kwargs_custom.get("ssl") is False

    def test_jittered_delay_bounds(self):
        from utils.api.http_retry import _jittered_delay, _jitter_retry_after
        # Base delay 2.0, attempt 1 -> nominal delay = 4.0. With jitter [0.75 * 4.0, 4.0] -> [3.0, 4.0]
        for _ in range(50):
            d = _jittered_delay(2.0, 1)
            assert 3.0 <= d <= 4.0

        # Base delay 0 -> delay 0
        assert _jittered_delay(0.0, 1) == 0.0

        # Retry-After 10.0 -> [9.0, 10.0]
        for _ in range(50):
            ra = _jitter_retry_after(10.0)
            assert 9.0 <= ra <= 10.0



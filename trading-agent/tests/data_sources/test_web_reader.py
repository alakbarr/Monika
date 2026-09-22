"""
Unit tests for WebReader SSRF protection and body stream limit (H-16, H-17).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from data_sources.web_reader import WebReader, is_prohibited_ip, validate_url_ip


def test_is_prohibited_ip():
    # Loopback
    assert is_prohibited_ip("127.0.0.1") is True
    assert is_prohibited_ip("127.0.0.254") is True
    assert is_prohibited_ip("::1") is True

    # RFC 1918 Private
    assert is_prohibited_ip("10.0.0.1") is True
    assert is_prohibited_ip("172.16.0.1") is True
    assert is_prohibited_ip("172.31.255.255") is True
    assert is_prohibited_ip("192.168.1.1") is True

    # Cloud metadata / Link-local
    assert is_prohibited_ip("169.254.169.254") is True
    assert is_prohibited_ip("169.254.1.1") is True

    # Public valid IP
    assert is_prohibited_ip("8.8.8.8") is False
    assert is_prohibited_ip("104.26.12.31") is False


@pytest.mark.asyncio
async def test_ssrf_blocked_for_private_hosts():
    reader = WebReader()

    # 1. Loopback URL
    res = await reader.read_url("http://127.0.0.1:8080/secret")
    assert res["success"] is False
    assert "SSRF blocked" in res["error"]

    # 2. Cloud metadata URL
    res = await reader.read_url("http://169.254.169.254/latest/meta-data")
    assert res["success"] is False
    assert "SSRF blocked" in res["error"]

    # 3. Private network
    res = await reader.read_url("http://192.168.1.50/admin")
    assert res["success"] is False
    assert "SSRF blocked" in res["error"]


@pytest.mark.asyncio
async def test_web_reader_body_stream_limit():
    """Verify that responses exceeding max_body_bytes are aborted (H-17)."""
    reader = WebReader(max_body_bytes=1024)  # 1KB limit for testing

    async def mock_chunk_iter(*args, **kwargs):
        # Yield two 800-byte chunks -> 1600 bytes total, exceeds 1024
        yield b"A" * 800
        yield b"B" * 800

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.content.iter_chunked = mock_chunk_iter
    mock_response.get_encoding.return_value = "utf-8"

    with patch("data_sources.web_reader.validate_url_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = None  # SSRF pass

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_response
            mock_get.return_value = mock_ctx

            res = await reader.read_url("https://example.com/huge-file.html")
            assert res["success"] is False
            assert "exceeded" in res["error"]


@pytest.mark.asyncio
async def test_web_reader_browser_fallback_on_403_challenge():
    """Verify that HTTP 403 triggers browser fallback and returns rendered content."""
    reader = WebReader(browser_fallback=True)

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.reason = "Forbidden"

    with patch("data_sources.web_reader.validate_url_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = None

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_response
            mock_get.return_value = mock_ctx

            with patch.object(reader, "_read_url_with_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {
                    "success": True,
                    "url": "https://example.com/cf-protected",
                    "title": "Unblocked Article",
                    "content": "Full article content after Cloudflare Turnstile bypass.",
                    "engine": "browser",
                }

                res = await reader.read_url("https://example.com/cf-protected")
                assert res["success"] is True
                assert res["engine"] == "browser"
                assert "Full article content" in res["content"]
                mock_browser.assert_awaited_once_with("https://example.com/cf-protected")


@pytest.mark.asyncio
async def test_web_reader_browser_fallback_on_challenge_content_in_200():
    """Verify that HTTP 200 with Cloudflare challenge text triggers browser fallback."""
    reader = WebReader(browser_fallback=True)

    challenge_html = "<html><head><title>Just a moment...</title></head><body><div class='cf-turnstile'>Verify you are human</div></body></html>"

    async def mock_chunk_iter(*args, **kwargs):
        yield challenge_html.encode("utf-8")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.content.iter_chunked = mock_chunk_iter
    mock_response.get_encoding.return_value = "utf-8"

    with patch("data_sources.web_reader.validate_url_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = None

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_response
            mock_get.return_value = mock_ctx

            with patch.object(reader, "_read_url_with_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {
                    "success": True,
                    "url": "https://example.com/turnstile-page",
                    "title": "Rendered Page",
                    "content": "Rendered paragraph after browser bypass.",
                    "engine": "browser",
                }

                res = await reader.read_url("https://example.com/turnstile-page")
                assert res["success"] is True
                assert res["engine"] == "browser"
                mock_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_reader_browser_fallback_disabled():
    """Verify that when browser_fallback is False, 403 returns HTTP error directly."""
    reader = WebReader(browser_fallback=False)

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.reason = "Forbidden"

    with patch("data_sources.web_reader.validate_url_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = None

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_response
            mock_get.return_value = mock_ctx

            with patch.object(reader, "_read_url_with_browser", new_callable=AsyncMock) as mock_browser:
                res = await reader.read_url("https://example.com/blocked")
                assert res["success"] is False
                assert "HTTP 403" in res["error"]
                mock_browser.assert_not_called()


@pytest.mark.asyncio
async def test_web_reader_browser_fallback_graceful_failure():
    """Verify that if browser fallback returns None, the original HTTP failure is returned."""
    reader = WebReader(browser_fallback=True)

    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.reason = "Forbidden"

    with patch("data_sources.web_reader.validate_url_ip", new_callable=AsyncMock) as mock_val:
        mock_val.return_value = None

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_response
            mock_get.return_value = mock_ctx

            with patch.object(reader, "_read_url_with_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = None  # Browser failed / unavailable

                res = await reader.read_url("https://example.com/blocked")
                assert res["success"] is False
                assert "HTTP 403" in res["error"]

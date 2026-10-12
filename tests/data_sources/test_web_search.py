import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from data_sources.web_search import WebSearchService, get_web_search_service


def _build_mock_session_and_resp(status=200, json_data=None, text_data=None):
    mock_resp = MagicMock()
    mock_resp.status = status
    if json_data is not None:
        mock_resp.json = AsyncMock(return_value=json_data)
    if text_data is not None:
        mock_resp.text = AsyncMock(return_value=text_data)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.get = MagicMock(return_value=mock_resp)
    return mock_session, mock_resp


class TestWebSearchService:

    def test_key_loading_travily_keys(self):
        with patch.dict(os.environ, {"TRAVILY_API_KEYS": "key1, key2 , key3"}, clear=True):
            svc = WebSearchService(settings={})
            assert svc.tavily_keys == ["key1", "key2", "key3"]

    def test_key_loading_tavily_keys(self):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": "tvly-1, tvly-2"}, clear=True):
            svc = WebSearchService(settings={})
            assert svc.tavily_keys == ["tvly-1", "tvly-2"]

    def test_key_loading_single_tavily_key(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-single"}, clear=True):
            svc = WebSearchService(settings={})
            assert svc.tavily_keys == ["tvly-single"]

    def test_key_loading_ignores_unexpanded_placeholder_and_uses_single_key(self):
        settings = {
            "search": {
                "tavily_api_keys": "${TRAVILY_API_KEYS:${TAVILY_API_KEYS:}}",
                "tavily_api_key": "${TAVILY_API_KEY:}",
                "brave_api_key": "${BRAVE_API_KEY:}",
            }
        }
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-fallback-key", "BRAVE_API_KEY": "brave-fallback"}, clear=True):
            svc = WebSearchService(settings=settings)
            assert svc.tavily_keys == ["tvly-fallback-key"]
            assert svc.brave_api_key == "brave-fallback"

    def test_key_rotation(self):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": "k1,k2,k3"}, clear=True):
            svc = WebSearchService(settings={})
            assert svc._get_next_tavily_key() == "k1"
            assert svc._get_next_tavily_key() == "k2"
            assert svc._get_next_tavily_key() == "k3"
            assert svc._get_next_tavily_key() == "k1"

    @pytest.mark.asyncio
    async def test_tavily_search_success(self):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": "k1"}, clear=True):
            svc = WebSearchService(settings={})
            
            mock_response_data = {
                "results": [
                    {
                        "title": "Fed Holds Rates",
                        "url": "https://example.com/fed",
                        "content": "Federal Reserve kept interest rates unchanged.",
                        "score": 0.95
                    }
                ]
            }

            mock_session, _ = _build_mock_session_and_resp(status=200, json_data=mock_response_data)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await svc.search("Federal Reserve rate decision", search_depth="fast", max_results=3)

            assert result["source"] == "tavily"
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Fed Holds Rates"
            assert result["results"][0]["url"] == "https://example.com/fed"

    @pytest.mark.asyncio
    async def test_tavily_failover_on_429(self):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": "k1,k2"}, clear=True):
            svc = WebSearchService(settings={})
            
            # Key 1 returns 429, Key 2 returns 200
            resp_429 = MagicMock()
            resp_429.status = 429
            resp_429.__aenter__ = AsyncMock(return_value=resp_429)
            resp_429.__aexit__ = AsyncMock(return_value=None)

            resp_200 = MagicMock()
            resp_200.status = 200
            resp_200.json = AsyncMock(return_value={
                "results": [{"title": "Success on Key 2", "url": "https://example.com/2", "content": "Ok"}]
            })
            resp_200.__aenter__ = AsyncMock(return_value=resp_200)
            resp_200.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(side_effect=[resp_429, resp_200])

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await svc.search("inflation data", search_depth="fast")

            assert result["source"] == "tavily"
            assert result["results"][0]["title"] == "Success on Key 2"

    @pytest.mark.asyncio
    async def test_fallback_to_brave_search(self):
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "brave-key"}, clear=True):
            svc = WebSearchService(settings={})
            svc.tavily_keys = []

            mock_brave_data = {
                "web": {
                    "results": [
                        {
                            "title": "Brave ECB Decision",
                            "url": "https://brave.com/ecb",
                            "description": "ECB cuts deposit rate by 25bps"
                        }
                    ]
                }
            }

            mock_session, _ = _build_mock_session_and_resp(status=200, json_data=mock_brave_data)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await svc.search("ECB rate decision")

            assert result["source"] == "brave"
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Brave ECB Decision"

    @pytest.mark.asyncio
    async def test_fallback_to_duckduckgo_html(self):
        with patch.dict(os.environ, {}, clear=True):
            svc = WebSearchService(settings={})
            svc.tavily_keys = []
            svc.brave_api_key = ""

            sample_html = """
            <html>
                <body>
                    <div class="result">
                        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fddg">Gold News</a>
                        <a class="result__snippet">DuckDuckGo snippet content about gold price breakout.</a>
                    </div>
                </body>
            </html>
            """

            mock_session, _ = _build_mock_session_and_resp(status=200, text_data=sample_html)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await svc.search("XAUUSD gold rally")

            assert result["source"] == "duckduckgo"
            assert len(result["results"]) >= 1
            assert "gold price breakout" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_ttl_cache(self):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": "k1"}, clear=True):
            svc = WebSearchService(settings={})
            
            mock_session, _ = _build_mock_session_and_resp(
                status=200,
                json_data={"results": [{"title": "Cached Title", "url": "https://example.com", "content": "Cached Content"}]}
            )

            with patch("aiohttp.ClientSession", return_value=mock_session):
                # Call 1
                res1 = await svc.search("cache test query", search_depth="fast")
                assert not res1.get("cached")

                # Call 2 with identical query & depth
                res2 = await svc.search("cache test query", search_depth="fast")
                assert res2.get("cached") is True
                assert res2["results"][0]["title"] == "Cached Title"

                # mock_session.post should have been called only once due to TTL cache
                assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_lru_cache_bounded_eviction(self):
        svc = WebSearchService(settings={"search": {"max_cache_size": 3}})
        assert svc._max_cache_size == 3

        import utils.clock as clock
        t0 = clock.now()
        svc._put_cache("k1", (t0, {"q": 1}))
        svc._put_cache("k2", (t0, {"q": 2}))
        svc._put_cache("k3", (t0, {"q": 3}))

        assert list(svc._cache.keys()) == ["k1", "k2", "k3"]

        # Access k1 so it moves to MRU
        async with svc._lock:
            cached_at, cached_res = svc._cache["k1"]
            svc._cache.move_to_end("k1")

        # Now insert k4, which should evict the LRU item ("k2")
        svc._put_cache("k4", (t0, {"q": 4}))
        assert "k2" not in svc._cache
        assert "k1" in svc._cache
        assert "k3" in svc._cache
        assert "k4" in svc._cache
        assert len(svc._cache) == 3

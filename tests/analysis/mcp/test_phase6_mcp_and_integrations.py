# ==============================================================================
# File: tests/analysis/mcp/test_phase6_mcp_and_integrations.py
# ==============================================================================

import asyncio
import base64
import os
import tempfile
import pytest

from analysis.mcp.mcp_death_supervisor import McpDeathSupervisor
from analysis.mcp.mcp_schema_cache import McpSchemaCache
from analysis.mcp.client import McpServerProcess
from data_sources.web_search import SearchMemo
from analysis.tools.domain.multimodal_tools import (
    VisionImageProcessor,
    ChartVisionInput,
    handle_chart_vision_analyze,
    MAX_IMAGE_BYTES,
)


def test_mcp_death_supervisor_registration():
    # Register dummy pid
    McpDeathSupervisor.register_process(999999)
    assert 999999 in McpDeathSupervisor._tracked_pids

    McpDeathSupervisor.unregister_process(999999)
    assert 999999 not in McpDeathSupervisor._tracked_pids


def test_mcp_schema_cache_fingerprint_and_invalidation():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = McpSchemaCache(cache_dir=tmpdir)
        cfg = {"command": "python", "args": ["-m", "mcp_server"], "env": {"ENV_VAR": "1"}}

        tools = [
            {"name": "fetch_orderbook", "description": "Fetches MT5 orderbook"},
            {"name": "calc_spread", "description": "Calculates cross-pair spread"},
        ]

        cache.save_cached_tools("crypto_mcp", cfg, tools)

        # Hit
        loaded = cache.get_cached_tools("crypto_mcp", cfg)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["name"] == "fetch_orderbook"

        # Mutate config -> Miss
        mutated_cfg = {"command": "python", "args": ["-m", "mcp_server_v2"], "env": {"ENV_VAR": "1"}}
        assert cache.get_cached_tools("crypto_mcp", mutated_cfg) is None


def test_mcp_server_process_transport_config():
    p_stdio = McpServerProcess("local_proc", {"command": "python", "args": []})
    assert p_stdio.transport == "stdio"

    p_http = McpServerProcess("remote_proc", {"transport": "http", "url": "http://localhost:8000/mcp"})
    assert p_http.transport == "http"
    assert p_http.url == "http://localhost:8000/mcp"


@pytest.mark.asyncio
async def test_search_memo_single_flight_coalescing():
    memo = SearchMemo()
    call_count = 0

    async def mock_heavy_search():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"query": "fed rate decision", "results": ["Rate unchanged"]}

    # Launch 5 concurrent calls with identical cache key
    tasks = [
        memo.execute_coalesced("key_fed_rate", mock_heavy_search)
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    # The actual network/heavy factory must only execute once!
    assert call_count == 1

    # Leader has original dict, followers have coalesced=True
    coalesced_count = sum(1 for r in results if r.get("coalesced") is True)
    assert coalesced_count == 4


@pytest.mark.asyncio
async def test_multimodal_vision_clamp_and_repeat_refusal():
    # 1. Test fallback with non-image raw bytes
    raw_payload = b"\x00\xFF" * (200 * 1024)  # 400 KB
    clamped_raw, mime_raw = VisionImageProcessor.clamp_image_to_budget(raw_payload)
    assert len(clamped_raw) <= MAX_IMAGE_BYTES

    # 2. Test with real PIL image
    from PIL import Image
    import io
    img = Image.new("RGB", (1200, 1200), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    clamped_img, mime_img = VisionImageProcessor.clamp_image_to_budget(png_bytes)
    assert len(clamped_img) <= MAX_IMAGE_BYTES
    assert mime_img == "image/jpeg"

    # 3. Test handle_chart_vision_analyze execution
    b64_img = base64.b64encode(png_bytes).decode("ascii")
    inp = ChartVisionInput(
        image_path_or_base64=b64_img,
        symbol="EURUSD",
        timeframe="H1",
    )
    res = await handle_chart_vision_analyze(inp)
    assert res["success"] is True
    assert res["symbol"] == "EURUSD"
    assert res["clamped_bytes"] <= MAX_IMAGE_BYTES

    # 4. Repeat refusal test: same input immediately returns cached analysis
    repeat_res = await handle_chart_vision_analyze(inp)
    assert repeat_res["success"] is True
    assert repeat_res.get("cached_analysis") is True

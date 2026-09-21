"""
Unit tests for Output Spill Store (Phase 7.4).
"""

import tempfile
from pathlib import Path
import pytest
from utils.storage.spill_store import SpillStore


def test_spill_store_text_artifact():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = SpillStore(base_dir=tmp_dir, max_preview_chars=200)

        # Oversized text payload
        large_text = "Headline: Central bank interest rate hike shock.\n" + ("Data row analysis with macroeconomic impact indicators.\n" * 20)
        res = store.spill_artifact(large_text, artifact_type="news_feed", preview_chars=100)

        assert res["spilled"] is True
        assert Path(res["file_path"]).exists()
        assert len(res["preview"]) <= 250  # Bounded preview with omission notice
        assert "spilled to disk" in res["preview"]

        # Reload
        reloaded = store.load_artifact(res["artifact_id"])
        assert reloaded == large_text


def test_spill_store_json_artifact():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = SpillStore(base_dir=tmp_dir, max_preview_chars=150)

        data = {
            "order_book": [{"price": 2000.0 + i, "volume": 10.0 * i} for i in range(50)],
            "symbol": "XAUUSD",
        }
        res = store.spill_artifact(data, artifact_type="order_book")

        assert res["spilled"] is True
        assert res["type"] == "order_book"

        reloaded = store.load_artifact(res["artifact_id"])
        assert isinstance(reloaded, dict)
        assert reloaded["symbol"] == "XAUUSD"
        assert len(reloaded["order_book"]) == 50

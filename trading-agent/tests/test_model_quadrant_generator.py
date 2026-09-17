# ==============================================================================
# File: tests/test_model_quadrant_generator.py
# ==============================================================================

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure scripts directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

csv_path = root_dir / "trading-agent" / "benchmark" / "results" / "model_all.csv"
if not csv_path.exists():
    csv_path = root_dir / "model_all.csv"

from scripts.generate_model_quadrant import (
    clean_num,
    parse_csv,
    compute_stats,
    generate_html,
)


def test_clean_num():
    assert clean_num("1,80") == 1.8
    assert clean_num("$10,00") == 10.0
    assert clean_num("36.000,00") == 36000.0
    assert clean_num("0,00") == 0.0
    assert clean_num("", default=5.0) == 5.0
    assert clean_num("invalid", default=0.0) == 0.0


def test_parse_csv_and_stats():
    assert csv_path.exists(), f"model_all.csv must exist (checked {csv_path})"

    models = parse_csv(str(csv_path))
    assert len(models) == 72, f"Expected 72 models, got {len(models)}"

    # Check structure of parsed model
    m0 = models[0]
    assert "provider" in m0
    assert "model" in m0
    assert "cost" in m0
    assert "score" in m0
    assert "thinking" in m0
    assert isinstance(m0["cost"], float)
    assert isinstance(m0["score"], float)

    # Check stats
    stats = compute_stats(models)
    assert stats["count"] == 72
    assert stats["score_min"] == 21.9
    assert stats["score_max"] == 59.15
    assert stats["cost_min"] == 0.0
    assert stats["cost_max"] == 1.8
    assert stats["score_median"] == 44.95
    assert stats["cost_median"] == 0.115


def test_generate_html():
    models = parse_csv(str(csv_path))
    stats = compute_stats(models)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        generate_html(models, stats, tmp_path)
        assert os.path.exists(tmp_path)
        assert os.path.getsize(tmp_path) > 20000

        with open(tmp_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "echarts" in content
        assert "THE SWEET SPOT" in content
        assert "Kuadran Evaluasi Model LLM" in content
        assert "datasetStats" in content
        assert "claude-fable-5" in content
        assert "numScore" in content
        assert "numCost" in content
        assert "preset-btn" in content
        assert "btnToggleClickMode" in content
        assert "setThresholdsFromModel" in content
        assert "liveCounterPill" in content
        assert "localStorage" in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

from typing import Any, Dict, List
import pytest
from monika.infrastructure.llm.caveman_compressor import compress_tool_payload


def test_compress_tool_payload_basic():
    """Verify standard compression behavior: floats rounded, nulls stripped, preserve_keys respected."""
    raw = {
        "symbol": "EURUSD",
        "empty_str": "",
        "none_val": None,
        "empty_list": [],
        "preserve_empty": [],  # not in preserve_keys
        "events": [],  # in preserve_keys
        "price": 1.123456789,
        "tiny_float": 0.0000000001,
    }
    compressed = compress_tool_payload(raw)
    assert compressed["symbol"] == "EURUSD"
    assert "empty_str" not in compressed
    assert "none_val" not in compressed
    assert "empty_list" not in compressed
    assert "preserve_empty" not in compressed
    assert "events" in compressed
    assert compressed["events"] == []
    assert compressed["price"] == 1.12346
    assert compressed["tiny_float"] == 0.0


def test_compress_tool_payload_circular_dict():
    """Verify circular dictionary references do not cause RecursionError and are pruned safely."""
    cyclic_dict: Dict[str, Any] = {"status": "ok", "count": 10}
    cyclic_dict["self_ref"] = cyclic_dict

    # Must complete safely without RecursionError
    result = compress_tool_payload(cyclic_dict)
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert result["count"] == 10
    assert "self_ref" not in result


def test_compress_tool_payload_circular_list():
    """Verify circular list references do not cause RecursionError and are pruned safely."""
    cyclic_list: List[Any] = [1, 2, 3]
    cyclic_list.append(cyclic_list)

    result = compress_tool_payload(cyclic_list)
    assert isinstance(result, list)
    assert result == [1, 2, 3]


def test_compress_tool_payload_diamond_dag():
    """Verify non-circular diamond DAG structures preserve both branches correctly."""
    leaf = {"value": 12.345678, "news": []}
    dag = {
        "branch_a": leaf,
        "branch_b": leaf,
    }

    result = compress_tool_payload(dag)
    assert isinstance(result, dict)
    assert "branch_a" in result
    assert "branch_b" in result
    assert result["branch_a"]["value"] == 12.34568
    assert result["branch_b"]["value"] == 12.34568
    assert result["branch_a"]["news"] == []
    assert result["branch_b"]["news"] == []


def test_compress_tool_payload_depth_ceiling():
    """Verify pathological nesting depth is capped at max_depth without stack overflow."""
    # Build 50-level nested dict
    curr: Dict[str, Any] = {"deep": "value"}
    for i in range(50):
        curr = {f"level_{i}": curr}

    result = compress_tool_payload(curr, max_depth=10)
    assert isinstance(result, dict)
    # Beyond max_depth, data is returned without crashing

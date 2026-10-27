import time
from monika.infrastructure.providers.base_provider import extract_and_parse_json


def test_extract_and_parse_json_performance_on_huge_truncated_payload():
    """Memastikan payload raksasa (400k+ chars) yang terpotong tidak memblokir CPU lebih dari 1.5 detik."""
    lines = [
        f'    "- Key evidence item {i}: price at 1.08{i:03d} rejected with RSI 65.4, stochastic cross, volume spike {i * 10} contracts"'
        for i in range(4000)
    ]
    # Incomplete/truncated payload with invalid internal syntax
    text = (
        "{\n"
        '  "directional_bias": "BULLISH",\n'
        '  "confidence": 0.75,\n'
        '  "analysis": "Here is an unescaped " quote early on in the response:\n'
        + "\n".join(lines)
        + '\n  "key_evidence": ["truncated'
    )
    t0 = time.perf_counter()
    res = extract_and_parse_json(text)
    elapsed = time.perf_counter() - t0

    # Must complete fast without O(N^2) event loop freeze
    assert elapsed < 1.5, f"Parsing took {elapsed:.2f}s, exceeding 1.5s freeze safety budget"
    # Unrepairable garbage must return None rather than a dummy empty dict {}
    assert res is None


def test_extract_and_parse_json_capped_tail_trim_success():
    """Memverifikasi bahwa pemotongan ekor (tail-trimming) berhasil memperbaiki truncation dalam batas 15 baris."""
    raw_text = (
        "{\n"
        '  "status": "ok",\n'
        '  "signal": "BULLISH",\n'
        '  "items": [\n'
        '    {"id": 1, "name": "valid item"},\n'
        '    {"id": 2, "name": "truncated item that gets cut off'
    )
    parsed = extract_and_parse_json(raw_text)
    assert parsed is not None
    assert parsed["status"] == "ok"
    assert parsed["signal"] == "BULLISH"
    assert len(parsed["items"]) == 2
    assert parsed["items"][0]["name"] == "valid item"

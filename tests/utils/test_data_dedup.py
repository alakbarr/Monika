"""
Unit tests for generation-tracked data fetch deduplication.
"""

from utils.llm.data_dedup import DataFetchDeduplicator


def test_data_fetch_deduplication():
    dedup = DataFetchDeduplicator()

    payload = "XAUUSD H1 OHLC: open=2650.0 high=2665.0 low=2648.0 close=2662.0 volume=12500 atr=12.5"
    args = {"symbol": "XAUUSD", "timeframe": "H1"}

    # 1. First fetch -> returns None (new data recorded)
    res1 = dedup.check_and_record("get_price_history", args, payload)
    assert res1 is None

    # 2. Identical fetch in same generation -> returns stub notice
    res2 = dedup.check_and_record("get_price_history", args, payload)
    assert res2 is not None
    assert "Data unchanged since previous fetch" in res2
    assert "gen 1" in res2

    # 3. Different args (e.g. H4) -> returns None
    args_h4 = {"symbol": "XAUUSD", "timeframe": "H4"}
    res3 = dedup.check_and_record("get_price_history", args_h4, payload)
    assert res3 is None

    # 4. Context compaction occurs -> invalidates cache
    dedup.invalidate_on_compaction()

    # 5. First fetch in new generation (gen 2) -> returns None (full data)
    res4 = dedup.check_and_record("get_price_history", args, payload)
    assert res4 is None

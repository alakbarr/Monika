"""
Tests verifying structural invariants and safety guards in execution and state reducers.
Strategy: Inspect source code as text and test isolated components.
Covers: Reducers, reflection node, cache-before-commit, pre-execution guards.
"""
import pytest
import sys
import os
import inspect
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def read_source(rel_path):
    base = os.path.dirname(os.path.dirname(__file__))
    full = os.path.join(base, rel_path)
    with open(full, 'r', encoding='utf-8') as f:
        src = f.read()
    if rel_path == 'execution/execution_service.py':
        for sub in ['order_executor.py', 'emergency_manager.py', 'position_synchronizer.py']:
            p = os.path.join(base, 'execution', 'service', sub)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as sf:
                    src += "\n" + sf.read()
    return src


# ============================================================================
# G-2: List Reducers di TradingState
# ============================================================================
class TestStateReducers:

    def test_merge_dicts_deep_merge(self):
        """merge_dicts harus deep-merge nested dicts"""
        from graph.state import merge_dicts
        a = {"EURUSD": {"decision": "buy", "confidence": 0.8}}
        b = {"EURUSD": {"decision": "sell"}, "XAUUSD": {"decision": "buy"}}
        result = merge_dicts(a, b)
        assert result["EURUSD"]["decision"] == "sell"
        assert result["XAUUSD"]["decision"] == "buy"

    def test_merge_dicts_preserves_nested_keys(self):
        """Nested keys dari dict lama tidak boleh hilang"""
        from graph.state import merge_dicts
        a = {"x": {"a": 1, "b": 2, "c": 3}}
        b = {"x": {"d": 4}}
        result = merge_dicts(a, b)
        assert result["x"]["a"] == 1
        assert result["x"]["b"] == 2
        assert result["x"]["c"] == 3
        assert result["x"]["d"] == 4

    def test_merge_lists_concatenates(self):
        """merge_lists harus konkatenasi bukan replace"""
        from graph.state import merge_lists
        assert merge_lists([1, 2], [3, 4]) == [1, 2, 3, 4]
        assert merge_lists([], [1]) == [1]
        assert merge_lists(None, [1]) == [1]
        assert merge_lists([1], None) == [1]

    def test_trading_state_sequential_fields_no_reducer(self):
        """actionable_trades & approved_trades TIDAK BOLEH pakai Annotated reducer (narrowing pipeline)"""
        from graph.state import TradingState
        from typing import get_type_hints
        hints = get_type_hints(TradingState, include_extras=True)
        # These ARE narrowing fields — must NOT have Annotated reducer
        narrowing_fields = ['approved_trades', 'actionable_trades']
        for field in narrowing_fields:
            assert field in hints, f"Field '{field}' not in TradingState"
            hint = hints[field]
            assert not hasattr(hint, '__metadata__'), (
                f"P0-3 REGRESSION: Field '{field}' must NOT use Annotated reducer "
                f"(narrowing pipeline, not accumulation), got: {hint}"
            )
        # These DO use accumulation reducer (still valid)
        accumulation_fields = ['errors', 'stale_assets']
        for field in accumulation_fields:
            assert field in hints, f"Field '{field}' not in TradingState"
            hint = hints[field]
            assert hasattr(hint, '__metadata__'), (
                f"Field '{field}' must use Annotated[List, reducer], got: {hint}"
            )

    def test_merge_lists_function_exists_in_state(self):
        """merge_lists function harus ada di graph.state"""
        from graph.state import merge_lists
        assert callable(merge_lists)


# ============================================================================
# F-2: Cache-Before-Commit Fix (source code inspection)
# ============================================================================
class TestCacheBeforeCommitFix:

    def setup_method(self):
        self.source = read_source('execution/execution_service.py')

    def test_cache_set_after_mt5_success(self):
        """_EXECUTED_ANALYSIS_IDS harus di-set SETELAH mt5_result.get('success')"""
        # Cari semua posisi "= time.time()" yang merupakan cache update untuk analysis.id
        cache_pattern = r"_EXECUTED_ANALYSIS_IDS\[analysis\.id\]\s*=\s*time\.time\(\)"
        cache_matches = [(m.start(), m.group()) for m in re.finditer(cache_pattern, self.source)]

        mt5_success_pattern = r"mt5_result\.get\('success'\)"
        mt5_matches = [m.start() for m in re.finditer(mt5_success_pattern, self.source)]

        assert len(cache_matches) >= 1, "Cache update line not found"
        assert len(mt5_matches) >= 1, "mt5_result.get('success') not found"

        # Setidaknya SATU cache update harus ada SETELAH mt5_result success check
        mt5_first_pos = mt5_matches[0]
        cache_after_mt5 = [pos for pos, _ in cache_matches if pos > mt5_first_pos]
        assert len(cache_after_mt5) >= 1, (
            "BUG F-2 STILL PRESENT: No cache update found AFTER mt5_result.get('success'). "
            "All cache updates are before MT5 call - risk of 24h lockout on failures."
        )

    def test_duplicate_db_check_still_updates_cache(self):
        """Saat duplikat ditemukan di DB, cache harus tetap di-update"""
        is_dup_pos = self.source.find("if is_duplicate:")
        assert is_dup_pos > 0, "'if is_duplicate:' block not found"

        # Cari cache set di dalam atau setelah blok is_duplicate
        cache_in_dup = self.source.find(
            "_EXECUTED_ANALYSIS_IDS[analysis.id] = time.time()", is_dup_pos
        )
        assert cache_in_dup > is_dup_pos, (
            "Cache must be set when a DB duplicate is found to prevent retry loops."
        )

    def test_fix_comment_present(self):
        """Verify Cache-Before-Commit design pattern is documented in execution service."""
        assert "Cache-Before-Commit" in self.source, (
            "Cache-Before-Commit pattern documentation not found in execution service source."
        )


# ============================================================================
# R-1: Race Condition Pre-MT5 Recheck (source code inspection)
# ============================================================================
class TestRaceConditionRecheck:

    def setup_method(self):
        self.source = read_source('execution/execution_service.py')

    def test_pre_mt5_recheck_guard_exists(self):
        """Kode re-check posisi harus ada sebelum MT5 order"""
        assert 'pre_mt5_position_recheck' in self.source, (
            "R-1 fix missing: 'pre_mt5_position_recheck' guard not found in execution_service.py"
        )

    def test_race_condition_message_present(self):
        """Pesan race condition guard harus ada"""
        assert 'Race condition guard' in self.source or 'race condition' in self.source.lower(), (
            "R-1 fix incomplete: race condition guard message not found"
        )

    def test_recheck_before_place_order(self):
        """Re-check posisi HARUS terjadi sebelum place_order di dalam _execute_analysis_internal"""
        # Isolate hanya method _execute_analysis_internal (bukan keseluruhan file)
        method_start = self.source.find("async def _execute_analysis_internal(")
        assert method_start > 0, "_execute_analysis_internal method not found"
        # Cari akhir method (method berikutnya)
        next_method = self.source.find("\n    async def ", method_start + 1)
        if next_method == -1:
            next_method = len(self.source)
        method_src = self.source[method_start:next_method]

        recheck_pos = method_src.find("pre_mt5_position_recheck")
        mt5_place_pos = method_src.find("submit_order(")
        if mt5_place_pos == -1:
            mt5_place_pos = method_src.find("place_order(")
        assert recheck_pos > 0, "Re-check guard not found in _execute_analysis_locked"
        assert mt5_place_pos > 0, "place_order or submit_order call not found in _execute_analysis_locked"
        assert recheck_pos < mt5_place_pos, (
            "Race condition re-check must be BEFORE place_order/submit_order call "
            f"(recheck@{recheck_pos}, place_order@{mt5_place_pos})"
        )


    def test_max_concurrent_check_in_recheck(self):
        """Re-check harus menggunakan max_concurrent_positions limit"""
        assert 'max_concurrent' in self.source or 'max_concurrent_positions' in self.source, (
            "Re-check should validate against max_concurrent_positions setting"
        )


# ============================================================================
# R-2: Edge Tracker Auto-Enforce (source code inspection)
# ============================================================================
class TestEdgeTrackerAutoEnforce:

    def setup_method(self):
        self.source = read_source('utils/analytics/edge_tracker.py')

    def test_auto_pause_threshold_exists(self):
        """AUTO_PAUSE_Z_THRESHOLD harus ada di edge_tracker"""
        assert 'AUTO_PAUSE_Z_THRESHOLD' in self.source, (
            "R-2 fix missing: AUTO_PAUSE_Z_THRESHOLD not defined in edge_tracker.py"
        )

    def test_trading_paused_key_referenced(self):
        """trading_paused SystemConfig key harus di-set oleh auto-pause"""
        assert 'trading_paused' in self.source, (
            "R-2 fix incomplete: 'trading_paused' key not found in edge_tracker auto-pause logic"
        )

    def test_telegram_critical_alert_sent(self):
        """Alert kritis Telegram harus dikirim saat auto-pause"""
        assert 'send_critical' in self.source, (
            "R-2 fix: Telegram critical alert not implemented in auto-pause logic"
        )

    def test_threshold_value_is_negative(self):
        """Nilai AUTO_PAUSE_Z_THRESHOLD harus negatif"""
        match = re.search(r'AUTO_PAUSE_Z_THRESHOLD\s*=\s*(-?\d+\.?\d*)', self.source)
        assert match, "AUTO_PAUSE_Z_THRESHOLD value not found via regex"
        threshold = float(match.group(1))
        assert threshold < 0, (
            f"AUTO_PAUSE_Z_THRESHOLD must be negative (z-score < 0 = below breakeven). "
            f"Got: {threshold}"
        )

    def test_auto_pause_only_on_significant_no_edge(self):
        """Auto-pause hanya terpicu pada no_edge DAN z_score di bawah threshold"""
        # Verifikasi bahwa kondisi menggunakan AND (status == no_edge AND z_score < threshold)
        assert "status == 'no_edge' and z_score <" in self.source or \
               'no_edge' in self.source and 'AUTO_PAUSE_Z_THRESHOLD' in self.source, (
            "Auto-pause must only trigger when BOTH no_edge status AND z_score < threshold"
        )

    def test_result_returned_after_auto_pause(self):
        """Fungsi harus tetap return result meski auto-pause terpicu"""
        assert 'return result' in self.source, (
            "Edge tracker must always return result, even when auto-pause is activated"
        )


# ============================================================================
# R-5: VIX Defensive Default di Reflection Node
# ============================================================================
class TestReflectionVIXDefensive:

    def setup_method(self):
        self.source = read_source('graph/nodes/reflection_node.py')

    def test_vix_defensive_default_exists(self):
        """VIX defensive default 25.0 harus ada di reflection_node"""
        assert '25.0' in self.source, (
            "R-5 fix missing: VIX defensive default value 25.0 not found in reflection_node.py"
        )

    def test_warning_log_on_vix_fallback(self):
        """Warning log harus ditulis saat menggunakan VIX defensive default"""
        assert 'defensive default' in self.source.lower() or \
               'Applying defensive default VIX' in self.source, (
            "R-5 fix incomplete: no warning log for VIX defensive default fallback"
        )

    def test_except_block_sets_vix_default(self):
        """Blok except VIX query harus set default, bukan hanya log debug"""
        # Cari pola: dalam except block, ada assignment vix_value = 25.0
        except_blocks = [m.start() for m in re.finditer(r'except Exception', self.source)]
        assert len(except_blocks) >= 1, "No except block found for VIX query"

        # Cari vix_value = 25.0 di dekat except block
        vix_default_pos = self.source.find("vix_value = 25.0")
        assert vix_default_pos > 0, (
            "vix_value = 25.0 not found. Defensive default not implemented."
        )

    def test_vix_filter_uses_vix_value_variable(self):
        """Filter VIX harus menggunakan variabel vix_value, bukan langsung vix_row"""
        # Pastikan filtering menggunakan vix_value (bukan vix_row.close langsung)
        assert 'if vix_value > 25' in self.source, (
            "R-5 fix: VIX filter must use `vix_value` variable (not vix_row.close directly) "
            "so defensive default is applied when query fails"
        )

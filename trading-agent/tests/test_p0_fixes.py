"""
Tests untuk P0 fixes dari IMPLEMENTATION_PLAN.md.
Strategy: source code inspection (no heavy DB imports).
"""
import pytest
import re

def read_source(rel_path):
    import os
    base = os.path.join(os.path.dirname(__file__), '..')
    with open(os.path.join(base, rel_path), 'r', encoding='utf-8') as f:
        return f.read()


class TestP01PaperTrackerDesync:
    """P0-1: Paper Position rows harus ikut closed saat PaperTradeRecord closed."""

    def setup_method(self):
        self.source = read_source('utils/analytics/paper_tracker.py')

    def test_close_linked_position_method_exists(self):
        assert '_close_linked_position' in self.source, \
            "P0-1 MISSING: _close_linked_position method not found in paper_tracker.py"

    def test_position_imported(self):
        assert 'from database.models import' in self.source
        assert 'Position' in self.source, \
            "P0-1 MISSING: Position not imported in paper_tracker.py"

    def test_called_in_max_holding_time_branch(self):
        idx = self.source.find("'max_holding_time'")
        assert idx > 0, "max_holding_time branch not found"
        snippet = self.source[idx:idx+500]
        assert '_close_linked_position' in snippet, \
            "P0-1 MISSING: _close_linked_position not called in max_holding_time branch"

    def test_called_in_expired_limit_branch(self):
        idx = self.source.find("'expired_limit'")
        assert idx > 0, "expired_limit branch not found"
        snippet = self.source[idx:idx+400]
        assert '_close_linked_position' in snippet, \
            "P0-1 MISSING: _close_linked_position not called in expired_limit branch"

    def test_called_in_sl_tp_branch(self):
        idx = self.source.find('closed.append(result)')
        assert idx > 0, "SL/TP result append not found"
        snippet = self.source[idx:idx+300]
        assert '_close_linked_position' in snippet, \
            "P0-1 MISSING: _close_linked_position not called after SL/TP hit result"


class TestP02ToolSchemaMismatch:
    """P0-2: SUBMIT_FUNDAMENTAL_BRIEF schema harus pakai SubmitFundamentalBriefSchema."""

    def setup_method(self):
        self.source = read_source('analysis/tools/tools_definitions.py')

    def test_correct_schema_used(self):
        match = re.search(r'_fundamental_brief_schema\s*=\s*get_tool_schema\((\w+)\)', self.source)
        assert match, "_fundamental_brief_schema assignment not found"
        schema_name = match.group(1)
        assert schema_name == 'SubmitFundamentalBriefSchema', (
            f"P0-2 BUG: Using '{schema_name}' instead of 'SubmitFundamentalBriefSchema'. "
        )

    def test_legacy_schema_not_imported(self):
        assert 'FundamentalBriefSchema' not in self.source or \
               'from analysis.schemas.pydantic_schemas import FundamentalBriefSchema' not in self.source, \
            "P0-2: Legacy FundamentalBriefSchema still imported"


class TestP03ActionableTradesReducer:
    """P0-3: actionable_trades dan approved_trades TIDAK BOLEH pakai merge_lists reducer."""

    def test_no_annotated_reducer_on_pipeline_fields(self):
        from graph.state import TradingState
        from typing import get_type_hints
        hints = get_type_hints(TradingState, include_extras=True)
        for field in ('actionable_trades', 'approved_trades'):
            hint = hints[field]
            assert not hasattr(hint, '__metadata__'), (
                f"P0-3 REGRESSION: '{field}' has Annotated reducer. "
            )

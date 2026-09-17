import pytest
import os

def read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..')
    full = os.path.join(base, rel_path)
    with open(full, 'r', encoding='utf-8') as f:
        src = f.read()
    if rel_path == 'analysis/stages/per_asset_stage.py':
        for sub in ['runner.py', 'context_builder.py']:
            p = os.path.join(base, 'analysis', 'stages', 'per_asset', sub)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as sf:
                    src += "\n" + sf.read()
    return src

class TestP21StrategyRollback:
    def test_session_rollback_in_except(self):
        src = read_source('analysis/strategies/registry.py')
        except_idx = src.find('except Exception as e:')
        assert except_idx > 0, "P2-1 MISSING"
        assert 'session.rollback()' in src[except_idx:], "P2-1 MISSING"

class TestP22Stage1ConfidenceRefactor:
    def setup_method(self):
        self.src = read_source('analysis/stages/per_asset_stage.py')

    def test_fetch_method_exists(self):
        assert 'def _fetch_stage1_confidence' in self.src, "P2-2 MISSING"

    def test_run_one_uses_param(self):
        assert 'stage1_confidence: float' in self.src, "P2-2 MISSING"
        assert 'self._stage1_confidence' not in self.src, "P2-2 BUG"

class TestP23SQLiteGuard:
    def test_models_have_sqlite_where(self):
        src = read_source('database/models.py')
        assert src.count('sqlite_where=') >= 2, "P2-3 MISSING"

    def test_main_guard_strengthened(self):
        src = read_source('main.py')
        assert 'sqlite' in src.lower() and 'REQUIRED' in src, "P2-3 MISSING"

class TestP24USDJPYTimeframeFilter:
    def test_timeframe_filter(self):
        src = read_source('risk/position_sizing.py')
        usdjpy_block = src.find('PriceOHLCV.symbol == "USDJPY"')
        assert usdjpy_block > 0, "USDJPY query not found"
        assert "PriceOHLCV.timeframe == 'H4'" in src[usdjpy_block:usdjpy_block+200], "P2-4 MISSING"

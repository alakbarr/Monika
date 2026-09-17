import pytest
import os

def read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..')
    with open(os.path.join(base, rel_path), 'r', encoding='utf-8') as f:
        return f.read()

class TestP31StructuredOutputDeleted:
    def test_structured_output_deleted(self):
        base = os.path.join(os.path.dirname(__file__), '..')
        assert not os.path.exists(os.path.join(base, 'analysis', 'schemas', 'structured_output.py')), 'P3-1 MISSING'
        assert not os.path.exists(os.path.join(base, 'tests', 'test_structured_output.py')), 'P3-1 MISSING'

class TestP32CycleStartFix:
    def test_cycle_start_uses_elapsed(self):
        src = read_source('graph/nodes/per_asset_node.py')
        assert "elapsed_total_s" in src and "cycle_start" in src, 'P3-2 MISSING'

class TestP35NewsWatcherForceClassify:
    def test_force_classify_logic(self):
        src = read_source('scheduler/news_watcher.py')
        assert 'asyncio.gather' in src, 'P3-5 MISSING asyncio.gather'
        assert 'force_classify = any(shock_checks)' in src, 'P3-5 MISSING force_classify any'
        assert 'if force_classify or (' in src, 'P3-5 MISSING or clause'

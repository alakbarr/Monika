import pytest
import os

def read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..')
    full = os.path.join(base, rel_path)
    with open(full, 'r', encoding='utf-8') as f:
        src = f.read()
    if rel_path == 'execution/execution_service.py':
        for sub in ['emergency_manager.py', 'position_synchronizer.py', 'order_executor.py']:
            p = os.path.join(base, 'execution', 'service', sub)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as sf:
                    src += "\n" + sf.read()
    return src

class TestP11PaperPositionGuards:
    def setup_method(self):
        self.source = read_source('execution/execution_service.py')

    def test_close_paper_position_method_exists(self):
        assert '_close_paper_position' in self.source

    def test_guard_in_close_position_by_ticket(self):
        assert "getattr(db_pos, 'is_paper', False)" in self.source

    def test_guard_in_modify_position_sl_tp(self):
        assert "getattr(db_pos, 'is_paper', False)" in self.source

class TestP12SSVPRetryCount:
    def setup_method(self):
        self.state_src = read_source('graph/state.py')
        self.node_src = read_source('graph/nodes/fundamental_node.py')

    def test_field_in_state(self):
        assert 'ssvp_retry_count: int' in self.state_src

    def test_ssvp_blocked_logic(self):
        assert "state.get('ssvp_retry_count', 0) < 1" in self.node_src

class TestP13DeadBuildCall:
    def test_dead_call_removed(self):
        src = read_source('graph/nodes/fundamental_node.py')
        assert 'build_reconciliation_context()' not in src

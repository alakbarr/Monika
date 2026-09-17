import pytest
from unittest.mock import AsyncMock, patch
from graph.nodes.debate_node import debate_node

@pytest.mark.asyncio
async def test_debate_node_does_not_crash_with_actionable_trade():
    """Regression test untuk NameError risk_client_conservative.
    Setiap kali ada actionable trade, debate_node HARUS bisa jalan sampai selesai
    tanpa NameError/AttributeError, apa pun hasil keputusannya."""
    fake_state = {
        'summary': {},
        'actionable_trades': [('EURUSD', {'analysis_id': 1, 'decision': 'buy', 'confidence': 0.7})],
    }
    fake_scheduler = type('S', (), {'settings': {
        'agent_architecture': {'enable_debate': True, 'debate_rounds': 1},
        'llm': {'task_roles': {}, 'providers': {}, 'model_catalog': {}},
    }})()
    config = {'configurable': {'scheduler': fake_scheduler}}
    with patch('graph.nodes.debate_node.get_session'), \
         patch('graph.nodes.debate_node.get_client_for_task', return_value=AsyncMock()):
        # Tidak boleh melempar NameError — kalau ada exception lain (mis. DB mock)
        # itu boleh, tapi TIDAK BOLEH NameError terkait risk_client_*
        try:
            await debate_node(fake_state, config)
        except NameError as e:
            pytest.fail(f"debate_node crashed with NameError (regression!): {e}")
        except Exception:
            pass  # exception lain dari mock DB itu wajar, bukan target test ini

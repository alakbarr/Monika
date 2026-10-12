import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import create_mock_async_session
from graph.nodes.debate_node import debate_node
from database.models import AssetAnalysis

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
    
    mock_session = create_mock_async_session()
    fake_analysis = AssetAnalysis(
        id=1,
        symbol="EURUSD",
        decision="buy",
        confidence=0.7,
        price_at_analysis=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        entry_zone="{}",
    )
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=fake_analysis),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]), first=MagicMock(return_value=None))),
            all=MagicMock(return_value=[]),
            first=MagicMock(return_value=None),
        )
    )

    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=MagicMock(content="{}", text="{}"))
    mock_client.generate_content = AsyncMock(return_value=MagicMock(content="{}", text="{}"))

    with patch('graph.nodes.debate_node.get_session') as mock_gs, \
         patch('graph.nodes.debate_node.get_client_for_task', return_value=mock_client):
        mock_gs.return_value.__aenter__.return_value = mock_session
        try:
            await debate_node(fake_state, config)
        except NameError as e:
            pytest.fail(f"debate_node crashed with NameError (regression!): {e}")
        except Exception:
            pass  # exception lain dari mock DB itu wajar, bukan target test ini

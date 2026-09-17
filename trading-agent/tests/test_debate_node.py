import pytest
from unittest.mock import AsyncMock, MagicMock
from graph.state import TradingState
from graph.nodes.debate_node import debate_node

@pytest.mark.asyncio
async def test_debate_node_bypass():
    state = TradingState(
        actionable_trades=[("BTCUSD", {"analysis_id": 1})],
        summary={},
        debate_states={},
        risk_debate_states={},
        investment_verdicts={},
        portfolio_decisions={}
    )
    
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={
                    "agent_architecture": {
                        "enable_debate": False
                    }
                }
            )
        }
    }
    
    result = await debate_node(state, config)
    assert result == {}

@pytest.mark.asyncio
async def test_debate_node_empty_actionable():
    state = TradingState(
        actionable_trades=[],
        summary={},
        debate_states={},
        risk_debate_states={},
        investment_verdicts={},
        portfolio_decisions={}
    )
    
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={
                    "agent_architecture": {
                        "enable_debate": True
                    }
                }
            )
        }
    }
    
    result = await debate_node(state, config)
    assert result == {}

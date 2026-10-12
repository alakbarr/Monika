import pytest
from utils.protocol.ssvp_coordinator import SSVPCoordinator

@pytest.fixture
def mock_settings():
    return {
        "ssvp": {
            "cds_thresholds": {
                "warning": 0.35,
                "sync_trigger": 0.50,
                "block_buysell": 0.65,
                "abort_all": 0.75
            }
        }
    }

@pytest.mark.asyncio
async def test_ssvp_coordinator_init(mock_settings):
    coord = SSVPCoordinator(settings=mock_settings)
    assert coord.warning_threshold == 0.35
    assert coord.sync_threshold == 0.50
    assert coord.block_threshold == 0.65

# Further integration tests would require mocking DB sessions

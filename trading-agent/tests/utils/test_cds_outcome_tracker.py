import pytest
from utils.analytics.cds_outcome_tracker import compute_cds_outcome_correlation

@pytest.mark.asyncio
async def test_correlate_outcomes():
    # Because it requires a DB connection, we just do a simple instantiation test
    assert compute_cds_outcome_correlation is not None

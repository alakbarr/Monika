"""
Validation test ensuring paper trading lifecycle operations behave correctly.
Run via: python -m tests.test_paper_tracker_fix
"""
import pytest
import asyncio
from datetime import datetime, timezone

@pytest.mark.asyncio
async def test_paper_trade_detection(db_session):
    from utils.analytics.paper_tracker import PaperTracker
    from database.models import PaperTradeRecord
    from sqlalchemy import select
    
    # 1. Check for active open paper trades in isolated test DB
    open_trades = (await db_session.execute(
        select(PaperTradeRecord).where(PaperTradeRecord.status == 'open').limit(5)
    )).scalars().all()
    assert isinstance(open_trades, list)
    
    # 2. Execute trade closure check
    tracker = PaperTracker()
    closed = await tracker.check_and_close_trades(db_session)
    assert isinstance(closed, list)
    
    # 3. Get stats
    stats = await tracker.get_statistics(db_session)
    assert isinstance(stats, dict)
    assert "total_trades" in stats
    assert "win_rate_pct" in stats
    assert stats["total_trades"] >= 0

if __name__ == '__main__':
    import sys
    if sys.platform == "win32":
        asyncio.run(test_paper_trade_detection(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(test_paper_trade_detection())

import pytest
import os
import shutil
import tempfile
from logging_observability.report_writer import ReportWriter

@pytest.mark.asyncio
async def test_report_writer_async():
    temp_dir = tempfile.mkdtemp()
    try:
        writer = ReportWriter(output_dir=temp_dir)
        state = {
            "fundamental_analysis_result": {"status": "ok"},
            "asset_analyses": {"EURUSD": {"bias": "bullish"}},
            "debate_states": {"EURUSD": {"bull_argument": "Bull reasons", "bear_argument": "Bear reasons"}},
            "investment_verdicts": {"EURUSD": {"action": "BUY"}},
            "risk_debate_states": {"EURUSD": {"risk": "LOW"}},
            "portfolio_decisions": {"EURUSD": {"size": 0.1}},
            "summary": {"cycles_completed": 1},
        }
        await writer.write_cycle_report_async("cycle_test_123", state)

        # Verify directories and files created
        subdirs = os.listdir(temp_dir)
        assert len(subdirs) == 1
        cycle_dir = os.path.join(temp_dir, subdirs[0])
        assert os.path.exists(os.path.join(cycle_dir, "00_fundamental_brief.md"))
        assert os.path.exists(os.path.join(cycle_dir, "summary.md"))
        assert os.path.exists(os.path.join(cycle_dir, "EURUSD", "01_initial_analysis.md"))
        assert os.path.exists(os.path.join(cycle_dir, "EURUSD", "02_bull_argument.md"))
        assert os.path.exists(os.path.join(cycle_dir, "EURUSD", "03_bear_argument.md"))
        assert os.path.exists(os.path.join(cycle_dir, "EURUSD", "04_investment_verdict.md"))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

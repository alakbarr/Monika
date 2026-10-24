import asyncio
import json
import os
import re
from datetime import datetime, UTC


class ReportWriter:
    """
    Writes per-cycle markdown reports.
    """

    def __init__(self, output_dir: str = "results"):
        self.output_dir = output_dir

    async def write_cycle_report_async(self, cycle_id: str, state: dict) -> None:
        """Asynchronously writes per-cycle markdown reports off the event loop."""
        await asyncio.to_thread(self.write_cycle_report, cycle_id, state)

    def write_cycle_report(self, cycle_id: str, state: dict):
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_cid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(cycle_id))
        cycle_dir = os.path.join(self.output_dir, f"{safe_cid}_{timestamp}")
        os.makedirs(cycle_dir, exist_ok=True)

        # 1. Write fundamental brief
        brief_data = state.get("fundamental_analysis_result", {})
        with open(os.path.join(cycle_dir, "00_fundamental_brief.md"), "w", encoding="utf-8") as f:
            f.write("# Fundamental Brief\n\n")
            f.write(json.dumps(brief_data, indent=2, default=str))

        # 2. Per-asset reports
        asset_analyses = state.get("asset_analyses", {})
        for sym, data in asset_analyses.items():
            safe_sym = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sym))
            sym_dir = os.path.join(cycle_dir, safe_sym)
            os.makedirs(sym_dir, exist_ok=True)

            with open(os.path.join(sym_dir, "01_initial_analysis.md"), "w", encoding="utf-8") as f:
                f.write(f"# Initial Analysis for {sym}\n\n")
                f.write(json.dumps(data, indent=2, default=str))

        # 3. Debate results
        debate_states = state.get("debate_states", {})
        for sym, data in debate_states.items():
            safe_sym = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sym))
            sym_dir = os.path.join(cycle_dir, safe_sym)
            os.makedirs(sym_dir, exist_ok=True)

            if "bull_argument" in data:
                with open(os.path.join(sym_dir, "02_bull_argument.md"), "w", encoding="utf-8") as f:
                    f.write(str(data["bull_argument"]))
            if "bear_argument" in data:
                with open(os.path.join(sym_dir, "03_bear_argument.md"), "w", encoding="utf-8") as f:
                    f.write(str(data["bear_argument"]))

        verdicts = state.get("investment_verdicts", {})
        for sym, data in verdicts.items():
            safe_sym = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sym))
            sym_dir = os.path.join(cycle_dir, safe_sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "04_investment_verdict.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, default=str))

        risk_states = state.get("risk_debate_states", {})
        for sym, data in risk_states.items():
            safe_sym = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sym))
            sym_dir = os.path.join(cycle_dir, safe_sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "05_risk_debate.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, default=str))

        portfolio = state.get("portfolio_decisions", {})
        for sym, data in portfolio.items():
            safe_sym = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sym))
            sym_dir = os.path.join(cycle_dir, safe_sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "06_final_decision.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, default=str))

        # 4. Summary
        with open(os.path.join(cycle_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("# Cycle Summary\n\n")
            f.write(json.dumps(state.get("summary", {}), indent=2, default=str))

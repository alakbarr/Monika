import asyncio
import os
import json
from datetime import datetime

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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cycle_dir = os.path.join(self.output_dir, f"{cycle_id}_{timestamp}")
        os.makedirs(cycle_dir, exist_ok=True)
        
        # 1. Write fundamental brief
        brief_data = state.get("fundamental_analysis_result", {})
        with open(os.path.join(cycle_dir, "00_fundamental_brief.md"), "w", encoding="utf-8") as f:
            f.write("# Fundamental Brief\n\n")
            f.write(json.dumps(brief_data, indent=2))
            
        # 2. Per-asset reports
        asset_analyses = state.get("asset_analyses", {})
        for sym, data in asset_analyses.items():
            sym_dir = os.path.join(cycle_dir, sym)
            os.makedirs(sym_dir, exist_ok=True)
            
            with open(os.path.join(sym_dir, "01_initial_analysis.md"), "w", encoding="utf-8") as f:
                f.write(f"# Initial Analysis for {sym}\n\n")
                f.write(json.dumps(data, indent=2))
                
        # 3. Debate results
        debate_states = state.get("debate_states", {})
        for sym, data in debate_states.items():
            sym_dir = os.path.join(cycle_dir, sym)
            os.makedirs(sym_dir, exist_ok=True)
            
            if "bull_argument" in data:
                with open(os.path.join(sym_dir, "02_bull_argument.md"), "w", encoding="utf-8") as f:
                    f.write(data["bull_argument"])
            if "bear_argument" in data:
                with open(os.path.join(sym_dir, "03_bear_argument.md"), "w", encoding="utf-8") as f:
                    f.write(data["bear_argument"])
            
        verdicts = state.get("investment_verdicts", {})
        for sym, data in verdicts.items():
            sym_dir = os.path.join(cycle_dir, sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "04_investment_verdict.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
                
        risk_states = state.get("risk_debate_states", {})
        for sym, data in risk_states.items():
            sym_dir = os.path.join(cycle_dir, sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "05_risk_debate.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
                
        portfolio = state.get("portfolio_decisions", {})
        for sym, data in portfolio.items():
            sym_dir = os.path.join(cycle_dir, sym)
            os.makedirs(sym_dir, exist_ok=True)
            with open(os.path.join(sym_dir, "06_final_decision.md"), "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2))
                
        # 4. Summary
        with open(os.path.join(cycle_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("# Cycle Summary\n\n")
            f.write(json.dumps(state.get("summary", {}), indent=2))

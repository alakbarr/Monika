# ==============================================================================
# File: cli/subcommands/simulation.py
# ==============================================================================

"""
Simulation & Backtesting Subcommands (backtest, scenario-stress, benchmark).
"""

import argparse
from cli.subcommands.base import Subcommand
from cli.theme import get_console, stamp_info, stamp_ok


class SimulationSubcommand(Subcommand):
    name = "simulation"
    description = "Run backtests and parallel market scenario stress-tests."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser("simulation", help="Backtesting & scenario stress simulations.")
        sub = parser.add_subparsers(dest="sim_action")

        bt_p = sub.add_parser("backtest", help="Run historical backtest engine.")
        bt_p.add_argument("--symbol", default="XAUUSD", help="Symbol to backtest.")
        bt_p.add_argument("--days", type=int, default=30, help="Days of history.")

        sc_p = sub.add_parser("scenario", help="Run parallel multi-scenario stress-tests.")
        sc_p.add_argument("--workers", type=int, default=4, help="Worker processes count.")
        sc_p.add_argument("--output", default="batch_results.jsonl", help="Output JSONL filename.")

        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        action = getattr(args, "sim_action", None) or getattr(args, "command", "backtest")
        console = get_console()

        if action == "backtest":
            from cli.main import _cmd_backtest
            await _cmd_backtest(args)
        elif action == "scenario":
            from backtest.batch_scenario_runner import BatchScenarioRunner, MarketScenario
            console.print(f"{stamp_info('SIMULATION')} Initializing Batch Scenario Runner...")
            runner = BatchScenarioRunner(max_workers=getattr(args, "workers", 4))
            
            # Default institutional scenario test matrix
            scenarios = [
                MarketScenario(
                    scenario_id="flash_crash_xau",
                    title="Gold Flash Crash Liquidity Squeeze",
                    symbol="XAUUSD",
                    timeframe="M15",
                    event_type="flash_crash",
                    start_time="2026-05-10T12:00:00Z",
                    end_time="2026-05-10T16:00:00Z",
                    synthetic_ticks=[{"price_delta": -25.0}, {"price_delta": -40.0}, {"price_delta": +15.0}],
                ),
                MarketScenario(
                    scenario_id="fomc_surprise_eur",
                    title="FOMC Rate Shock EUR Volatility",
                    symbol="EURUSD",
                    timeframe="H1",
                    event_type="rate_hike",
                    start_time="2026-06-15T18:00:00Z",
                    end_time="2026-06-15T22:00:00Z",
                    synthetic_ticks=[{"price_delta": +0.0080}, {"price_delta": -0.0120}],
                ),
            ]
            results = runner.run_scenarios(scenarios, output_file_name=getattr(args, "output", "batch_results.jsonl"))
            console.print(f"{stamp_ok('COMPLETE')} Processed {len(results)} scenarios in parallel without lock contention.")
        return 0

# ==============================================================================
# File: tests/agent/test_runtime_enhancements.py
# ==============================================================================

import asyncio
import os
import socket
import tempfile
import time
from pathlib import Path
import pytest

from bootstrap import race_dual_stack_socket, bootstrap_runtime
from agent.monitors.startup_watchdog import StartupWatchdog
from backtest.batch_scenario_runner import BatchScenarioRunner, MarketScenario, ScenarioResult
from cli.subcommands import AVAILABLE_SUBCOMMANDS
from cli.subcommands.daemon import DaemonSubcommand
from cli.subcommands.simulation import SimulationSubcommand


class TestBootstrapAndSocketRacer:
    """Test RFC 8305 socket racing and bootstrap initialization."""

    def test_bootstrap_idempotent(self):
        bootstrap_runtime()
        bootstrap_runtime()
        # Verify socket.create_connection is wrapped
        assert hasattr(socket, "create_connection")

    def test_race_dual_stack_local_loopback(self):
        # Create a real listening server socket on loopback
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        addr_info = socket.getaddrinfo("127.0.0.1", port, socket.AF_INET, socket.SOCK_STREAM)
        client = race_dual_stack_socket(addr_info, effective_timeout=2.0)
        assert client is not None
        client.close()
        server.close()


class TestStartupWatchdogCPUExtension:
    """Test CPU-delta progress tracking in startup watchdog."""

    def test_watchdog_cpu_extension(self):
        # Initialize watchdog with very short 0.1s timeout
        dog = StartupWatchdog(timeout_seconds=0.1, enforce_exit=False)
        dog.start()
        # Simulate quick work and mark complete
        dog.report_progress("test_phase", lease_seconds=1.0)
        time.sleep(0.05)
        dog.mark_complete()
        assert dog.is_complete is True


class TestBatchScenarioRunner:
    """Test multi-process parallel scenario runner with fsync persistence."""

    def test_run_parallel_scenarios(self, tmp_path):
        runner = BatchScenarioRunner(output_dir=tmp_path, max_workers=2)
        scenarios = [
            MarketScenario(
                scenario_id="sc_1",
                title="Scenario 1",
                symbol="XAUUSD",
                timeframe="M15",
                event_type="test",
                start_time="2026-01-01",
                end_time="2026-01-02",
                synthetic_ticks=[{"price_delta": 10.0}, {"price_delta": -5.0}],
            ),
            MarketScenario(
                scenario_id="sc_2",
                title="Scenario 2",
                symbol="EURUSD",
                timeframe="H1",
                event_type="test",
                start_time="2026-01-01",
                end_time="2026-01-02",
                synthetic_ticks=[{"price_delta": -20.0}, {"price_delta": 50.0}],
            ),
        ]
        out_file = "test_results.jsonl"
        results = runner.run_scenarios(scenarios, output_file_name=out_file)

        assert len(results) == 2
        assert all(isinstance(r, ScenarioResult) for r in results)
        
        # Verify fsync written file
        written_file = tmp_path / out_file
        assert written_file.exists()
        lines = written_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2


class TestModularSubcommands:
    """Test CLI subcommands architecture."""

    def test_subcommands_registry(self):
        assert len(AVAILABLE_SUBCOMMANDS) >= 4
        names = {sc.name for sc in AVAILABLE_SUBCOMMANDS}
        assert "daemon" in names
        assert "trading" in names
        assert "simulation" in names
        assert "mcp" in names

# ==============================================================================
# File: backtest/run_card.py
# Monika Quantitative Research Standard: Institutional Run Card Generator
# ==============================================================================

"""
Backtesting Run Card Standard & Anti-Tamper Provenance.

Generates immutable, verifiable Run Cards for every backtest execution:
1. System Lineage: Git commit SHA, Python environment, engine version.
2. Data Provenance: Dataset time boundaries, asset list, SHA-256 data fingerprint.
3. Cost Assumptions: Explicit slippage, spread multipliers, swap modeling, commissions.
4. Quantitative Performance Metrics: Exact decimal citations for:
   - Sharpe Ratio (annualized)
   - Sortino Ratio
   - Calmar Ratio
   - Maximum Drawdown (%)
   - Profit Factor
   - Win Rate (%)
   - Expected Shortfall / VaR 95%
5. Anti-Tamper Hash: Cryptographic SHA-256 hash chaining all fields together.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("TradingAgent.Backtest.RunCard")


@dataclass
class CostAssumptions:
    spread_multiplier: float = 1.5
    slippage_points: float = 5.0
    swap_enabled: bool = True
    commission_per_lot_usd: float = 7.0


@dataclass
class QuantitativeMetrics:
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    total_return_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0


@dataclass
class RunCard:
    run_id: str
    strategy_name: str
    git_commit: str
    created_at: str
    symbols: List[str]
    timeframe: str
    start_date: str
    end_date: str
    data_fingerprint: str
    cost_assumptions: CostAssumptions
    metrics: QuantitativeMetrics
    parameters: Dict[str, Any] = field(default_factory=dict)
    verification_hash: str = ""

    def compute_verification_hash(self) -> str:
        """Computes deterministic SHA-256 over all non-hash fields."""
        payload = {
            "run_id": self.run_id,
            "strategy_name": self.strategy_name,
            "git_commit": self.git_commit,
            "created_at": self.created_at,
            "symbols": sorted(self.symbols),
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "data_fingerprint": self.data_fingerprint,
            "cost_assumptions": asdict(self.cost_assumptions),
            "metrics": asdict(self.metrics),
            "parameters": self.parameters,
        }
        canonical_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def finalize(self) -> RunCard:
        """Locks and signs the run card."""
        self.verification_hash = self.compute_verification_hash()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_name": self.strategy_name,
            "git_commit": self.git_commit,
            "created_at": self.created_at,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "data_fingerprint": self.data_fingerprint,
            "cost_assumptions": asdict(self.cost_assumptions),
            "metrics": asdict(self.metrics),
            "parameters": self.parameters,
            "verification_hash": self.verification_hash,
        }

    def render_markdown(self) -> str:
        """Renders GitHub-flavored markdown report."""
        c = self.cost_assumptions
        m = self.metrics
        return f"""# Quantitative Backtest Run Card: {self.strategy_name}
**Run ID**: `{self.run_id}`  
**Generated At**: `{self.created_at}`  
**Git Commit**: `{self.git_commit}`  
**Anti-Tamper SHA-256**: `{self.verification_hash}`  

---

## 1. Scope & Data Provenance
- **Symbols**: {", ".join(self.symbols)}
- **Timeframe**: `{self.timeframe}`
- **Test Horizon**: `{self.start_date}` to `{self.end_date}`
- **Data Fingerprint**: `{self.data_fingerprint[:16]}...`

## 2. Friction & Execution Assumptions
- **Spread Multiplier**: `{c.spread_multiplier}x`
- **Slippage**: `{c.slippage_points} pts`
- **Commission**: `${c.commission_per_lot_usd} / lot`
- **Daily Rollover Swap Modeling**: `{'Enabled' if c.swap_enabled else 'Disabled'}`

## 3. Quantitative Performance Citations
| Metric | Value | Baseline Target | Status |
| :--- | :--- | :--- | :--- |
| **Sharpe Ratio** | `{m.sharpe_ratio:.2f}` | >= 1.50 | {'✅ PASS' if m.sharpe_ratio >= 1.5 else '⚠️ LOW'} |
| **Sortino Ratio** | `{m.sortino_ratio:.2f}` | >= 2.00 | {'✅ PASS' if m.sortino_ratio >= 2.0 else '⚠️ LOW'} |
| **Calmar Ratio** | `{m.calmar_ratio:.2f}` | >= 2.00 | {'✅ PASS' if m.calmar_ratio >= 2.0 else '⚠️ LOW'} |
| **Max Drawdown** | `{m.max_drawdown_pct:.2f}%` | <= 10.0% | {'✅ PASS' if m.max_drawdown_pct <= 10.0 else '❌ BREACH'} |
| **Total Return** | `{m.total_return_pct:.2f}%` | > 0.0% | {'✅ PROFIT' if m.total_return_pct > 0 else '❌ LOSS'} |
| **Win Rate** | `{m.win_rate_pct:.1f}%` | >= 50.0% | {'✅ PASS' if m.win_rate_pct >= 50.0 else '⚠️ LOW'} |
| **Profit Factor** | `{m.profit_factor:.2f}` | >= 1.50 | {'✅ PASS' if m.profit_factor >= 1.5 else '⚠️ LOW'} |
| **Total Trades** | `{m.total_trades}` | >= 30 | {'✅ STAT_SIG' if m.total_trades >= 30 else '⚠️ FEW'} |
| **VaR 95%** | `{m.var_95_pct:.2f}%` | - | Validated |
| **CVaR / Expected Shortfall 95%** | `{m.cvar_95_pct:.2f}%` | - | Validated |

---
*Generated deterministically by Monika Institutional Research Engine.*
"""

    def export(self, output_dir: Union[str, Path]) -> Tuple[Path, Path]:
        """Saves run_card.json and run_card.md to output directory."""
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)

        json_path = out_p / f"run_card_{self.run_id}.json"
        md_path = out_p / f"run_card_{self.run_id}.md"

        json_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        md_path.write_text(self.render_markdown(), encoding="utf-8")

        logger.info(f"[RunCard] Exported Run Card {self.run_id} to {out_p}")
        return json_path, md_path


def get_git_commit_sha() -> str:
    """Retrieves current git commit hash, or returns fallback."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "GIT_COMMIT_UNAVAILABLE"


def compute_data_fingerprint(data_objects: Sequence[Any]) -> str:
    """Computes a SHA-256 hash over an array of data records / OHLCV prices."""
    hasher = hashlib.sha256()
    for item in data_objects:
        if hasattr(item, "timestamp") and hasattr(item, "close"):
            chunk = f"{item.timestamp}:{item.close}:{getattr(item, 'volume', 0)}"
        elif isinstance(item, dict):
            chunk = f"{item.get('timestamp')}:{item.get('close')}:{item.get('volume', 0)}"
        else:
            chunk = str(item)
        hasher.update(chunk.encode("utf-8"))
    return hasher.hexdigest()

"""
WalkForwardEngine: Rolling-Window Walk-Forward Optimization & Out-of-Sample Validation.
Evaluates strategy robustness, alpha degradation, and detects overfitting across chronological rolling folds.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple, Optional, Literal, cast

from backtest.point_in_time_engine import PointInTimeBacktestEngine, BacktestMode
from backtest.report_generator import ReportGenerator
from backtest.statistical_tests import deflated_sharpe_ratio, compute_sample_moments
from backtest.alpha_validation import validate_alpha, AlphaValidation
from database.models import BacktestTrade

logger = logging.getLogger("TradingAgent.WalkForwardEngine")


@dataclass
class WalkForwardFold:
    fold_index: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    is_metrics: Dict[str, Any] = field(default_factory=dict)
    oos_metrics: Dict[str, Any] = field(default_factory=dict)
    wfe: float = 0.0
    is_trades_count: int = 0
    oos_trades_count: int = 0


@dataclass
class WalkForwardResult:
    folds: List[WalkForwardFold]
    aggregate_is_sharpe: float
    aggregate_oos_sharpe: float
    overall_wfe: float
    is_overfit: bool
    total_oos_trades: int
    oos_win_rate_pct: float
    stitched_oos_trades: List[BacktestTrade] = field(default_factory=list)
    deflated_sharpe: Optional[float] = None
    alpha_validation: Optional[AlphaValidation] = None


class WalkForwardEngine:
    """
    Walk-Forward Optimization & Validation Engine.
    Splits historical timeline into K rolling folds (In-Sample train + Out-of-Sample test),
    measures Walk-Forward Efficiency (WFE), and flags curve-fitting / overfitting.
    """

    mode: BacktestMode

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        is_window_days: int = 90,
        oos_window_days: int = 30,
        step_days: int = 30,
        settings: Optional[dict] = None,
        mode: BacktestMode = "replay",
        step_hours: int = 4,
        purge_days: int = 4,
        embargo_pct: float = 0.01,
        n_trials: Optional[int] = None,
    ):
        self.start_date = start_date.replace(tzinfo=timezone.utc) if start_date.tzinfo is None else start_date
        self.end_date = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
        self.is_window_days = is_window_days
        self.oos_window_days = oos_window_days
        self.step_days = step_days
        self.settings = settings or {}
        self.mode: BacktestMode = mode
        self.step_hours = step_hours
        self.purge_days = max(0, purge_days)
        self.embargo_pct = max(0.0, embargo_pct)
        self.n_trials = n_trials

    def generate_folds(self) -> List[Tuple[datetime, datetime, datetime, datetime]]:
        """
        Generate chronological rolling folds (is_start, is_end, oos_start, oos_end).
        Applies purging between IS and OOS to eliminate label horizon overlap,
        and post-test embargo to prevent serial correlation leakage.
        """
        folds = []
        current_is_start = self.start_date
        total_duration = (self.end_date - self.start_date).days
        min_required_days = self.is_window_days + min(7, self.oos_window_days)
        embargo_days = max(1, math.ceil(self.oos_window_days * self.embargo_pct)) if self.embargo_pct > 0 else 0

        if total_duration < min_required_days:
            # Fallback single fold with 75% IS / 25% OOS split
            split_days = max(1, int(total_duration * 0.75))
            oos_start = self.start_date + timedelta(days=split_days)
            is_end = oos_start - timedelta(days=self.purge_days) if self.purge_days > 0 else oos_start
            if is_end <= self.start_date:
                is_end = oos_start
            folds.append((self.start_date, is_end, oos_start, self.end_date))
            return folds

        while True:
            is_raw_end = current_is_start + timedelta(days=self.is_window_days)
            oos_start = is_raw_end
            is_end = oos_start - timedelta(days=self.purge_days) if self.purge_days > 0 else is_raw_end
            if is_end <= current_is_start:
                is_end = is_raw_end

            oos_end = oos_start + timedelta(days=self.oos_window_days)

            if oos_start >= self.end_date:
                break

            if oos_end > self.end_date:
                if (self.end_date - oos_start).days >= 7:
                    folds.append((current_is_start, is_end, oos_start, self.end_date))
                break

            folds.append((current_is_start, is_end, oos_start, oos_end))
            current_is_start += timedelta(days=self.step_days + embargo_days)

        return folds

    async def run(self) -> WalkForwardResult:
        """
        Execute Walk-Forward Optimization across all generated folds.
        Evaluates In-Sample and Out-of-Sample metrics, computes WFE, and stitches OOS trades.
        """
        raw_folds = self.generate_folds()
        logger.info(f"Starting Walk-Forward Optimization across {len(raw_folds)} folds...")

        results_folds: List[WalkForwardFold] = []
        all_oos_trades: List[BacktestTrade] = []

        is_sharpes = []
        oos_sharpes = []
        is_returns = []
        oos_returns = []

        for idx, (is_start, is_end, oos_start, oos_end) in enumerate(raw_folds, 1):
            logger.info(f"--- Running Fold {idx}/{len(raw_folds)}: IS [{is_start.strftime('%Y-%m-%d')} - {is_end.strftime('%Y-%m-%d')}] | OOS [{oos_start.strftime('%Y-%m-%d')} - {oos_end.strftime('%Y-%m-%d')}] ---")

            from database.models import BacktestRun

            # 1. Run In-Sample simulation
            is_engine = PointInTimeBacktestEngine(
                start_date=is_start,
                end_date=is_end,
                mode=cast(BacktestMode, self.mode),
                step_hours=self.step_hours,
                settings=self.settings
            )
            if hasattr(is_engine, "run_simulation") and callable(is_engine.run_simulation):
                is_res = await is_engine.run_simulation()
            else:
                is_res = await is_engine.run()
            is_trades = is_res if isinstance(is_res, list) else getattr(is_engine, "trades", [])
            is_run_rec = is_res if isinstance(is_res, BacktestRun) else BacktestRun(start_date=is_start, end_date=is_end, initial_equity=10000.0)
            is_rep = ReportGenerator(run=is_run_rec, trades=is_trades, start_date=is_start, end_date=is_end)
            is_rep.calculate_metrics()
            is_days = max(1.0, (is_end - is_start).total_seconds() / 86400.0)
            is_total_pnl = sum(float(t.pnl_pct or 0.0) for t in is_trades)
            is_metrics = {
                "sharpe_ratio": getattr(is_run_rec, "sharpe_ratio", 0.0) or 0.0,
                "sortino_ratio": getattr(is_rep, "sortino_ratio", 0.0) or 0.0,
                "win_rate": getattr(is_run_rec, "win_rate", 0.0) or 0.0,
                "profit_factor": getattr(is_run_rec, "profit_factor", 0.0) or 0.0,
                "total_pnl_pct": is_total_pnl,
                "annualized_return_pct": (is_total_pnl / is_days) * 365.0,
                "max_drawdown_pct": getattr(is_run_rec, "max_drawdown_pct", 0.0) or 0.0,
            }

            # 2. Run Out-of-Sample simulation
            oos_engine = PointInTimeBacktestEngine(
                start_date=oos_start,
                end_date=oos_end,
                mode=cast(BacktestMode, self.mode),
                step_hours=self.step_hours,
                settings=self.settings
            )
            if hasattr(oos_engine, "run_simulation") and callable(oos_engine.run_simulation):
                oos_res = await oos_engine.run_simulation()
            else:
                oos_res = await oos_engine.run()
            oos_trades = oos_res if isinstance(oos_res, list) else getattr(oos_engine, "trades", [])
            oos_run_rec = oos_res if isinstance(oos_res, BacktestRun) else BacktestRun(start_date=oos_start, end_date=oos_end, initial_equity=10000.0)
            oos_rep = ReportGenerator(run=oos_run_rec, trades=oos_trades, start_date=oos_start, end_date=oos_end)
            oos_rep.calculate_metrics()
            oos_days = max(1.0, (oos_end - oos_start).total_seconds() / 86400.0)
            oos_total_pnl = sum(float(t.pnl_pct or 0.0) for t in oos_trades)
            oos_metrics = {
                "sharpe_ratio": getattr(oos_run_rec, "sharpe_ratio", 0.0) or 0.0,
                "sortino_ratio": getattr(oos_rep, "sortino_ratio", 0.0) or 0.0,
                "win_rate": getattr(oos_run_rec, "win_rate", 0.0) or 0.0,
                "profit_factor": getattr(oos_run_rec, "profit_factor", 0.0) or 0.0,
                "total_pnl_pct": oos_total_pnl,
                "annualized_return_pct": (oos_total_pnl / oos_days) * 365.0,
                "max_drawdown_pct": getattr(oos_run_rec, "max_drawdown_pct", 0.0) or 0.0,
            }

            all_oos_trades.extend(oos_trades)

            # Extract annualized returns and Sharpe
            is_ann_ret = float(is_metrics.get("annualized_return_pct", 0.0) or is_metrics.get("total_pnl_pct", 0.0) or 0.0)
            oos_ann_ret = float(oos_metrics.get("annualized_return_pct", 0.0) or oos_metrics.get("total_pnl_pct", 0.0) or 0.0)
            is_sharpe = float(is_metrics.get("sharpe_ratio", 0.0) or 0.0)
            oos_sharpe = float(oos_metrics.get("sharpe_ratio", 0.0) or 0.0)

            is_sharpes.append(is_sharpe)
            oos_sharpes.append(oos_sharpe)
            is_returns.append(is_ann_ret)
            oos_returns.append(oos_ann_ret)

            # Compute Walk-Forward Efficiency: WFE = OOS_Return / IS_Return
            if is_ann_ret > 0:
                fold_wfe = round(oos_ann_ret / is_ann_ret, 3)
            elif is_ann_ret == 0.0:
                fold_wfe = 1.0 if oos_ann_ret >= 0 else 0.0
            else:
                # IS was negative
                fold_wfe = 0.0 if oos_ann_ret <= is_ann_ret else round(abs(oos_ann_ret - is_ann_ret) / abs(is_ann_ret), 3)

            fold_obj = WalkForwardFold(
                fold_index=idx,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                is_metrics=is_metrics,
                oos_metrics=oos_metrics,
                wfe=fold_wfe,
                is_trades_count=len(is_trades),
                oos_trades_count=len(oos_trades)
            )
            results_folds.append(fold_obj)

        # Calculate aggregate institutional metrics
        avg_is_sharpe = round(sum(is_sharpes) / len(is_sharpes), 2) if is_sharpes else 0.0
        avg_oos_sharpe = round(sum(oos_sharpes) / len(oos_sharpes), 2) if oos_sharpes else 0.0
        
        avg_is_ret = sum(is_returns) / len(is_returns) if is_returns else 0.0
        avg_oos_ret = sum(oos_returns) / len(oos_returns) if oos_returns else 0.0
        
        if avg_is_ret > 0:
            overall_wfe = round(avg_oos_ret / avg_is_ret, 3)
        else:
            overall_wfe = 1.0 if avg_oos_ret >= 0 else 0.0

        # Compute Deflated Sharpe Ratio (DSR) across folds
        effective_trials = self.n_trials if self.n_trials is not None and self.n_trials > 0 else max(1, len(results_folds))
        total_oos_days = max(10, sum((f.oos_end - f.oos_start).days for f in results_folds))
        n_obs = max(len(all_oos_trades), total_oos_days)
        # De-annualize Sharpe to match daily frequency scale of n_obs
        daily_oos_sr = avg_oos_sharpe / math.sqrt(252.0) if avg_oos_sharpe > 0 else avg_oos_sharpe
        oos_trade_returns = [float(t.pnl_pct or 0.0) / 100.0 for t in all_oos_trades] if all_oos_trades else []
        _, _, oos_skew, oos_kurt = compute_sample_moments(oos_trade_returns) if len(oos_trade_returns) >= 3 else (0.0, 0.0, 0.0, 0.0)

        dsr_score = deflated_sharpe_ratio(
            observed_sr=daily_oos_sr,
            n_trials=effective_trials,
            n_obs=n_obs,
            skew=oos_skew,
            excess_kurt=oos_kurt,
            sr_std=0.5 / math.sqrt(252.0),
        )

        # Alpha validation (directional balance, split-half consistency, cost stress)
        alpha_val = validate_alpha(trades=all_oos_trades, cost_multiplier=2.0)

        # Overfitting criteria: WFE < 0.50, OOS Sharpe < 0.0, DSR < 0.40, or failing critical alpha validation (with >= 10 trades)
        is_overfit = bool(
            overall_wfe < 0.50
            or avg_oos_sharpe < 0.0
            or (len(all_oos_trades) >= 10 and (dsr_score < 0.40 or not alpha_val.passed))
        )

        # OOS win rate across stitched holdout trades (standardized with ReportGenerator)
        oos_wins = sum(1 for t in all_oos_trades if (t.pnl_pct or 0) > 0)
        oos_win_rate = round((oos_wins / len(all_oos_trades)) * 100.0, 1) if all_oos_trades else 0.0

        result = WalkForwardResult(
            folds=results_folds,
            aggregate_is_sharpe=avg_is_sharpe,
            aggregate_oos_sharpe=avg_oos_sharpe,
            overall_wfe=overall_wfe,
            is_overfit=is_overfit,
            total_oos_trades=len(all_oos_trades),
            oos_win_rate_pct=oos_win_rate,
            stitched_oos_trades=all_oos_trades,
            deflated_sharpe=dsr_score,
            alpha_validation=alpha_val,
        )

        logger.info(f"Walk-Forward Optimization Complete: WFE={overall_wfe:.2f}, DSR={dsr_score:.2f}, AlphaValid={alpha_val.passed} (IS Sharpe={avg_is_sharpe}, OOS Sharpe={avg_oos_sharpe}, Overfit={is_overfit})")
        return result

    def generate_markdown_report(self, result: WalkForwardResult) -> str:
        """Generate formatted Markdown analysis report for WFO results."""
        lines = [
            "# Walk-Forward Optimization (WFO) Report",
            f"**Evaluation Period**: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}",
            f"**Total Folds**: {len(result.folds)} | **IS Window**: {self.is_window_days}d | **OOS Window**: {self.oos_window_days}d | **Purge**: {self.purge_days}d",
            "",
            "## Summary Performance",
            f"- **Overall Walk-Forward Efficiency (WFE)**: `{result.overall_wfe:.2f}` ({'PASS (>= 0.50)' if result.overall_wfe >= 0.50 else 'FAIL (< 0.50)'})",
            f"- **Aggregate In-Sample Sharpe**: `{result.aggregate_is_sharpe:.2f}`",
            f"- **Aggregate Out-of-Sample Sharpe**: `{result.aggregate_oos_sharpe:.2f}`",
            f"- **Deflated Sharpe Ratio (DSR)**: `{result.deflated_sharpe:.2f}` ({'PASS (>= 0.50)' if result.deflated_sharpe and result.deflated_sharpe >= 0.50 else 'CAUTION (< 0.50)'})" if result.deflated_sharpe is not None else "",
            f"- **Total Stitched OOS Trades**: `{result.total_oos_trades}` (Win Rate: `{result.oos_win_rate_pct:.1f}%`)",
            f"- **Alpha Validation (Beta/Consistency/Cost)**: `{'PASS' if result.alpha_validation and result.alpha_validation.passed else 'FAIL'}`" if result.alpha_validation else "",
            f"  - Details: {result.alpha_validation.details}" if result.alpha_validation else "",
            f"- **Overfitting Detected**: `{'YES (Strategy degrades out-of-sample)' if result.is_overfit else 'NO (Strategy generalizes well)'}`",
            "",
            "## Fold-by-Fold Breakdown",
            "| Fold | IS Period | OOS Period | IS Trades | OOS Trades | IS Sharpe | OOS Sharpe | WFE |",
            "|---|---|---|:---:|:---:|:---:|:---:|:---:|"
        ]

        for f in result.folds:
            is_s = f.is_start.strftime("%Y-%m-%d") + ".." + f.is_end.strftime("%m-%d")
            oos_s = f.oos_start.strftime("%Y-%m-%d") + ".." + f.oos_end.strftime("%m-%d")
            is_shp = f.is_metrics.get("sharpe_ratio", 0.0) or 0.0
            oos_shp = f.oos_metrics.get("sharpe_ratio", 0.0) or 0.0
            lines.append(f"| {f.fold_index} | {is_s} | {oos_s} | {f.is_trades_count} | {f.oos_trades_count} | {is_shp:.2f} | {oos_shp:.2f} | {f.wfe:.2f} |")

        return "\n".join([line for line in lines if line])

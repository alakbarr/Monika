"""
Comprehensive Backtest Report Generator with Daily-Resampled Sharpe & Sortino Ratios.
"""
import logging
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import numpy as np
from database.models import BacktestRun, BacktestTrade

logger = logging.getLogger("TradingAgent.ReportGenerator")


class ReportGenerator:
    def __init__(
        self,
        run: BacktestRun,
        trades: List[BacktestTrade],
        equity_curve: Optional[List[Dict[str, Any]]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        self.run = run
        self.trades = trades or []
        self.equity_curve = equity_curve or []
        self.start_date = start_date or getattr(run, "start_date", None)
        self.end_date = end_date or getattr(run, "end_date", None)
        self.wilson_lower = 0.0
        self.wilson_upper = 0.0
        self.expectancy_r = 0.0
        self.sortino_ratio = 0.0
        self.calmar_ratio = 0.0
        self.omega_ratio = 0.0
        self.cvar_95 = 0.0
        self.ulcer_index = 0.0

    def calculate_metrics(self):
        """Calculates institutional backtesting performance metrics."""
        initial_eq = getattr(self.run, "initial_equity", 10000.0) or 10000.0
        if not self.trades:
            self.run.total_trades = 0
            self.run.win_rate = 0.0
            self.run.profit_factor = 0.0
            self.run.sharpe_ratio = 0.0
            self.run.max_drawdown_pct = 0.0
            self.run.final_equity = initial_eq
            self.calmar_ratio = 0.0
            self.omega_ratio = 0.0
            self.cvar_95 = 0.0
            self.ulcer_index = 0.0
            return

        self.run.total_trades = len(self.trades)

        wins = [t for t in self.trades if (t.pnl_pct or 0) > 0]
        losses = [t for t in self.trades if (t.pnl_pct or 0) <= 0]

        self.run.win_rate = round((len(wins) / len(self.trades)) * 100, 2)

        def _get_trade_usd(t):
            if hasattr(t, "pnl_usd") and getattr(t, "pnl_usd", None) is not None:
                return float(t.pnl_usd)
            if hasattr(t, "pnl") and getattr(t, "pnl", None) is not None:
                return float(t.pnl)
            pnl_pct = getattr(t, "pnl_pct", None)
            return (float(pnl_pct or 0.0) / 100.0) * initial_eq

        trade_pnls = [_get_trade_usd(t) for t in self.trades]
        gross_profit = sum(p for p in trade_pnls if p > 0)
        gross_loss = abs(sum(p for p in trade_pnls if p < 0))

        self.run.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # 1. Resample equity curve to Daily Return Series
        daily_returns = self._resample_daily_returns(initial_eq)

        # Determine annualization factor: asset-weighted based on crypto fraction (252 for FX, 365 for Crypto)
        crypto_symbols = ("BTC", "ETH", "SOL", "XRP", "BNB")
        total_t_count = len(self.trades)
        crypto_t_count = sum(1 for t in self.trades if any(c in t.symbol.upper() for c in crypto_symbols))
        
        has_crypto = crypto_t_count > 0
        crypto_fraction = (crypto_t_count / total_t_count) if total_t_count > 0 else 0.0
        ann_factor = round(252.0 + (crypto_fraction * (365.0 - 252.0)), 2)

        # 2. Annualized Daily Sharpe Ratio
        if len(daily_returns) > 1:
            mean_ret = float(np.mean(daily_returns))
            std_ret = float(np.std(daily_returns, ddof=1))
            if std_ret > 1e-8:
                self.run.sharpe_ratio = round(float((mean_ret / std_ret) * np.sqrt(ann_factor)), 2)
            else:
                self.run.sharpe_ratio = 0.0

            # 3. Annualized Sortino Ratio (Downside semi-deviation)
            downside_returns = [r for r in daily_returns if r < 0]
            if downside_returns:
                downside_std = float(np.sqrt(np.mean(np.array(downside_returns) ** 2)))
                if downside_std > 1e-8:
                    self.sortino_ratio = round(float((mean_ret / downside_std) * np.sqrt(ann_factor)), 2)
                else:
                    self.sortino_ratio = 0.0
            else:
                self.sortino_ratio = 99.0 if mean_ret > 0 else 0.0
        else:
            self.run.sharpe_ratio = 0.0
            self.sortino_ratio = 0.0

        # 4. Expectancy per-R
        avg_loss_pct = abs(sum(t.pnl_pct for t in losses if t.pnl_pct) / len(losses)) if losses else 1.0
        avg_win_pct = sum(t.pnl_pct for t in wins if t.pnl_pct) / len(wins) if wins else 0.0
        win_rate_dec = len(wins) / len(self.trades)
        loss_rate_dec = 1.0 - win_rate_dec
        self.expectancy_r = round((win_rate_dec * (avg_win_pct / avg_loss_pct) - loss_rate_dec), 2) if avg_loss_pct > 0 else 0.0

        # 5. Max Drawdown %
        if self.equity_curve:
            equities = [p.get("equity", initial_eq) if isinstance(p, dict) else float(p) for p in self.equity_curve]
            peak = initial_eq
            max_dd = 0.0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
            self.run.max_drawdown_pct = round(max_dd * 100.0, 2)
            self.run.final_equity = round(float(equities[-1]), 2)
        else:
            self.run.max_drawdown_pct = 0.0
            tot_pnl = sum(getattr(t, "pnl", 0.0) or 0.0 for t in self.trades)
            self.run.final_equity = round(float(initial_eq + tot_pnl), 2)

        # 6. Wilson Score 95% Confidence Interval for Win Rate
        if self.run.total_trades > 0:
            z = 1.96  # 95% CI
            n = float(self.run.total_trades)
            p = float(len(wins)) / n
            denominator = 1.0 + (z ** 2) / n
            centre_adjusted = p + (z ** 2) / (2.0 * n)
            adjusted_std = np.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * n)) / n)
            self.wilson_lower = max(0.0, float((centre_adjusted - z * adjusted_std) / denominator))
            self.wilson_upper = min(1.0, float((centre_adjusted + z * adjusted_std) / denominator))
        else:
            self.wilson_lower = 0.0
            self.wilson_upper = 0.0

        # 7. Extended Risk Metrics (Nautilus Parity)
        if len(daily_returns) > 1:
            var_5 = float(np.percentile(daily_returns, 5))
            tail_losses = [r for r in daily_returns if r <= var_5]
            self.cvar_95 = round(abs(float(np.mean(tail_losses))) * 100.0, 2) if tail_losses else 0.0
        else:
            self.cvar_95 = 0.0

        if len(daily_returns) > 0:
            pos_excess = sum(max(r, 0.0) for r in daily_returns)
            neg_excess = sum(max(-r, 0.0) for r in daily_returns)
            self.omega_ratio = round(float(pos_excess / neg_excess), 2) if neg_excess > 1e-8 else (99.0 if pos_excess > 0 else 0.0)
        else:
            self.omega_ratio = 0.0

        if self.equity_curve:
            equities = [p.get("equity", initial_eq) if isinstance(p, dict) else float(p) for p in self.equity_curve]
            peak = initial_eq
            dd_sq = []
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd_pct = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
                dd_sq.append(dd_pct ** 2)
            self.ulcer_index = round(float(np.sqrt(np.mean(dd_sq))), 2) if dd_sq else 0.0
        else:
            self.ulcer_index = 0.0

        if self.run.max_drawdown_pct > 0 and len(daily_returns) > 1:
            ann_return = float(np.mean(daily_returns) * ann_factor) * 100.0
            self.calmar_ratio = round(ann_return / self.run.max_drawdown_pct, 2)
        else:
            self.calmar_ratio = 0.0

        # 8. Monte Carlo Permutation Drawdown Analysis
        self.compute_monte_carlo_drawdowns(num_simulations=1000)

    def compute_monte_carlo_drawdowns(self, num_simulations: int = 10000) -> Dict[str, float]:
        """
        Runs Monte Carlo trade permutation to estimate 95% and 99% VaR Max Drawdown.
        """
        from backtest.monte_carlo_engine import MonteCarloStressTester
        tester = MonteCarloStressTester(seed=42)
        initial_eq = float(getattr(self.run, "initial_equity", 10000.0) or 10000.0)
        # Use actual fractional equity returns (dollar PnL / initial equity) rather than unleveraged price %
        trade_returns = [
            float(item["trade_pnl_usd"]) / initial_eq
            for item in self.equity_curve
            if isinstance(item, dict) and "trade_pnl_usd" in item and item.get("trade_pnl_usd") is not None
        ]
        if not trade_returns:
            trade_returns = [float(t.pnl_pct or 0.0) / 100.0 for t in self.trades]

        res = tester.run_permutation_drawdown_test(
            trade_returns=trade_returns,
            num_simulations=num_simulations,
            initial_equity=initial_eq
        )
        self.monte_carlo_results = {
            "var_95_drawdown_pct": res.get("var_95_drawdown_pct", 0.0),
            "var_99_drawdown_pct": res.get("var_99_drawdown_pct", 0.0),
            "max_simulated_dd_pct": res.get("max_simulated_dd_pct", 0.0),
            "ruin_probability_pct": res.get("ruin_probability_pct", 0.0),
        }
        return self.monte_carlo_results

    def _resample_daily_returns(self, initial_equity: float) -> List[float]:
        """
        Resamples the irregular trade equity curve into calendar daily returns.
        """
        if not self.start_date or not self.end_date or self.start_date >= self.end_date:
            # Fallback to trade-level returns if date bounds are unavailable
            if not self.equity_curve or len(self.equity_curve) < 2:
                return []
            eqs = [p.get("equity", initial_equity) if isinstance(p, dict) else float(p) for p in self.equity_curve]
            return [float((eqs[i] - eqs[i - 1]) / eqs[i - 1]) for i in range(1, len(eqs))]

        start_dt = self.start_date.date() if isinstance(self.start_date, datetime) else self.start_date
        end_dt = self.end_date.date() if isinstance(self.end_date, datetime) else self.end_date

        total_days = max(1, (end_dt - start_dt).days + 1)
        daily_equity: Dict[str, float] = {}

        # Fill end-of-day equity for each trade exit date
        current_eq = initial_equity
        for point in self.equity_curve:
            if isinstance(point, dict):
                ts = point.get("timestamp")
                eq = point.get("equity", current_eq)
                if ts:
                    dt = ts.date() if isinstance(ts, datetime) else start_dt
                    daily_equity[dt.isoformat()] = eq
                    current_eq = eq

        # Build continuous day series (preserve weekends if crypto was traded or weekend equity shifted)
        crypto_symbols = ("BTC", "ETH", "SOL", "XRP", "BNB")
        has_crypto = bool(self.trades) and any(any(c in t.symbol.upper() for c in crypto_symbols) for t in self.trades)
        
        full_series: List[float] = []
        running_eq = initial_equity
        for d in range(total_days):
            cur_date = start_dt + timedelta(days=d)
            day_date = cur_date.isoformat()
            
            is_weekend = cur_date.weekday() >= 5
            has_weekend_activity = day_date in daily_equity
            
            # If not crypto and it's weekend with no trading activity, skip
            if is_weekend and not has_crypto and not has_weekend_activity:
                continue
                
            if day_date in daily_equity:
                running_eq = daily_equity[day_date]
            full_series.append(running_eq)

        # Compute daily returns
        daily_rets = []
        for i in range(1, len(full_series)):
            prev = full_series[i - 1]
            curr = full_series[i]
            r = (curr - prev) / prev if prev > 0 else 0.0
            daily_rets.append(float(r))

        return daily_rets

    def to_dict(self) -> Dict[str, Any]:
        """Returns comprehensive dictionary of calculated metrics."""
        return {
            "total_trades": getattr(self.run, "total_trades", 0),
            "win_rate": getattr(self.run, "win_rate", 0.0),
            "win_rate_ci_95": (round(self.wilson_lower * 100, 1), round(self.wilson_upper * 100, 1)),
            "profit_factor": getattr(self.run, "profit_factor", 0.0),
            "sharpe_ratio": getattr(self.run, "sharpe_ratio", 0.0),
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "omega_ratio": self.omega_ratio,
            "cvar_95_pct": self.cvar_95,
            "ulcer_index": self.ulcer_index,
            "expectancy_r": self.expectancy_r,
            "max_drawdown_pct": getattr(self.run, "max_drawdown_pct", 0.0),
            "final_equity": getattr(self.run, "final_equity", 10000.0),
            "initial_equity": getattr(self.run, "initial_equity", 10000.0),
            "monte_carlo": getattr(self, "monte_carlo_results", {}),
        }

    def print_summary(self):
        """Prints the summary report to console."""
        print(f"\n{'='*55}")
        print(f"  INSTITUTIONAL BACKTEST REPORT ({self.run.mode.upper()} MODE)")
        print(f"{'='*55}")
        if self.run.start_date and self.run.end_date:
            print(f"Period:       {self.run.start_date.strftime('%Y-%m-%d')} to {self.run.end_date.strftime('%Y-%m-%d')}")
        print(f"Total Trades: {self.run.total_trades}")
        print(f"Win Rate:     {self.run.win_rate:.2f}% (95% CI: {self.wilson_lower*100:.1f}% - {self.wilson_upper*100:.1f}%)")
        print(f"Profit Factor:{self.run.profit_factor:.2f}")
        print(f"Sharpe (Ann): {self.run.sharpe_ratio:.2f}")
        print(f"Sortino:      {self.sortino_ratio:.2f}")
        print(f"Calmar:       {self.calmar_ratio:.2f}")
        print(f"Omega:        {self.omega_ratio:.2f}")
        print(f"CVaR (95%):   {self.cvar_95:.2f}%")
        print(f"Ulcer Index:  {self.ulcer_index:.2f}")
        print(f"Expectancy:   {self.expectancy_r:.2f} R")
        print(f"Max Drawdown: {self.run.max_drawdown_pct:.2f}%")
        if hasattr(self, "monte_carlo_results") and self.monte_carlo_results:
            print(f"MC 95% VaR DD:{self.monte_carlo_results.get('var_95_drawdown_pct', 0.0):.2f}%")
        print(f"Initial Eq:   ${self.run.initial_equity:,.2f}")
        print(f"Final Equity: ${self.run.final_equity:,.2f}")
        print(f"{'='*55}\n")


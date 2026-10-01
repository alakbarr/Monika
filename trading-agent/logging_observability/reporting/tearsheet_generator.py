"""
Executive Quant Tearsheet Engine (PyFolio / QuantStats Institutional Grade).

Computes comprehensive quantitative performance and risk metrics from historical and paper trades:
1. Equity Curve & Compounded Growth
2. Underwater Drawdown Series & Duration
3. Resampled Daily Return Distribution (Mean, Volatility, Skewness, Kurtosis)
4. Trade Expectancy & Payoff Profile (Expectancy per-R, Profit Factor, Wilson Score)
5. Risk-Adjusted Ratios (Annualized Sharpe, Sortino, Calmar, Gain-to-Pain)
6. Multi-Format Rendering (Interactive Markdown & Telegram HTML)
"""

import math
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union, Sequence
import numpy as np

logger = logging.getLogger("TradingAgent.QuantTearsheetGenerator")


@dataclass
class TearsheetResult:
    """Dataclass encapsulating comprehensive quant tearsheet analytics."""
    initial_equity: float
    final_equity: float
    total_net_pnl: float
    total_return_pct: float
    annualized_return_pct: float
    annualized_sharpe: float
    annualized_sortino: float
    calmar_ratio: float
    gain_to_pain_ratio: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    max_drawdown_duration_days: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    payoff_ratio: float
    expectancy_r: float
    expectancy_usd: float
    daily_mean_pct: float
    daily_std_pct: float
    skewness: float
    kurtosis: float
    best_trade_pct: float
    worst_trade_pct: float
    best_day_pct: float
    worst_day_pct: float
    cagr_pct: float = 0.0
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    by_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        """Generates an executive quant tearsheet in clean, publication-grade Markdown."""
        md = [
            f"# Executive Quant Tearsheet",
            f"*Generated at: {self.generated_at} UTC*",
            "",
            "## 1. Executive Performance Summary",
            "| Metric | Value | Metric | Value |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Initial Equity** | ${self.initial_equity:,.2f} | **Annualized Sharpe** | `{self.annualized_sharpe:.2f}` |",
            f"| **Final Equity** | ${self.final_equity:,.2f} | **Annualized Sortino** | `{self.annualized_sortino:.2f}` |",
            f"| **Total Net PnL** | ${self.total_net_pnl:+,.2f} | **Calmar Ratio** | `{self.calmar_ratio:.2f}` |",
            f"| **Total Return** | `{self.total_return_pct:+.2f}%` | **Gain-to-Pain Ratio** | `{self.gain_to_pain_ratio:.2f}` |",
            f"| **Annualized Return** | `{self.annualized_return_pct:+.2f}%` | **CAGR** | `{self.cagr_pct:+.2f}%` |",
            f"| **Max Drawdown** | `{self.max_drawdown_pct:.2f}%` | **Trades Evaluated** | {self.total_trades} |",
            "",
            "## 2. Trade Expectancy & Payoff Profile",
            "| Trade Metric | Value | Trade Metric | Value |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Total Closed Trades** | {self.total_trades} | **Win Rate** | `{self.win_rate_pct:.2f}%` ({self.winning_trades}W / {self.losing_trades}L) |",
            f"| **Profit Factor** | `{self.profit_factor:.2f}` | **Trade Expectancy (R)** | `{self.expectancy_r:+.2f} R` |",
            f"| **Payoff Ratio (Win/Loss)** | `{self.payoff_ratio:.2f}` | **Expectancy ($)** | `${self.expectancy_usd:+,.2f}` |",
            f"| **Best Trade** | `{self.best_trade_pct:+.2f}%` | **Worst Trade** | `{self.worst_trade_pct:+.2f}%` |",
            "",
            "## 3. Risk & Underwater Drawdown Analysis",
            "| Risk Metric | Value | Risk Metric | Value |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Max Peak-to-Valley DD** | `{self.max_drawdown_pct:.2f}%` | **Current Drawdown** | `{self.current_drawdown_pct:.2f}%` |",
            f"| **Max DD Duration** | {self.max_drawdown_duration_days:.1f} days | **Daily Volatility (Std)** | `{self.daily_std_pct:.2f}%` |",
            f"| **Value-at-Risk (VaR 95%)** | `{self.var_95_pct:.2f}%` | **Tail Risk (CVaR 95%)** | `{self.cvar_95_pct:.2f}%` |",
            f"| **Return Skewness** | `{self.skewness:.2f}` | **Return Kurtosis** | `{self.kurtosis:.2f}` |",
            f"| **Best Day** | `{self.best_day_pct:+.2f}%` | **Worst Day** | `{self.worst_day_pct:+.2f}%` |",
            "",
        ]

        if self.by_symbol:
            md.extend([
                "## 4. Asset Performance Breakdown",
                "| Asset | Trades | Win Rate | Net PnL ($) | Avg Trade ($) |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ])
            for sym, data in sorted(self.by_symbol.items(), key=lambda x: x[1].get("net_pnl", 0), reverse=True):
                t_count = data.get("trades", 0)
                wr = data.get("win_rate_pct", 0.0)
                pnl = data.get("net_pnl", 0.0)
                avg_p = pnl / t_count if t_count > 0 else 0.0
                md.append(f"| **{sym}** | {t_count} | {wr:.1f}% | ${pnl:+,.2f} | ${avg_p:+,.2f} |")

        return "\n".join(md)

    def to_telegram_html(self) -> str:
        """Generates compact, high-impact Telegram HTML brief."""
        badge = "[AKTIF] PROFITABLE" if self.total_net_pnl >= 0 else "[KRITIS] DRAWDOWN"
        lines = [
            f"[LAPORAN] <b>Executive Quant Tearsheet ({badge})</b>\n",
            f"<b>Equity:</b> <code>${self.final_equity:,.2f}</code> ({self.total_return_pct:+.2f}% | CAGR: <code>{self.cagr_pct:+.2f}%</code>)",
            f"<b>Net PnL:</b> <code>${self.total_net_pnl:+,.2f}</code>",
            f"<b>Sharpe:</b> <code>{self.annualized_sharpe:.2f}</code> | <b>Sortino:</b> <code>{self.annualized_sortino:.2f}</code>",
            f"<b>Max Drawdown:</b> <code>{self.max_drawdown_pct:.2f}%</code> (Current: {self.current_drawdown_pct:.2f}%)",
            f"<b>VaR (95%):</b> <code>{self.var_95_pct:.2f}%</code> | <b>CVaR (95%):</b> <code>{self.cvar_95_pct:.2f}%</code>",
            f"<b>Trades:</b> {self.total_trades} | <b>Win Rate:</b> <code>{self.win_rate_pct:.1f}%</code>",
            f"<b>Profit Factor:</b> <code>{self.profit_factor:.2f}</code> | <b>Expectancy:</b> <code>{self.expectancy_r:+.2f}R</code>",
            f"<b>Payoff Ratio:</b> <code>{self.payoff_ratio:.2f}</code> | <b>Calmar:</b> <code>{self.calmar_ratio:.2f}</code>",
        ]
        if self.by_symbol:
            lines.append("\n<b>Asset Summary:</b>")
            for sym, data in list(sorted(self.by_symbol.items(), key=lambda x: x[1].get("net_pnl", 0), reverse=True))[:4]:
                lines.append(f"• <b>{sym}</b>: {data.get('trades')} trades, WR: {data.get('win_rate_pct', 0):.0f}%, PnL: <code>${data.get('net_pnl', 0):+,.2f}</code>")
        return "\n".join(lines)

    def to_standalone_html(self, title: str = "Monika Institutional Quant Tearsheet") -> str:
        """Generates a standalone, print/PDF-optimized institutional HTML tearsheet."""
        badge_color = "#10b981" if self.total_net_pnl >= 0 else "#ef4444"
        badge_text = "PROFITABLE" if self.total_net_pnl >= 0 else "DRAWDOWN"

        # SVG Equity curve generator if points available
        svg_chart = ""
        if len(self.equity_curve) >= 2:
            pts = []
            eqs = [p.get("equity", self.initial_equity) for p in self.equity_curve]
            min_e, max_e = min(eqs), max(eqs)
            diff = max_e - min_e if max_e > min_e else 1.0
            w, h = 760, 220
            pad_x, pad_y = 40, 20
            for idx, e in enumerate(eqs):
                x = pad_x + (idx / (len(eqs) - 1)) * (w - 2 * pad_x)
                y = h - pad_y - ((e - min_e) / diff) * (h - 2 * pad_y)
                pts.append(f"{x:.1f},{y:.1f}")
            poly_pts = " ".join(pts)
            svg_chart = f"""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
              <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase; margin: 0 0 12px 0;">Compounded Equity Curve</h3>
              <svg viewBox="0 0 {w} {h}" style="width: 100%; height: auto; overflow: visible;">
                <polyline fill="none" stroke="{badge_color}" stroke-width="2.5" stroke-linecap="round" points="{poly_pts}"/>
              </svg>
            </div>
            """

        rows_asset = ""
        if self.by_symbol:
            for sym, data in sorted(self.by_symbol.items(), key=lambda x: x[1].get("net_pnl", 0), reverse=True):
                cnt = data.get("trades", 0)
                wr = data.get("win_rate_pct", 0.0)
                pnl = data.get("net_pnl", 0.0)
                p_col = "#10b981" if pnl >= 0 else "#ef4444"
                rows_asset += f"<tr><td><b>{sym}</b></td><td>{cnt}</td><td>{wr:.1f}%</td><td style='color:{p_col}; font-weight:600;'>${pnl:+,.2f}</td></tr>"

        asset_table = f"""
        <div class="card">
          <h2>Asset Performance Breakdown</h2>
          <table>
            <thead><tr><th>Asset</th><th>Trades</th><th>Win Rate</th><th>Net P&amp;L</th></tr></thead>
            <tbody>{rows_asset}</tbody>
          </table>
        </div>
        """ if rows_asset else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #334155; padding-bottom: 12px; margin-bottom: 20px; }}
  .badge {{ background: {badge_color}; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 12px; letter-spacing: 0.05em; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
  .stat-card {{ background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid {badge_color}; }}
  .stat-label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }}
  .stat-val {{ font-size: 20px; font-weight: 700; }}
  .card {{ background: #1e293b; padding: 18px; border-radius: 8px; margin-bottom: 20px; page-break-inside: avoid; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: #cbd5e1; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #334155; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; text-align: left; }}
  th {{ color: #94a3b8; font-weight: 600; border-bottom: 1px solid #334155; }}
  tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
  @media print {{
    body {{ background: #ffffff !important; color: #000000 !important; padding: 0; }}
    .stat-card, .card {{ background: #f8fafc !important; border: 1px solid #e2e8f0 !important; color: #000000 !important; }}
    th, td {{ color: #000000 !important; border-color: #cbd5e1 !important; }}
    .stat-label {{ color: #64748b !important; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1 style="margin: 0; font-size: 22px;">{title}</h1>
      <span style="font-size: 12px; color: #94a3b8;">Generated: {self.generated_at} UTC</span>
    </div>
    <span class="badge">{badge_text}</span>
  </div>

  <div class="grid">
    <div class="stat-card">
      <div class="stat-label">Final Equity</div>
      <div class="stat-val">${self.final_equity:,.2f}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Return</div>
      <div class="stat-val" style="color:{badge_color};">{self.total_return_pct:+.2f}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Sharpe Ratio</div>
      <div class="stat-val">{self.annualized_sharpe:.2f}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Max Drawdown</div>
      <div class="stat-val" style="color:#ef4444;">{self.max_drawdown_pct:.2f}%</div>
    </div>
  </div>

  {svg_chart}

  <div class="card">
    <h2>1. Executive Return &amp; Risk Metrics</h2>
    <table>
      <tbody>
        <tr><td><b>Initial Equity</b></td><td>${self.initial_equity:,.2f}</td><td><b>Annualized Return</b></td><td>{self.annualized_return_pct:+.2f}%</td></tr>
        <tr><td><b>Total Net P&amp;L</b></td><td>${self.total_net_pnl:+,.2f}</td><td><b>CAGR</b></td><td>{self.cagr_pct:+.2f}%</td></tr>
        <tr><td><b>Sortino Ratio</b></td><td>{self.annualized_sortino:.2f}</td><td><b>Calmar Ratio</b></td><td>{self.calmar_ratio:.2f}</td></tr>
        <tr><td><b>Gain-to-Pain</b></td><td>{self.gain_to_pain_ratio:.2f}</td><td><b>VaR (95%)</b></td><td>{self.var_95_pct:.2f}%</td></tr>
        <tr><td><b>Tail Risk (CVaR 95%)</b></td><td>{self.cvar_95_pct:.2f}%</td><td><b>Daily Volatility (Std)</b></td><td>{self.daily_std_pct:.2f}%</td></tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>2. Trade Expectancy &amp; Payoff Profile</h2>
    <table>
      <tbody>
        <tr><td><b>Total Trades</b></td><td>{self.total_trades}</td><td><b>Win Rate</b></td><td>{self.win_rate_pct:.2f}% ({self.winning_trades}W / {self.losing_trades}L)</td></tr>
        <tr><td><b>Profit Factor</b></td><td>{self.profit_factor:.2f}</td><td><b>Expectancy (R)</b></td><td>{self.expectancy_r:+.2f} R</td></tr>
        <tr><td><b>Payoff Ratio</b></td><td>{self.payoff_ratio:.2f}</td><td><b>Expectancy ($)</b></td><td>${self.expectancy_usd:+,.2f}</td></tr>
        <tr><td><b>Best Trade</b></td><td>{self.best_trade_pct:+.2f}%</td><td><b>Worst Trade</b></td><td>{self.worst_trade_pct:+.2f}%</td></tr>
      </tbody>
    </table>
  </div>

  {asset_table}
</div>
</body>
</html>"""

    def export_report(self, filepath: Optional[str] = None) -> str:
        """Saves standalone HTML report to disk for viewing or browser print-to-PDF."""
        import os
        if not filepath:
            os.makedirs("reports", exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join("reports", f"tearsheet_{ts}.html")
        html_content = self.to_standalone_html()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        return filepath


class QuantTearsheetGenerator:
    """
    Quantitative performance reporting engine calculating institutional tearsheets.
    """

    @classmethod
    def generate_from_trades(
        cls,
        trades: Sequence[Any],
        initial_equity: float = 10000.0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> TearsheetResult:
        """
        Generates comprehensive TearsheetResult from a collection of trades.
        Compatible with PaperTradeRecord, BacktestTrade, or dictionary trade records.
        """
        if not trades:
            return TearsheetResult(
                initial_equity=initial_equity,
                final_equity=initial_equity,
                total_net_pnl=0.0,
                total_return_pct=0.0,
                annualized_return_pct=0.0,
                annualized_sharpe=0.0,
                annualized_sortino=0.0,
                calmar_ratio=0.0,
                gain_to_pain_ratio=0.0,
                max_drawdown_pct=0.0,
                current_drawdown_pct=0.0,
                max_drawdown_duration_days=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                payoff_ratio=0.0,
                expectancy_r=0.0,
                expectancy_usd=0.0,
                daily_mean_pct=0.0,
                daily_std_pct=0.0,
                skewness=0.0,
                kurtosis=0.0,
                best_trade_pct=0.0,
                worst_trade_pct=0.0,
                best_day_pct=0.0,
                worst_day_pct=0.0,
            )

        # Standardize trade records
        parsed_trades: List[Dict[str, Any]] = []
        for t in trades:
            if isinstance(t, dict):
                pnl_val = t.get("pnl_usd")
                if pnl_val is None:
                    pnl_val = t.get("pnl", 0.0)
                pnl = float(pnl_val or 0.0)
                pnl_pct = float(t.get("pnl_pct", 0.0) or 0.0)
                sym = str(t.get("symbol", "UNKNOWN")).upper()
                closed_at = t.get("closed_at") or t.get("exit_time") or t.get("created_at")
            else:
                pnl_val = getattr(t, "pnl_usd", None)
                if pnl_val is None:
                    pnl_val = getattr(t, "pnl", 0.0)
                pnl = float(pnl_val or 0.0)
                pnl_pct = float(getattr(t, "pnl_pct", 0.0) or 0.0)
                sym = str(getattr(t, "symbol", "UNKNOWN")).upper()
                closed_at = getattr(t, "closed_at", None) or getattr(t, "exit_time", None) or getattr(t, "created_at", None)

            # Parse datetime if string
            dt_closed = None
            if isinstance(closed_at, datetime):
                dt_closed = closed_at
            elif isinstance(closed_at, str):
                try:
                    dt_closed = datetime.fromisoformat(closed_at)
                except Exception:
                    pass

            pct = pnl_pct if pnl_pct != 0.0 else (round((pnl / initial_equity) * 100.0, 4) if initial_equity > 0 else 0.0)
            parsed_trades.append({
                "pnl": pnl,
                "pnl_pct": pct,
                "symbol": sym,
                "closed_at": dt_closed,
            })

        # Sort chronologically
        parsed_trades.sort(key=lambda x: x["closed_at"] or datetime.min.replace(tzinfo=timezone.utc))

        # 1. Equity Curve & Compounding
        running_equity = initial_equity
        equity_curve = [{"timestamp": (parsed_trades[0]["closed_at"] or datetime.now(timezone.utc)).isoformat(), "equity": initial_equity, "drawdown_pct": 0.0}]
        peak = initial_equity
        peak_time = parsed_trades[0]["closed_at"]
        max_dd_pct = 0.0
        current_dd_pct = 0.0
        max_dd_duration_days = 0.0

        for trade in parsed_trades:
            pnl = trade["pnl"]
            pnl_pct = trade["pnl_pct"]
            if pnl != 0.0:
                running_equity += pnl
            elif pnl_pct != 0.0:
                running_equity *= (1.0 + pnl_pct / 100.0)

            t_date = trade["closed_at"]
            if running_equity >= peak:
                peak = running_equity
                if t_date:
                    peak_time = t_date
                current_dd_pct = 0.0
            else:
                dd = ((peak - running_equity) / peak) * 100.0 if peak > 0 else 0.0
                if dd > max_dd_pct:
                    max_dd_pct = dd
                current_dd_pct = dd

                # Track drawdown duration from peak
                if t_date and peak_time:
                    dur_days = (t_date - peak_time).total_seconds() / 86400.0
                    if dur_days > max_dd_duration_days:
                        max_dd_duration_days = dur_days

            t_iso = trade["closed_at"].isoformat() if trade["closed_at"] else ""
            equity_curve.append({
                "timestamp": t_iso,
                "equity": round(running_equity, 2),
                "drawdown_pct": round(((peak - running_equity) / peak) * 100.0, 2) if peak > 0 else 0.0,
            })

        final_equity = running_equity
        total_net_pnl = final_equity - initial_equity
        total_return_pct = round(((final_equity - initial_equity) / initial_equity) * 100.0, 2)

        # 2. Win / Loss Profile & Expectancy
        wins = [t for t in parsed_trades if t["pnl"] > 0 or t["pnl_pct"] > 0]
        losses = [t for t in parsed_trades if t["pnl"] < 0 or t["pnl_pct"] < 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        total_trades = len(parsed_trades)
        win_rate_pct = round((winning_trades / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
        loss_rate_dec = (losing_trades / total_trades) if total_trades > 0 else 0.0
        win_rate_dec = (winning_trades / total_trades) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in losses if t["pnl"] < 0))
        if gross_profit == 0.0 and gross_loss == 0.0:
            gross_profit = sum(t["pnl_pct"] for t in wins if t["pnl_pct"] > 0)
            gross_loss = abs(sum(t["pnl_pct"] for t in losses if t["pnl_pct"] < 0))

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        wins_vals = [t["pnl"] if t["pnl"] != 0.0 else t["pnl_pct"] for t in wins]
        losses_vals = [abs(t["pnl"]) if t["pnl"] != 0.0 else abs(t["pnl_pct"]) for t in losses]
        avg_win_val = sum(wins_vals) / len(wins_vals) if wins_vals else 0.0
        avg_loss_val = sum(losses_vals) / len(losses_vals) if losses_vals else 1.0
        payoff_ratio = round(avg_win_val / avg_loss_val, 2) if avg_loss_val > 0 else 1.0

        expectancy_r = round((win_rate_dec * payoff_ratio) - loss_rate_dec, 2)
        expectancy_usd = round(total_net_pnl / total_trades, 2) if total_trades > 0 else 0.0

        # Best / worst trades
        all_pcts = [t["pnl_pct"] for t in parsed_trades if t["pnl_pct"] != 0.0] or [t["pnl"] / initial_equity * 100.0 for t in parsed_trades]
        best_trade_pct = round(max(all_pcts), 2) if all_pcts else 0.0
        worst_trade_pct = round(min(all_pcts), 2) if all_pcts else 0.0

        # 3. Daily Resampled Returns & Distribution
        daily_pnl: Dict[str, float] = {}
        for t in parsed_trades:
            dt = t["closed_at"]
            d_key = dt.strftime("%Y-%m-%d") if dt else "unknown"
            daily_pnl[d_key] = daily_pnl.get(d_key, 0.0) + (t["pnl_pct"] or (t["pnl"] / initial_equity * 100.0))

        d_returns = list(daily_pnl.values())
        if len(d_returns) > 1:
            daily_mean = float(np.mean(d_returns))
            daily_std = float(np.std(d_returns, ddof=1))
            best_day = round(float(np.max(d_returns)), 2)
            worst_day = round(float(np.min(d_returns)), 2)

            # Skewness & Kurtosis
            diffs = np.array(d_returns) - daily_mean
            m3 = float(np.mean(diffs ** 3))
            m4 = float(np.mean(diffs ** 4))
            s_val = daily_std if daily_std > 1e-8 else 1e-8
            skewness = round(float(m3 / (s_val ** 3)), 2)
            kurtosis = round(float(m4 / (s_val ** 4)) - 3.0, 2)  # excess kurtosis
        else:
            daily_mean = d_returns[0] if d_returns else 0.0
            daily_std = 0.0
            best_day = daily_mean
            worst_day = daily_mean
            skewness = 0.0
            kurtosis = 0.0

        # 4. Annualized Sharpe, Sortino & Calmar
        ann_factor = math.sqrt(252.0)
        if daily_std > 1e-8:
            annualized_sharpe = round(float((daily_mean / daily_std) * ann_factor), 2)
        else:
            annualized_sharpe = 0.0

        # Sortino (downside semi-deviation across full return series)
        downside_diff = np.minimum(0.0, np.array(d_returns))
        downside_std = float(np.sqrt(np.mean(downside_diff ** 2)))
        if downside_std > 1e-8:
            annualized_sortino = round(float((daily_mean / downside_std) * ann_factor), 2)
        else:
            annualized_sortino = 99.0 if daily_mean > 0 else 0.0

        # Annualized return estimation
        days_span = 30.0
        if start_date and end_date:
            days_span = max(1.0, (end_date - start_date).total_seconds() / 86400.0)
        elif parsed_trades and parsed_trades[0]["closed_at"] and parsed_trades[-1]["closed_at"]:
            span = (parsed_trades[-1]["closed_at"] - parsed_trades[0]["closed_at"]).total_seconds() / 86400.0
            if span > 0:
                days_span = span

        ann_return_pct = round(total_return_pct * (365.25 / max(days_span, 1.0)), 2)
        calmar = round(ann_return_pct / max_dd_pct, 2) if max_dd_pct > 0 else (99.0 if ann_return_pct > 0 else 0.0)

        # Compound Annual Growth Rate (CAGR)
        years = max(days_span / 365.25, 1.0 / 365.25)
        if initial_equity > 0 and final_equity > 0:
            cagr = round(((final_equity / initial_equity) ** (1.0 / years) - 1.0) * 100.0, 2)
        elif final_equity <= 0:
            cagr = -100.0
        else:
            cagr = 0.0

        # Tail Risk: Value-at-Risk (VaR 95%) and Conditional VaR (CVaR 95% / Expected Shortfall)
        if d_returns:
            p5 = float(np.percentile(d_returns, 5.0))
            var_95_pct = round(abs(min(0.0, p5)), 2) if p5 < 0 else 0.0
            tail_losses = [r for r in d_returns if r <= p5]
            if tail_losses:
                cvar_mean = float(np.mean(tail_losses))
                cvar_95_pct = round(abs(min(0.0, cvar_mean)), 2) if cvar_mean < 0 else 0.0
            else:
                cvar_95_pct = var_95_pct
        else:
            var_95_pct = 0.0
            cvar_95_pct = 0.0

        # Gain to Pain Ratio
        pos_sum = sum(r for r in d_returns if r > 0)
        neg_sum = abs(sum(r for r in d_returns if r < 0))
        gain_to_pain = round(pos_sum / neg_sum, 2) if neg_sum > 0 else (99.0 if pos_sum > 0 else 0.0)

        # 5. Asset breakdown
        by_sym: Dict[str, Dict[str, Any]] = {}
        for t in parsed_trades:
            s = t["symbol"]
            st = by_sym.setdefault(s, {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            st["trades"] += 1
            if t["pnl"] > 0 or t["pnl_pct"] > 0:
                st["wins"] += 1
            else:
                st["losses"] += 1
            st["net_pnl"] = round(st["net_pnl"] + t["pnl"], 2)

        for s, data in by_sym.items():
            cnt = data["trades"]
            data["win_rate_pct"] = round((data["wins"] / cnt) * 100.0, 2) if cnt > 0 else 0.0

        return TearsheetResult(
            initial_equity=round(initial_equity, 2),
            final_equity=round(final_equity, 2),
            total_net_pnl=round(total_net_pnl, 2),
            total_return_pct=total_return_pct,
            annualized_return_pct=ann_return_pct,
            annualized_sharpe=annualized_sharpe,
            annualized_sortino=annualized_sortino,
            calmar_ratio=calmar,
            gain_to_pain_ratio=gain_to_pain,
            max_drawdown_pct=round(max_dd_pct, 2),
            current_drawdown_pct=round(current_dd_pct, 2),
            max_drawdown_duration_days=round(max_dd_duration_days, 1),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            payoff_ratio=payoff_ratio,
            expectancy_r=expectancy_r,
            expectancy_usd=expectancy_usd,
            daily_mean_pct=round(daily_mean, 3),
            daily_std_pct=round(daily_std, 3),
            skewness=skewness,
            kurtosis=kurtosis,
            best_trade_pct=best_trade_pct,
            worst_trade_pct=worst_trade_pct,
            best_day_pct=best_day,
            worst_day_pct=worst_day,
            cagr_pct=cagr,
            var_95_pct=var_95_pct,
            cvar_95_pct=cvar_95_pct,
            equity_curve=equity_curve,
            by_symbol=by_sym,
        )

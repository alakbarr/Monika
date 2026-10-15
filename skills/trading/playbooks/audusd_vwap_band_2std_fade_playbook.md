---
name: audusd_vwap_band_2std_fade_playbook
description: VWAP 2-stddev boundary mean reversion for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 0.73
profit_factor: 1.1
max_drawdown_pct: 8.33
win_rate: 0.38
---

# AUDUSD Empirical Playbook: VWAP Multi-Band Statistical Stretch Reversion

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 0.73 (Zero-Lookahead simulation)
- **Profit Factor**: 1.10 (92 verified trade executions)
- **Max Drawdown**: 8.3% (Institutional risk profile)
- **Total PnL Return**: +4.6%
- **Win Rate**: 38.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Calculate intraday session VWAP and ATR-normalized deviation.
- Long Trigger: Price extends <= -1.5x ATR from VWAP and prints bullish close.
- Short Trigger: Price extends >= +1.5x ATR from VWAP and prints bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints two consecutive closes accelerating away from VWAP.
- Invalidate during central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.

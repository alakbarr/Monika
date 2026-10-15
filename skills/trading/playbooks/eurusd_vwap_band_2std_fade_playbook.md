---
name: eurusd_vwap_band_2std_fade_playbook
description: VWAP 2-stddev boundary mean reversion for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.57
status: active
sharpe_ratio: 3.76
profit_factor: 1.4
max_drawdown_pct: 5.69
win_rate: 0.495
---

# EURUSD Empirical Playbook: VWAP Multi-Band Statistical Stretch Reversion

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.76 (Zero-Lookahead simulation)
- **Profit Factor**: 1.40 (101 verified trade executions)
- **Max Drawdown**: 5.7% (Institutional risk profile)
- **Total PnL Return**: +20.7%
- **Win Rate**: 49.5% (Normalized at minimum 1:1.57 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.2x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Calculate intraday session VWAP and ATR-normalized deviation.
- Long Trigger: Price extends <= -1.5x ATR from VWAP and prints bullish close.
- Short Trigger: Price extends >= +1.5x ATR from VWAP and prints bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.57 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints two consecutive closes accelerating away from VWAP.
- Invalidate during central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.

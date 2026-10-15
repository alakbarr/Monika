---
name: xbrusd_liquidity_sweep_playbook
description: HTF swing liquidity sweep & displacement playbook for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 3.3
profit_factor: 1.34
max_drawdown_pct: 6.92
win_rate: 0.379
---

# XBRUSD Empirical Playbook: HTF Swing Liquidity Sweep & Displacement

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.30 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (87 verified trade executions)
- **Max Drawdown**: 6.9% (Institutional risk profile)
- **Total PnL Return**: +18.5%
- **Win Rate**: 37.9% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Map rolling 48-hour swing high (BSL) and swing low (SSL) excluding latest 2 bars.
- Long Trigger: H1 sweeps SSL, rejects, closes back above SSL with candle body >= 0.5x ATR.
- Short Trigger: H1 sweeps BSL, rejects, closes back below BSL with candle body >= 0.5x ATR.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a full body close beyond the sweep extreme.
- Invalidate if trade remains stagnant without momentum for 12 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.

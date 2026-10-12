---
name: quant-research-workflow
description: "Institutional quant research: hypothesis testing, backtests, and walk-forward."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [quant, backtest, walk_forward, parameter_plateau, monte_carlo, overfitting, sharpe, sortino, hypothesis, riset]
---

# Quantitative Research & Strategy Validation Workflow

## 1. Core Philosophy: Combating Overfitting & P-Hacking
In financial quantitative research, in-sample optimization without rigorous out-of-sample and stability verification is guaranteed to fail in live markets. Every strategy proposal must pass through a structured multi-stage validation pipeline.

## 2. The 6-Stage Quant Validation Pipeline

```
[1. Hypothesis Formulation]
       |
       v
[2. In-Sample Vectorized / Event-Driven Backtest]
       |
       v
[3. Walk-Forward Analysis (WFA)]
       |
       v
[4. Parameter Plateau & Sensitivity Matrix]
       |
       v
[5. Statistical Significance & Monte Carlo Reshuffling]
       |
       v
[6. Risk Proposal & Safe Incubation]
```

## 3. Metrics & Hurdle Requirements

| Quantitative Metric | Minimum Hurdle | Optimal Institutional Target | Failure Implication |
|:---|:---|:---|:---|
| **Sharpe Ratio (Annualized)** | > 1.20 | > 2.00 | Insufficient excess return relative to risk |
| **Sortino Ratio** | > 1.80 | > 3.00 | Excessive downside volatility |
| **Profit Factor** | > 1.40 | > 1.80 | Fragile expectancy margin |
| **Max Drawdown (DD)** | < 12.0% | < 6.0% | Account ruin or psychological stop risk |
| **Walk-Forward Efficiency (WFE)**| > 60.0% | > 75.0% | Overfit curve-fitting in-sample |
| **Trade Count Sample Size** | > 150 trades | > 500 trades | Lack of statistical significance ($p > 0.05$) |

## 4. Execution Tools & Code Integration
- **Backtesting Harness**: Use `run_backtest(strategy_name, symbol, start_date, end_date)`.
- **Custom Quantitative Analysis**: When running custom scripts or econometric models, leverage `save_script`, `run_saved_script`, or `execute_analysis_code` with `scipy`, `statsmodels`, `pandas`, and `numpy`.
- **Parameter Plateau**: Never select solitary isolated peak parameters. Choose the center of broad parameter plateaus where nearby permutations remain profitable.
- **Seasonality Auditing**: Incorporate `get_seasonality(symbol, timeframe="monthly")` to eliminate calendar-skew bias.

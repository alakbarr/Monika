---
name: quant-math-verification
description: "Institutional quantitative mathematics, formula verification, and statistical edge calculation standards."
category: GENERAL
version: 1.0.0
platforms: [windows, linux, macos]
tags: [quant, kelly_criterion, monte_carlo, sharpe_ratio, walk_forward, statistics, edge]
---

# Quantitative Math & Statistical Verification Playbook

> **Standard**: Every quantitative metric, simulation, or sizing formula reported by Monika must be mathematically rigorous, verifiable, and free of heuristic hand-waving or hallucination.

---

## 1. Core Quantitative Formulas Reference

### A. Kelly Criterion (Optimal Growth Sizing)
For a trading strategy with win rate $W$ and win/loss payoff ratio $R = \frac{\text{Average Win}}{\text{Average Loss}}$:
$$f^* = W - \frac{1 - W}{R} = \frac{W \cdot (R + 1) - 1}{R}$$
- **Institutional Practice (Half-Kelly / Quarter-Kelly)**:
  $$f_{\text{safe}} = 0.5 \times f^* \quad \text{or} \quad 0.25 \times f^*$$
  *Full Kelly introduces catastrophic drawdown volatility. Monika recommends Quarter-Kelly for forex trading.*

### B. Expected Value & Trade Expectancy ($E$)
$$\text{Expectancy} = (W \times \text{Avg Win}) - ((1 - W) \times \text{Avg Loss})$$
$$\text{Expectancy Ratio (in R)} = (W \times R) - (1 - W)$$
- A system has a positive statistical edge if and only if $\text{Expectancy} > 0$.

### C. Annualized Sharpe & Sortino Ratios
$$\text{Sharpe} = \frac{\mu_r - r_f}{\sigma_r} \times \sqrt{252}$$
$$\text{Sortino} = \frac{\mu_r - r_f}{\sigma_{\text{downside}}} \times \sqrt{252}$$
where $\sigma_{\text{downside}} = \sqrt{\frac{1}{N} \sum_{r_t < 0} r_t^2}$.

### D. Walk-Forward Efficiency (WFE)
$$\text{WFE} = \frac{\text{Annualized Out-of-Sample (OOS) Return}}{\text{Annualized In-Sample (IS) Return}} \times 100\%$$
- $\text{WFE} \ge 60\%$: Robust strategy with durable edge.
- $\text{WFE} < 50\%$: Overfitted curve-fitting bias; reject parameters.

---

## 2. Verification Protocol

When asked quantitative questions:
1. Call the corresponding registered tool:
   - `calculate_kelly_criterion(win_rate, win_loss_ratio)`
   - `simulate_portfolio_drawdown(num_simulations, win_rate, ...)`
   - `run_walk_forward_optimization(symbol, strategy_name, ...)`
   - `optimize_strategy_parameters(...)`
2. Never approximate or guess simulation figures—quote the exact output from the tool execution.
3. Always accompany raw percentages with risk-adjusted interpretations (e.g. explain why Full Kelly is hazardous and recommend Fractional Kelly).

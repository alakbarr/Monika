---
name: parameter-plateau-optimizer
description: "Parameter plateau search and neighbor perturbation robustness evaluation."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [plateau_optimizer, parameter_tuning, robustness, curve_fitting, quantitative]
---

# Parameter Plateau Optimizer Playbook

## 1. Implementation Architecture
Implements the Robert Pardo and Marcos López de Prado parameter plateau search methodology in `analysis/calculators/quant_plateau_optimizer.py`.

- **Isolated Peak (Overfitted)**: A single parameter combination yielding high Sharpe ratio ($SR = 2.8$) whose adjacent neighbors collapse to zero or negative returns. Disqualified.
- **Robust Plateau**: A contiguous parameter neighborhood where performance remains consistently positive (mean $SR \ge 1.5$, $\sigma < 0.20$). Approved for production deployment.

## 2. Objective Fitness Function
$$\text{Fitness}(\theta) = \mu_{\text{neighbor}}(SR) - \lambda \cdot \sigma_{\text{neighbor}}(SR) - \text{Penalty}_{\text{DSR}}$$

Where:
- $\mu_{\text{neighbor}}(SR)$: Mean Sharpe Ratio across a $\pm 10\%$ parameter grid perturbation.
- $\lambda = 1.5$: Penalty weight for neighbor variance (penalizing sharp performance cliffs).
- $\text{Penalty}_{\text{DSR}}$: Deflated Sharpe Ratio penalty (zero if $DSR \ge 0.60$, otherwise $2.0 \times (0.60 - DSR)$).

## 3. Canonical Parameter Search Ranges for Monika
| Strategy Component | Target Parameter | Search Range ($\theta$) | Step Size | Minimum Neighborhood Stability |
|:---|:---|:---|:---|:---|
| **Intraday Range-Edge** | Stop Loss ATR Multiplier | $1.0\times\text{--}1.8\times$ | $0.1\times$ | $\sigma_{\text{neighbor}} < 0.25$ |
| **Intraday Range-Edge** | Take Profit ADR Min/Max | $40\%\text{--}90\%$ | $5\%$ | $\sigma_{\text{neighbor}} < 0.20$ |
| **SMC Confluence** | Baseline Entry Threshold | $6.0\text{--}9.0$ | $0.5$ | $\mu_{\text{neighbor}} \ge 1.40$ |
| **Donchian Breakout** | Lookback Period (H4) | $15\text{--}35\text{ bars}$ | $5\text{ bars}$ | $\sigma_{\text{neighbor}} < 0.15$ |

## 4. Execution Workflow
1. Execute grid or Sobol sequence across parameter bounds.
2. Evaluate 8-neighbor perturbation matrix for top-decile candidates.
3. Reject candidates failing Deflated Sharpe Ratio test ($DSR < 0.55$).
4. Export winning plateau parameter vector into `config/settings.yaml`.

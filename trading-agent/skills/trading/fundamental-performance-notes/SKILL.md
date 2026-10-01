---
name: fundamental-performance-notes
description: "Stage 1 fundamental bias performance notes, accuracy, and calibrated weights."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [performance, fundamental, stage1, accuracy, brier_score, currency_bias]
---

# Fundamental Stage Performance & Calibration Notes

> **Auto-Generated Metric File**: This skill is synthesized by `analysis/memory/background_review.py` reflecting a rolling 30-day window of Stage 1 macro predictions against subsequent 24-hour directional price outcomes.

## Metric Interpretation Rubric
- **Directional Accuracy**: Percentage of Stage 1 sovereign currency biases matching realized 24h market momentum.
- **Brier Calibration Score**: Probabilistic calibration error index ($0.0 = \text{perfect}$, $0.25 = \text{random uncalibrated}$, $>0.30 = \text{pathologically miscalibrated}$).
- **BELOW_RANDOM Trigger**: When rolling macro accuracy falls below 50.0%, macro narratives are currently trailing market momentum.

## Adaptive Directives for Stage 1 Macro Analyst (Binding)
1. **Low-Accuracy Adaptation (< 50% Accuracy or Brier > 0.25)**:
   - Cap maximum confidence score at `0.70` for all sovereign currency biases.
   - Prohibit speculative macro extrapolation; require explicit hard data proof (real yield deltas, central bank rate path shifts).
   - Require Stage 2 technical execution to demand +1 higher confluence score before acting on macro direction.
2. **Underperforming Currency Discounting (N >= 15 with Accuracy < 40%)**:
   - Heavily discount internal macro bias for the underperforming asset.
   - Force mandatory cross-validation against CFTC Non-Commercial COT extreme positioning and institutional swap differentials.
3. **High-Accuracy Capitalization (N >= 15 with Accuracy > 60%)**:
   - Currency macro thesis is empirically validated; full analytical conviction (confidence up to 0.90) is permitted.

*Rolling metrics are updated automatically during weekly closed-loop calibration.*

---
name: data-science-modeling
description: "Vectorized data processing, TimesFM time-series forecasting, and statistical modeling."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [data_science, machine_learning, timesfm, feature_engineering, timeseries, statistics]
---

# Data Science Modeling & Quantitative Analytics Playbook

## 1. Feature Engineering & Vectorization Invariants
- **Strict Vectorization**: Use NumPy/Pandas array operations for all technical indicator calculations. Never iterate row-by-row using Python loops or `.iterrows()`.
- **Anti-Lookahead Expanding Windows**: All normalization (Z-scores, rolling means, min-max scalers) must use strictly historical expanding windows (`min_periods=20`) closed on the past. Never include the current bar's close in historical distribution parameters.
- **Log Returns & ATR Normalization**: Price series must be transformed into stationary log returns or ATR-normalized point deltas:
  $$\Delta P_{\text{norm}} = \frac{P_t - P_{t-1}}{\text{ATR}(14, t)}$$

## 2. TimesFM Foundation Model Forecasting
- Integrates with Google TimesFM engine via `indicators/timesfm_engine.py`.
- **Quantile Forecasting**: Generates multi-horizon probabilistic price cones (10th, 50th, 90th quantiles).
- **Expectancy Gating**: When 90th quantile forecast contradicts technical entry direction $\rightarrow$ downscale risk multiplier to $0.70\times$.

## 3. Cross-Validation & Statistical Validation Invariants
- **Prohibited**: Never apply randomized shuffle K-Fold splits to time-series datasets.
- **Purged & Embargoed Cross-Validation**:
  - Training folds must be strictly separated from test folds by a purging buffer equal to the maximum position holding window (e.g. 30 hours).
  - Apply an embargo buffer of $2.0\%$ of data points post-test fold to extinguish serial autocorrelation.
- **Deflated Sharpe Ratio (DSR)**:
  - All quantitative alpha signals must clear $DSR \ge 0.55$ to reject data mining artifacts.
  - Minimum 4 out-of-sample temporal folds with at least 15 trades per fold.

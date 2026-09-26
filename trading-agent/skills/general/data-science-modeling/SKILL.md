---
name: data-science-modeling
description: "Vectorized data processing, feature engineering, and statistical modeling."
version: 1.0.0
category: GENERAL
tags: [data_science, machine_learning, feature_engineering, timeseries, statistics]
---

# Data Science Modeling & Quantitative Analytics

## Core Principles
1. **Vectorized Operations**:
   - Prefer NumPy, Pandas, or Polars vector operations over Python loops for financial tick and bar arrays.
   - Guard against lookahead bias during feature calculation (all moving windows and Z-scores must use rolling/expanding windows closed on the left).

2. **Stationarity & Feature Normalization**:
   - Always verify stationarity using Augmented Dickey-Fuller (ADF) tests prior to autoregressive or linear modeling.
   - Transform prices into log-returns or fractional differentiation to preserve memory while achieving stationarity.

3. **Cross-Validation Invariants**:
   - Never use standard K-Fold shuffle cross-validation on time-series data.
   - Use Purged Group TimeSeries Split or Combinatorial Purged Cross-Validation (CPCV) with embargo periods.

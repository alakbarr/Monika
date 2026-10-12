---
name: academic-literature
description: "Synthesize mathematical formulations and alpha mechanics from quantitative papers."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [arxiv, papers, literature, quantitative_finance, machine_learning, equations]
---

# Quantitative Academic Literature Synthesis Playbook

## 1. Literature Discovery & Retrieval SOP
- **Target Channels**: arXiv (`q-fin.ST`, `q-fin.TR`, `stat.ML`), SSRN, Journal of Portfolio Management, Journal of Financial Economics.
- **Search Tooling Chain**: Call `academic_search` or `web_search` with targeted boolean operators (e.g. `"VPIN" AND "order flow toxicity"`, `"TimesFM" AND "time series foundation model"`).

## 2. 5-Point Quantitative Paper Evaluation Rubric
Rate candidate papers on a 1–5 scale across:
1. **Mathematical Core Rigor (1–5)**: Are equations closed-form, stationary, and free from hidden parameter tuning?
2. **Data Partitioning & Leakage Defense (1–5)**: Does the paper utilize Purged K-Fold or Walk-Forward Cross Validation?
3. **Transaction Cost Realism (1–5)**: Are realistic bid-ask spreads, slippage, and swap costs included in backtests?
4. **Execution Implementability in MT5 (1–5)**: Can the signal be calculated on OHLCV/tick bars without ultra-low latency requirements?
5. **Regime Robustness (1–5)**: Was the strategy tested across multiple volatile macro cycles (e.g. 2008, 2020, 2022)?

## 3. Red Flags & Instant Rejection Checklist
**REJECT paper immediately if any condition is true**:
- [ ] No out-of-sample testing (pure in-sample curve fitting).
- [ ] Lookahead bias (e.g., standardizing data using global dataset mean/variance instead of expanding window).
- [ ] Unrealistic zero-cost / zero-slippage assumptions.
- [ ] Survivorship bias in universe selection.

## 4. Mandatory Output Template for Accepted Papers
```markdown
### Quantitative Paper Synthesis: [Title] ([arXiv ID / Citation])
- **Alpha Invariant**: [1-sentence explanation of structural market anomaly exploited]
- **Mathematical Core**:
  $$[LaTeX Equation]$$
- **Python / NumPy Vectorized Implementation**:
  ```python
  # Clean, vectorized calculation
  def calculate_alpha_signal(df: pd.DataFrame) -> pd.Series:
      ...
  ```
- **Monika Integration Path**: [Target module: e.g. `indicators/timesfm_engine.py` or `analysis/calculators/`]
- **Risk Assessment**: [Failure modes and regime vulnerabilities]
```

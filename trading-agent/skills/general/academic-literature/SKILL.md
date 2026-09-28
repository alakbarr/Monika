---
name: academic-literature
description: Synthesize and extract mathematical formulations from arXiv/quant papers.
category: research
version: 1.0.0
platforms: [windows, linux, macos]
tags: [arxiv, papers, literature, quantitative-finance, machine-learning, equations]
---

# Quantitative Academic Literature Synthesis Playbook

Protocol for researching, dissecting, and operationalizing cutting-edge academic papers for algorithmic trading models.

## 1. Literature Discovery & Retrieval
- Target authoritative sources: arXiv (`q-fin`, `stat.ML`, `cs.LG`), SSRN, Journal of Financial Economics, Mathematical Finance.
- Use query formulation with explicit boolean operators and mathematical identifiers (e.g. `"order flow toxicity" AND "VPIN"`, `"deep reinforcement learning" AND "limit order book"`).

## 2. Structural Decomposition of Quantitative Papers
Extract and evaluate four critical pillars:
1. **Underlying Invariant**: What fundamental market anomaly or structural property does the author exploit?
2. **Mathematical Formulation**: Transcribe core equations into Python/NumPy vectorized pseudocode.
3. **Overfitting & Lookahead Bias**: Inspect data partitioning (Purged K-Fold vs Walk-Forward), transaction cost assumptions, and slippage modeling.
4. **Execution Feasibility**: Assess whether latency, order book liquidity, or borrow fees render the paper's alpha unimplementable in live MT5 markets.

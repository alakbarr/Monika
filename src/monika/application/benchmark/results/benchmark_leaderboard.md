# Monika Frontier LLM Trading Benchmark — Leaderboard

> **Methodology**: Deterministic Multi-Pillar Scoring (0 - 100) combining Stage 1 (Macro Framework, 40%) and Stage 2 (Asset Execution & Risk Math, 60%). 100% objective, mathematically verified, zero stochastic LLM bias.

| Rank | Model | Composite Score | Stage 1 (Macro) | Stage 2 (Execution) | Decision (EURUSD) | Total Latency | Cost (USD) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 🥇  | **Kimi k3 (max)** | **91.6** | 97.0 | 88.0 | `SELL` | 98.0s | $0.4984 |
| 🥈  | **DeepSeek v4.1 Flash (max)** | **91.6** | 97.0 | 88.0 | `SELL` | 101.4s | $0.0874 |
| 🥉  | **GLM-5.3 Flash (max)** | **90.8** | 96.2 | 87.2 | `SELL` | 207.6s | $0.0304 |
| 4.  | **Gemini 4 Argon (high)** | **89.8** | 92.4 | 88.0 | `SELL` | 202.0s | $0.5594 |
| 5.  | **Gemini 3.8 Flash (high)** | **83.3** | 76.5 | 87.8 | `SELL` | 211.0s | $0.4937 |
| 6.  | **GPT-6.1 Sol (high)** | **82.8** | 59.2 | 98.6 | `WAIT` | 289.9s | $0.4100 |
| 7.  | **Muse Spark 1.3 (max)** | **77.0** | 95.0 | 65.0 | `WAIT` | 207.2s | $0.1671 |
| 8.  | **DeepSeek v4 Pro (max)** | **65.0** | 89.3 | 48.8 | `SELL` | 599.3s | $0.1933 |
| 9.  | **GLM-5.3 (max)** | **60.0** | 85.4 | 43.0 | `SELL` | 1272.8s | $0.3936 |

## Scoring Pillar Breakdown

### Stage 1: Fundamental Macro Analysis (Max 100 pts)
- **Grounding (30 pts)**: Explicit citations of DXY, NFP (+29k), Treasury Yields (10Y 3.82%), VIX (16.7), FedWatch (82% Hold), and Energy Catalysts.
- **Invalidation (25 pts)**: Precision and falsifiability of per-currency invalidation conditions (>= 40 chars with concrete numerical levels/price/dates).
- **Priced-In & Counter-Thesis (25 pts)**: Completeness of 4-method priced-in assessment and substantive contrary thesis (>= 50 chars).
- **Efficiency (20 pts)**: Latency under 600s budget and non-runaway token consumption.

### Stage 2: Per-Asset Execution EURUSD (Max 100 pts)
- **Risk & Math Compliance (35 pts)**: Mathematically correct SL/TP side relative to entry, R:R >= 1.3, and ADR boundary compliance.
- **Structural Confluence (25 pts)**: Order Block / FVG / Liquidity level citations in rationale and valid confluence score.
- **Decision Discipline (20 pts)**: Quantitative invalidation levels and re-evaluation trigger presence.
- **Execution & Sizing (20 pts)**: Clean lot sizing execution via RiskGate and operational latency efficiency.

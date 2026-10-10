# Benchmark Report: System One Decision Models for News Classification

> **Generated at**: `2026-10-09 00:12:18 UTC`  
> **Task Role**: `news_classification` (System One Fast-Reflex Triage)  
> **Dataset**: `raw_news_batch_25.json` (25 Canonical Golden Fixtures with Analyst-Verified Ground Truth)  
> **Evaluation Endpoint**: `POST https://openrouter.ai/api/alpha/decisions`  
> **Scoring Protocol**: Deterministic System One Scorer (`40% Accuracy with Ordinal Grace, 35% Latency, 15% Calibration, 10% Schema`)  

---

## 1. Executive Summary & Model Leaderboard

System One (Decision) models utilize single forward-pass categorical probability distributions instead of slow autoregressive token generation. They output `output_tokens: 0`, yielding sub-second latencies and token costs approaching $0.00.

In volatility triage, **ordinal distance** is critical: classifying a `HIGH` catalyst as `MEDIUM` is a minor granularity distinction (within acceptable risk tolerances), whereas classifying a `BREAKING` war ultimatum as `NONE` is a catastrophic miss. Models are evaluated on both **Exact Accuracy** and **Adjacent Accuracy (±1 tier grace)**.

| Rank | Model Name | Model ID | Exact Acc | Adj Acc (±1) | Mean Tier Dist | Mean Lat (ms) | P95 Lat (ms) | Brier Cal (0-10) | S1 Score (0-10) | Cost / 1k News |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | TypeSafe Jev (latest) | `~typesafe/jev-latest` | 80.0% | **100.0%** | 0.20 | 483ms | 925ms | 8.36 | **9.51** | $0.0256 |
| 2 | TypeSafe Jev 1.13 | `typesafe/jev-1.13` | 80.0% | **100.0%** | 0.20 | 513ms | 1249ms | 8.30 | **9.45** | $0.0256 |
| 3 | Liquid D1 | `liquid/d1` | 76.0% | **100.0%** | 0.24 | 630ms | 1212ms | 8.59 | **9.32** | $0.0121 |
| 4 | Luna Decision (GPT-6) | `openai/gpt-6-luna-decisions` | 68.0% | **100.0%** | 0.32 | 543ms | 934ms | 8.16 | **9.29** | $0.0364 |
| 5 | Mercury Decide (Free) | `inception/mercury-decide:free` | 76.0% | **92.0%** | 0.32 | 370ms | 856ms | 8.66 | **9.28** | $0.0000 |
| 6 | Mercury Decide | `inception/mercury-decide` | 76.0% | **92.0%** | 0.32 | 565ms | 1078ms | 8.61 | **9.19** | $0.0071 |
| 7 | Cloudflare Clef Flash | `cloudflare/clef-flash` | 68.0% | **96.0%** | 0.36 | 581ms | 699ms | 7.81 | **9.08** | $0.0100 |
| 8 | Cloudflare Clef | `cloudflare/clef` | 72.0% | **92.0%** | 0.36 | 610ms | 738ms | 8.40 | **9.05** | $0.0177 |
| 9 | Perplexity Decider 27B | `perplexity/pplx-decider-v1.1-27b` | 76.0% | **88.0%** | 0.36 | 669ms | 1362ms | 8.12 | **8.82** | $0.0072 |
| 10 | Together TEV1 4B | `togethercomputer/tev1-4b-experimental` | 56.0% | **80.0%** | 0.68 | 563ms | 742ms | 7.46 | **8.47** | $0.0156 |
| 11 | Kev 4B | `jaredpalmer/kev-4b` | 68.0% | **92.0%** | 0.40 | 950ms | 1291ms | 5.80 | **8.02** | $0.0118 |
| 12 | Solar Decide Flash | `upstage/solar-decide-flash` | 60.0% | **72.0%** | 0.76 | 806ms | 1478ms | 7.56 | **7.86** | $0.0300 |
| 13 | Solar Decide | `upstage/solar-decide` | 72.0% | **92.0%** | 0.40 | 6828ms | 17250ms | 7.72 | **6.63** | $0.0300 |

---

## 2. In-Depth Architectural Analysis by Metric

### A. Classification Accuracy Breakdown (Per-Class Exact / Adjacent)
The canonical 25-item dataset tests edge cases across volatility tiers (`BREAKING`, `HIGH`, `MEDIUM`, `LOW`, `NONE`).

| Model Name | BREAKING | HIGH | MEDIUM | LOW | NONE |
| :--- | :---: | :---: | :---: | :---: | :---: |
| TypeSafe Jev (latest) | 100% (4/4) | 50% (1/2) | 100% (4/4) | 70% (7/10) | 80% (4/5) |
| TypeSafe Jev 1.13 | 100% (4/4) | 50% (1/2) | 100% (4/4) | 70% (7/10) | 80% (4/5) |
| Liquid D1 | 100% (4/4) | 50% (1/2) | 100% (4/4) | 70% (7/10) | 60% (3/5) |
| Luna Decision (GPT-6) | 100% (4/4) | 0% (0/2) | 75% (3/4) | 60% (6/10) | 80% (4/5) |
| Mercury Decide (Free) | 100% (4/4) | 50% (1/2) | 100% (4/4) | 80% (8/10) | 40% (2/5) |
| Mercury Decide | 100% (4/4) | 50% (1/2) | 100% (4/4) | 80% (8/10) | 40% (2/5) |
| Cloudflare Clef Flash | 100% (4/4) | 50% (1/2) | 100% (4/4) | 70% (7/10) | 20% (1/5) |
| Cloudflare Clef | 100% (4/4) | 50% (1/2) | 100% (4/4) | 80% (8/10) | 20% (1/5) |
| Perplexity Decider 27B | 100% (4/4) | 100% (2/2) | 100% (4/4) | 80% (8/10) | 20% (1/5) |
| Together TEV1 4B | 100% (4/4) | 50% (1/2) | 100% (4/4) | 30% (3/10) | 40% (2/5) |
| Kev 4B | 100% (4/4) | 50% (1/2) | 75% (3/4) | 50% (5/10) | 80% (4/5) |
| Solar Decide Flash | 100% (4/4) | 50% (1/2) | 75% (3/4) | 40% (4/10) | 60% (3/5) |
| Solar Decide | 100% (4/4) | 50% (1/2) | 75% (3/4) | 60% (6/10) | 80% (4/5) |

### B. Latency Hierarchy & Cloud WAN Distribution
- **Sub-1000ms Tier**: Models delivering real-time reflex speed over WAN HTTPS.
- **1000ms–2000ms Tier**: Reliable performance with minor network jitter.
- **>2000ms Outliers**: Models exhibiting queue delays or unoptimized execution paths.

### C. Economic Efficiency (Cost per Million News Items)
Unlike Context Generation models (e.g. GPT-6.1 Sol, Claude Opus 5.5, DeepSeek v4 Pro) which cost $5.00 – $40.00 per task, Decision models cost fractions of a cent:

| Model Name | Input Tokens / Batch | Total Cost (25 items) | Cost per 1,000 Items | Projected Cost / 100k Items |
| :--- | :---: | :---: | :---: | :---: |
| TypeSafe Jev (latest) | 15255 | $0.000641 | $0.0256 | $2.56 |
| TypeSafe Jev 1.13 | 15255 | $0.000641 | $0.0256 | $2.56 |
| Liquid D1 | 7586 | $0.000303 | $0.0121 | $1.21 |
| Luna Decision (GPT-6) | 9105 | $0.000910 | $0.0364 | $3.64 |
| Mercury Decide (Free) | 8873 | $0.000000 | $0.0000 | $0.00 |
| Mercury Decide | 8849 | $0.000177 | $0.0071 | $0.71 |
| Cloudflare Clef Flash | 10519 | $0.000249 | $0.0100 | $1.00 |
| Cloudflare Clef | 10519 | $0.000442 | $0.0177 | $1.77 |
| Perplexity Decider 27B | 8948 | $0.000179 | $0.0072 | $0.72 |
| Together TEV1 4B | 9295 | $0.000390 | $0.0156 | $1.56 |
| Kev 4B | 7043 | $0.000296 | $0.0118 | $1.18 |
| Solar Decide Flash | 14995 | $0.000750 | $0.0300 | $3.00 |
| Solar Decide | 14995 | $0.000750 | $0.0300 | $3.00 |

---

## 3. Production Deployment Recommendation for Monika

1. **Primary Reflex Screener**: The top-ranked model from this benchmark should be set as Monika's default `news_classification` System One provider.
2. **Zero Prose Leakage**: All tested models achieved 100% schema validity via typed questions (`type: choice`), completely eliminating markdown formatting or conversational noise.
3. **Fallback & Escalation Protocol**: Retain Monika's Option C Hybrid Architecture — Jev/Luna Decision handles 95% of incoming news volume for sub-cent costs; borderline or high-impact events automatically escalate to Gemini Flash Lite.

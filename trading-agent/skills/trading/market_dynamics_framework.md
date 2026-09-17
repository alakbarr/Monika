# file: skills/market_dynamics_framework.md

# Market Dynamics Framework — Expectations, Pricing & Event Behavior

Price discounts future expectations before reality. Sentiment drives price BEFORE events; reality corrects AFTER.

## Part 1: Buy the Rumor, Sell the News Matrix

| Scenario | Pre-Event State | Event Result | Reaction |
|:---|:---|:---|:---|
| **A: Fully Priced, Met** | Ran up 80-100% | Meets expectation | Counter-trend reversal ("sell the news") |
| **B: Fully Priced, Missed** | Ran up 80-100% | Disappoints | **Violent** counter-trend reversal |
| **C: Partially Priced, Beat** | Moved 30-60% | Exceeds expectation | Continuation with brief volatility |
| **D: NOT Priced In** | Flat / opposite | Surprise either way | **Large directional move** in surprise direction |

## Part 2: 4-Method Priced-In Score (1-10 Scale)

### Method 1: FedWatch Probability (Monetary Policy)
| Dominant Probability | Score | Label | Action |
|:---|:---|:---|:---|
| > 90% | 9-10 | Fully Priced In | Very high sell-the-news risk. Avoid trend entries. |
| 75-90% | 7-8 | Largely Priced In | High sell-the-news risk. Reduce size. |
| 55-75% | 5-6 | Partially Priced In | Moderate uncertainty. |
| 35-55% | 3-4 | Weakly Priced In | High potential post-event move. |
| < 35% | 1-2 | NOT Priced In | Genuine surprise risk. |

Rapid probability shift (+40% in 2 weeks) → add +1 for repricing momentum.

### Method 2: COT Extreme Positioning (Leveraged Funds)
Extreme thresholds (overcrowded = +3 score):
- Gold: > +200k / < -80k
- EUR/USD: > +150k / < -150k
- GBP/USD: > +80k / < -80k
- JPY / AUD: > +60k / < -60k

### Method 3: Price Run-Up vs ATR (H4, 20-bar lookback)
- `run_up_vs_atr` > 4.0: Score +3 (Very High)
- `run_up_vs_atr` 2.5 - 4.0: Score +2 (High)
- `run_up_vs_atr` 1.5 - 2.5: Score +1 (Moderate)
- `run_up_vs_atr` < 1.5: Score +0 (Low)

### Method 4: News Narrative Saturation
- 5+ articles over 3+ days: +2
- 2-4 articles over 1-2 days: +1
- <2 articles: +0

### Composite Score Action Guide
| Score | Label | Trading Rule |
|:---|:---|:---|
| 8-10 | **FULLY PRICED IN** | NO new trend entries in event direction. Wait for post-event. |
| 5-7 | **LARGELY PRICED IN** | High-confluence only. Reduce lot size 30-50%. |
| 3-4 | **PARTIALLY PRICED IN** | Standard confluence thresholds apply. |
| 1-2 | **NOT PRICED IN** | Genuine surprise risk. Pre-event positions are speculative. |

## Part 3: Driver Hierarchy & Conflict Resolution
1. Central Bank Policy Surprise > 2. Geopolitical Black Swan > 3. Tier-1 Data Surprise > 4. FedWatch Shift > 5. COT Extreme > 6. VIX Shift > 7. DXY Trend > 8. Technical Levels.
- Fresh driver beats stale driver.
- Balanced drivers (confidence < 50%) → WAIT or AVOID.

## Part 4: Event Timing Playbook
- **PRE-EVENT (12-48h)**: Volatility coiling. If score ≥7 → DO NOT enter.
- **EVENT (0-4h)**: Do NOT chase first candle spike.
- **POST-EVENT (4-48h)**: HIGHEST QUALITY window. Structure resets, liquidity swept.

## Part 5: Asset Nuances
- **USD/DXY**: FedWatch primary.
- **XAUUSD**: Real yields primary. COT leveraged net >150k = crowded.
- **EUR/GBP**: Central bank divergence (Fed vs ECB/BOE).
- **XTIUSD**: EIA inventory (Wed 14:30 UTC), OPEC compliance.
- **BTCUSD**: ETF net flows, funding rate (>+0.05% crowded long, <-0.05% crowded short).

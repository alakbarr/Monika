---
name: event-probability-playbook
description: "Central bank event probability modeling and 3-scenario trading plan playbook."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [event_probability, central_banks, fomc, rate_decision, scenario_planning]
---

# Event Probability Playbook — Central Bank Decisions & Macro Expectations

Institutional playbook for analyzing central bank rate decision probabilities (FOMC, ECB, BOE, BOJ, RBA), deconstructing market expectations vs policy reality, mitigating "sell-the-news" risks, evaluating asset pricing asymmetry, and formulating structured 3-Scenario Trading Plans integrated with Monika's LangGraph Trading Engine (`user_market_intel`).

---

## SECTION 1: 5-STAGE THINKING FLOW PROTOCOL

When evaluating interest rate decisions, central bank releases, or Tier-1 macroeconomic events, the AI Agent MUST execute a sequential 5-stage reasoning protocol:

```
[Stage 1: Data Gathering & Multi-Source Grounding]
                       │
                       ▼
[Stage 2: Priced-In Testing & Asymmetry Evaluation]
                       │
                       ▼
[Stage 3: Historical Precedents Matching]
                       │
                       ▼
[Stage 4: Press Conference & SEP Forward Guidance Decoding]
                       │
                       ▼
[Stage 5: Multi-Scenario Trading Plan Formulation & LangGraph Handshake]
```

### Stage 1: Data Gathering & Multi-Source Grounding
1. **Real-Time Market Probabilities**:
   - Execute `get_fedwatch_probabilities` (or `web_search` if local database records are unavailable or stale).
   - Record: Current dominant target bucket probability, 2-week trajectory shift (repricing momentum), and daily repricing velocity.
2. **Benchmark Yields & Sovereign Curves**:
   - Execute `get_treasury_yields` / `get_bond_yield_spreads`.
   - Record: US 2-Year Yield (sensitive to short-end policy expectations), US 10-Year Yield (long-term financial conditions benchmark), 2s10s curve spread (inversion vs un-inversion), and TIPS real yields.
3. **Hard Economic Data Catalysts**:
   - Inflation: Headline CPI YoY/MoM, Core CPI, Core PCE, and supercore services inflation (non-housing services).
   - Labor Market: Non-Farm Payrolls (NFP), official unemployment rate (U-3), and Average Hourly Earnings (AHE).
   - Growth & Real Activity: GDP quarterly annualized estimates and ISM Services/Manufacturing PMIs.
4. **Internal Committee Structure & Official Communications**:
   - Record voting split from prior meetings (e.g. 9-3 splits denote vocal hawkish/dovish factions).
   - Keynote speeches from the Chair (e.g. Jackson Hole) and signals from permanent voting members.
5. **Institutional Positioning & Retail Sentiment**:
   - Execute `get_cot_report` to inspect Leveraged Funds net positioning in DXY, Gold (XAUUSD), and US Treasuries.
   - Execute `get_retail_sentiment` / `get_fxssi_sentiment` to evaluate retail crowding skews.

---

### Stage 2: Priced-In Testing (Market Discounting Evaluation)
Calculate the composite Priced-In Score on a 1–10 scale. The canonical methodology is defined in `market-dynamics-framework/SKILL.md` and enforced by `analysis/calculators/macro_priced_in_calculator.py`:

$$\text{Priced-In Score} = \min(10, \max(1, \text{Method 1} + \text{Repricing Momentum} + \text{Method 2} + \text{Method 3} + \text{Method 4}))$$

*(Note: Raw unclamped score is strictly clamped to 1–10 for Pydantic schema validation and server-side RiskGate gating. Score $\ge 8$ mandates an immediate `WAIT` decision).*

#### 1. Method 1: FedWatch Dominant Probability
| Dominant Probability | Score | Label | Reaction Characteristics |
|:---|:---|:---|:---|
| > 90% | 9-10 | Fully Priced In | Severe "sell-the-news" reversal risk. Forbid pre-event breakout entries in consensus direction. |
| 75-90% | 7-8 | Largely Priced In | High sell-the-news risk. Reduce risk sizing (0.5x–0.7x lot size). |
| 55-75% | 5-6 | Partially Priced In | Moderate uncertainty; balanced two-way post-release volatility. |
| 35-55% | 3-4 | Weakly Priced In | Substantial directional expansion potential post-event. |
| < 35% | 1-2 | NOT Priced In | True shock risk upon realization. |

*Repricing Momentum Modifier*: If dominant probability surged >40% within the past 14 days (e.g. from 50% to 90%), add **+1 score**.

#### 2. Method 2: COT Extreme Positioning (Leveraged Funds)
If institutional speculative positioning is overstretched in the direction of consensus, add **+3 score**:
- Gold (XAUUSD): Net position > +200k (Overcrowded Long) or < -80k (Overcrowded Short).
- EUR/USD: Net position > +150k or < -150k.
- GBP/USD: Net position > +80k or < -80k.
- JPY / AUD: Net position > +60k or < -60k.

#### 3. Method 3: Price Run-Up vs ATR (H4, 20-bar lookback)
Measure how far price has extended prior to the catalyst relative to normal volatility:
- `run_up_vs_atr` > 4.0: Score **+3** (Extreme expansion, acute mean-reversion risk).
- `run_up_vs_atr` 2.5 - 4.0: Score **+2** (High expansion).
- `run_up_vs_atr` 1.5 - 2.5: Score **+1** (Moderate expansion).
- `run_up_vs_atr` < 1.5: Score **+0** (Price has not moved significantly).

#### 4. Method 4: News Narrative Saturation
- 5+ Tier-1 financial media headlines dominating the same thematic angle for 3+ consecutive days: Score **+2**.
- 2-4 articles over 1-2 days: Score **+1**.
- < 2 articles: Score **+0**.

#### Composite Score Action Guidelines & Execution Windows
| Composite Score | Label | Monika System Directive |
|:---|:---|:---|
| **8-10** | **FULLY PRICED IN** | **FORBID** opening new positions in consensus direction prior to release. Enforce WAIT or prepare *fade the move* setups post-press conference. |
| **5-7** | **LARGELY PRICED IN** | Require strict confluence. Scale down lot sizing by 30-50% (0.5x–0.7x). |
| **3-4** | **PARTIALLY PRICED IN** | Apply standard system confluence requirements. |
| **1-2** | **NOT PRICED IN** | Genuine surprise risk. Pre-release positions carry severe tail risk. |

**Execution Timing Windows (Event Timing Playbook)**:
- **PRE-EVENT (12-48 hours)**: Volatility undergoes compression. If priced-in score $\ge 7$, **FORBID** pre-event breakout positioning.
- **EVENT (0-4 hours)**: **NEVER** chase the opening candle spike at 14:00 EST / 18:00 UTC. Allow initial liquidity to be swept and await press conference confirmation (18:30 UTC / 14:30 EST). Enforce multi-timeframe discipline:
  - **Intraday Execution (M15 / H1)**: Entry window unlocks 15-30 minutes after press conference begins, ONLY AFTER initial liquidity sweep completes and confirmed Market Structure Shift (MSS) + FVG appear on M15/H1.
  - **Macro Swing Execution (H4 / D1)**: Allow H4 candle close (22:00 UTC) to confirm closing prints outside the liquidity sweep range before building scale-in swing positions.
- **POST-EVENT (4-48 hours)**: **HIGHEST PROBABILITY WINDOW**. Market structure resets, stop hunts clear, and true trend trajectory confirms post-presser.

---

## SECTION 2: CENTRAL BANK SURPRISE HISTORICAL PRECEDENTS & MULTI-ASSET TRANSMISSION

5 canonical historical precedents where central banks (The Fed) surprised or defied consensus, and the verified multi-asset transmission:

| Case & Period | Context & Consensus Expectations | Actual Decision & Policy Signal | Multi-Asset Transmission (DXY, Yields, Gold, Equities, Crypto) | Core Mechanism / Monika System Takeaway |
|:---|:---|:---|:---|:---|
| **1. 1994 Greenspan Preemptive Strike ("Bond Market Massacre")**<br>*Feb 4, 1994 – Feb 1995* | Trailing inflation subdued (~2.5%), GDP expanding 3-4%. Consensus priced flat/gradual rates (<20% probability of Feb 1994 hike). | Aggressive preemptive hiking cycle: +25bp (Feb), +25bp (Mar), +25bp (Apr), +50bp (May), +50bp (Aug), +75bp (Nov), +50bp (Feb 1995). Total +300bp hike (3.0% to 6.0%). | • **Yields**: US 10Y exploded +229 bps (5.75% to 8.04%); US 30Y surged to 8.16%. Global bond losses ~$1.5 Trillion.<br>• **DXY**: Initial consolidation due to US-Japan trade friction, followed by 1995-2001 structural super-bull rally.<br>• **Equities**: S&P 500 corrected -8.9% in Q1 1994; finished year flat (+1.5%).<br>• **Gold**: Capped in narrow range ($370–$395/oz), crushed by surging real yields.<br>• **Crypto (Modern Analog)**: Drastic global liquidity contraction; high-duration speculative assets face severe valuation de-rating.<br>• **Systemic**: Orange County bankruptcy (Dec 1994) & Mexican Peso Tequila Crisis. | **Preemptive Forward-Looking Tightening**:<br>Central bank front-runs inflation expectations before headline data accelerates. Lagging data watchers face violent de-leveraging. |
| **2. Sep 2013 Bernanke "No-Taper" Surprise**<br>*September 18, 2013* | Following May/June "Taper Tantrum" rhetoric, Bloomberg surveys & futures priced $10B–$15B/month tapering with >75-80% probability. | FOMC vote 9-1: Maintained full $85 Billion/month QE intact ($40B MBS, $45B Treasuries). Tapering deferred to Dec 2013. | • **Yields**: US 10Y plunged -17 bps on decision day (2.87% to 2.70%); 2Y fell 6 bps.<br>• **DXY**: Crashed -1.1% in a single day (81.2 to 80.1) to multi-month lows.<br>• **Gold**: Exploded +$55/oz (+4.2%) from $1,305 to $1,365 within hours.<br>• **Equities**: S&P 500 jumped +1.22% to fresh All-Time Highs (1,725.52).<br>• **Crypto**: BTC ($130) catalyzed by prolonged liquidity, ignited parabolic surge to $1,150 (+780%) in Nov 2013. | **Endogenous Financial Conditions Feedback Loop**:<br>Yield spikes prior to meeting already tightened financial conditions. Markets did the Fed's tightening work ahead of time, eliminating need for formal action. |
| **3. Sep 2015 Yellen "China Shock / Global Risk" Hold**<br>*September 17, 2015* | US labor market robust (5.1% unemployment). Strong consensus priced Sep 2015 as first rate liftoff post-ZIRP. | FOMC vote 9-1: Held rates at 0.00–0.25%, explicitly citing slowing Chinese growth and global financial turbulence. | • **Yields**: US 10Y fell -11 bps (2.30% to 2.19%); US 2Y fell -13 bps (0.81% to 0.68%).<br>• **DXY**: Dropped -0.7% (95.4 to 94.7) before stabilizing.<br>• **Gold**: Rallied +$14/oz (+1.25%) from $1,118 to $1,132 driven by declining real yields.<br>• **Equities**: Brief bounce then closed down (S&P -0.26%); Fed acknowledgment of global fragility triggered risk-off.<br>• **Crypto**: BTC consolidated at $230–$240, cementing base accumulation before 2016-2017 bull market. | **Mandate Asymmetry & Risk Management Minimax**:<br>Asymmetric loss function: Triggering global contagion/recession is far more destructive than delaying rate hikes by 6-12 weeks. |
| **4. Jul 2019 Powell "Mid-Cycle Adjustment" Hawkish Cut**<br>*July 31, 2019* | Markets priced 100% probability of 25bp cut, with futures curve projecting aggressive 75-100bp easing cycle due to trade war risks. | Cut 25bp (to 2.00–2.25%) & ended balance sheet runoff early. However at 14:35 EDT presser, Powell stated: *"It's a mid-cycle adjustment to policy, not the beginning of a long series of rate cuts."* | • **Yields**: US 2Y rose +4 bps (1.87% to 1.91%); curve inversion eased briefly.<br>• **DXY**: Surged +0.55% to 2-year highs (98.68) — Dollar rallied on a rate cut!<br>• **Equities**: S&P 500 tumbled -1.09% (-33 pts) and Dow -333 pts during press conference.<br>• **Gold**: Dumped -$20/oz ($1,430 to $1,410) as aggressive easing expectations were dashed.<br>• **Crypto**: BTC fell ~3% ($10,100 to $9,800), moving in lockstep with risk-off selling. | **Forward Guidance Dichotomy (Hawkish Cut)**:<br>Action fulfilled rate cut, but verbal forward guidance crushed further easing hopes. Never buy rate cut breakouts before press conference tone is verified! |
| **5. Jun 2022 Powell 75bp Acceleration ("WSJ Leak & CPI Panic")**<br>*June 15, 2022* | Official guidance pre-blackout: 50bp ("75bp is not actively considered"). On blackout Friday (Jun 10), May CPI spiked to 8.6% & UMich inflation hit 3.3%. | Monday Jun 13 14:00 EDT: Nick Timiraos (WSJ) published 75bp whisper leak. Wednesday Jun 15: Fed delivered 75bp emergency hike (largest since 1994) to 1.50–1.75%. | • **Yields**: US 2Y surged +55 bps over 2 days (2.81% to 3.36%), biggest 2-day leap since 1987; US 10Y hit 3.48%.<br>• **DXY**: Blasted from 104.0 to 105.6 (+1.5%) to 20-year highs.<br>• **Equities**: S&P 500 plunged -5.8% on Jun 10-13 (entered Bear Market). On Jun 15 announcement, saw relief rally +1.46% (already 100% priced via WSJ leak).<br>• **Gold**: Crushed -$65/oz ($1,875 to $1,810) by surging real yields.<br>• **Crypto**: Systemic contagion; BTC plummeted $30,000 to $20,000 (-33%) triggering Celsius & 3AC insolvencies. | **Emergency Credibility Defense & Blackout Whisper Leak**:<br>When inflation expectations threaten to de-anchor, central banks sacrifice forward guidance and utilize trusted proxy journalists to reprice markets within 48 hours to avert execution-day liquidity collapse. |

---

## SECTION 3: TAXONOMY OF 5 MARKET CONSENSUS VS CENTRAL BANK FAILURE MECHANISMS

1. **Mechanism 1: Endogenous Financial Conditions Feedback Loop (Markets Pre-Tightening / Easing)**
   - *Principle*: Financial markets react aggressively ahead of meeting dates. If sovereign yields spike, credit spreads widen, mortgage rates surge, and DXY rallies, the Financial Conditions Index (FCI) tightens autonomously.
   - *Failure Dynamic*: Market pre-tightening equals 50–100 bps of rate hikes without central bank action. Additional formal hikes risk causing severe financial accidents. Conversely, premature market rallies loosen conditions, forcing central banks to turn unexpectedly hawkish to preserve policy stance.

2. **Mechanism 2: Mandate Asymmetry & Risk Management Loss Function (Minimax Optimization)**
   - *Principle*: Market participants forecast median/mean outcomes, whereas central bank governors optimize *minimax* loss functions (minimizing tail-risk severity).
   - *Loss Matrix*:
     - *Type I Error* (Over-tightening): Growth slows 0.5%, easily remediated by rate cuts in subsequent quarters.
     - *Type II Error* (Under-tightening): Inflation expectations de-anchor, triggering 1970s-style wage-price spirals requiring deep recessions to resolve.
     - *Financial Tail Risk*: Major trade partner devaluations (China 2015) or regional banking stress (SVB 2023) immediately trigger caution (*pause/hold*), superseding short-term inflation targets.

3. **Mechanism 3: Institutional Credibility & Political Independence Signaling**
   - *Principle*: Time inconsistency dilemma. Executive politicians operate on short election cycles and favor low interest rates.
   - *Signaling Dynamic*: Yield-capping pressures or executive criticism create strong institutional incentives for central bank governors to deliver orthodox, firm decisions (hawkish hold or hike) to assert monetary independence before global *bond vigilantes*.

4. **Mechanism 4: Information Asymmetry, Latent Data, & Global Spillover**
   - *Principle*: Retail traders rely on public lagging economic data (monthly CPI, monthly NFP).
   - *Information Advantage*: Central banks possess exclusive real-time telemetry (daily Fedwire settlement volumes, banking liquidity flows, internal supervisory stress metrics, and BIS Basel swap-line intelligence). Decisions that seem perplexing to consensus are typically driven by latent liquidity fractures.

5. **Mechanism 5: Forward Guidance Ambiguity & Noise-Trader Overinterpretation**
   - *Principle*: Central bank communications are framed as conditional probability distributions ("data-dependent", "if appropriate").
   - *Consensus Trap*: Binary bet structures (CME FedWatch) oversimplify 60% conditional signals into 100% certainties, building overcrowded speculative positions. When the Chair refuses to commit to further moves during the presser, forced liquidation squeezes reverse prices aggressively.

---

## SECTION 3.1: ANALOG MATCHING ENGINE CRITERIA

To determine the closest historical precedent, `worker_macro` or `ChatAgent` MUST evaluate the following rubric:

### 1. Analog Match Score Rubric (0 – 100 Points)
1. **Priced-In Crowding & Easing Cycle Mispricing (Weight: 20 Points)**:
   - FedWatch dominant probability > 85% and 14-day shift > 30%: +10 Points.
   - Markets price aggressive cumulative cuts (>75 bps) while Core PCE / services inflation remain sticky (>2.5%): +10 Points (Triggers Powell 2019 / Hawkish Cut Analog).
2. **Financial Conditions Index (FCI) Divergence (Weight: 25 Points)**:
   - US 10Y Yield moved > 40 bps counter to policy direction over 60 days: +15 Points.
   - Credit Spreads (US High Yield OAS) widened > 75 bps: +10 Points (Triggers Bernanke 2013 Analog).
3. **External / Global Contagion Risk (Weight: 20 Points)**:
   - Key trading partner currency devaluation, regional banking crisis, or global equity index down > 7% in 30 days: +20 Points (Triggers Yellen 2015 Analog).
4. **Institutional Independence Friction (Weight: 15 Points)**:
   - Public executive criticism of rate policy or fiscal intervention opposing tightening: +15 Points (Triggers Greenspan 1994 Analog).
5. **Whisper Leak / Blackout Breach Indicator (Weight: 20 Points)**:
   - Emergence of authoritative journalist articles (e.g. WSJ / FT) during blackout drastically shifting rate projections: +20 Points (Triggers Powell 2022 Analog).

### 2. Historical Precedent Decision Tree
```
[Macro Event Evaluation]
       │
       ├─► Authoritative whisper leak during blackout (e.g. WSJ leak)?
       │     └─► YES ──► [2022 POWELL PRECEDENT]: Emergency Repricing. Watch for relief rally post-hike.
       │
       ├─► Global market crisis / elevated systemic stress (China / Banking / Geopolitical)?
       │     └─► YES ──► [2015 YELLEN PRECEDENT]: Minimax Hold. Surprise hold risk elevated.
       │
       ├─► US 10Y Yield spiked sharply, pre-tightening financial conditions autonomously?
       │     └─► YES ──► [2013 BERNANKE PRECEDENT]: No-Action/No-Taper Surprise. Fade tightening expectations.
       │
       ├─► Open political pressure AND Chair seeking to reinforce institutional independence?
       │     └─► YES ──► [1994 GREENSPAN PRECEDENT]: Preemptive Hawkish Action. Prepare for yield shock.
       │
       └─► Markets pricing prolonged easing cycle while inflation data remains sticky?
             └─► YES ──► [2019 POWELL PRECEDENT]: Hawkish Cut Trap. Prepare to short risk assets post-presser.
```

---

## SECTION 4: RATE DECISION (ACTION) VS FORWARD GUIDANCE FRAMEWORK

Central bank decisions consist of TWO distinct sequential phases that must never be conflated:

```
[18:00 UTC / 14:00 EST] ───────► INTEREST RATE DECISION & STATEMENT (Action)
                                  - Binary: Hike / Cut / Hold
                                  - HFT / Algorithmic reaction (0-120 seconds)
                                  - Warning: Frequently an initial Fakeout / Liquidity Sweep
                                             │
                                             ▼
[18:30 UTC / 14:30 EST] ───────► SEP DOT PLOT PROJECTIONS & PRESS CONFERENCE (Forward Guidance)
                                  - Median terminal rate, inflation, GDP projections
                                  - Chair rhetoric, tone, and independence assertions in Q&A
                                  - Dictates TRUE DIRECTIONAL TREND (True Trend 4-48 hours)
```

### 4-Quadrant Action vs Guidance Interaction Matrix

| Quadrant | Rate Decision (Action) | Forward Guidance (SEP & Q&A) | Asset Impact (DXY, XAU, Equities, Crypto) | Monika Execution Strategy |
|:---|:---|:---|:---|:---|
| **1. Hawkish Continuation** | Hike / Restrictive Hold | Dot Plot raised, Chair stresses inflation fight unfinished, refuses cut commitment | Sustained DXY rally; Yields surge; XAUUSD, Equities, BTCUSD face sharp selling | Align with USD strength post-presser; seek Sell on Rally setups on XAUUSD and EURUSD after H4 FVG retests. |
| **2. Dovish Hike (Sell-the-News)** | Expected Hike delivered | Dot Plot flattened, Chair notes rates sufficiently restrictive, avoids further hike commitments | DXY initial spike then aggressive dump; XAUUSD bounces violently; Equities rally | **Fade initial spike!** FORBID pre-event breakout orders. Allow initial spike to sweep swing low liquidity, then await M15/H1 liquidity sweep + MSS reclaim confirmation post-presser. |
| **3. Hawkish Cut (Bull Trap)** | Rate Cut delivered | Chair labels move a "mid-cycle adjustment", caps further cut expectations, Dot Plot raised | Equities & Gold dump post-initial pop; DXY rallies sharply | **Bull Trap Avoidance!** Do NOT chase buy breakouts on cut announcement. Await presser confirmation, prepare short setups following M15/H1 MSS breakdown. |
| **4. Dovish Easing Explosion** | Cut / Dovish Pause | Aggressive cut projections, Chair voices deep concern over labor market slack | DXY collapses; XAUUSD, BTCUSD, & Equities surge exponentially | **Momentum buy breakout!** Buy pullbacks into H1 discount zones on XAUUSD, EURUSD, BTCUSD; engage TrailingStopManager. |

---

## SECTION 5: INSTITUTIONAL 6-PART OUTPUT TEMPLATE

When presenting deep research briefings, the system MUST structure output according to the 6-part institutional framework:

```markdown
# Policy Decision & Press Conference Analysis: [Central Bank Name: FOMC / ECB / BOE / BOJ / RBA] — [Chair / Governor Name]

## 1. Current Data Snapshot & Market Expectation Trajectory
- Market Probabilities (CME FedWatch / OIS / Swap Pricing): [Current dominant percentage, daily & 14-day shift trajectory]
- Hard Economic Data Catalysts:
  - Committee Dynamics & Prior Meeting: [Prior voting split, key dissenters]
  - Leadership Communications: [Chair speeches, hawkish/dovish tone shifts]
  - Labor & Capacity: [NFP/Unemployment (Fed), Wage Tracker (ECB), Wage pressures (BoE), Shunto (BoJ), Capacity utilisation (RBA)]
  - Inflation Baseline: [Core PCE (Fed), HICP (ECB), CPI (BoE/BoJ), Trimmed Mean CPI (RBA)]
- Consensus Narrative Synthesis: [Why consensus prices this specific outcome as dominant base case]

## 2. Priced-In Score & Risk Asymmetry Analysis
- Absolute Certainty Test: [Why market probability is not 100% guaranteed]
- Priced-In Score Calculation (1-10): [Composite Methods 1-4 calculation]
- Friction & Skepticism Check:
  - Committee Factional Split: [Potential dovish/hawkish dissenters]
  - Institutional & Fiscal Friction: [Treasury interventions, bond buybacks, political pressure]
  - Reaction Asymmetry: [Sell-the-news vulnerability evaluation upon consensus delivery]
- Deviation Assessment: [Probability of surprise deviation based on independent signal convergence]

## 3. Historical Precedents & Central Bank Surprise Analysis
[Detailed historical precedent matching based on Sections 2 & 3]:
- Relevant Analog (e.g. Greenspan 1994, Bernanke 2013, Yellen 2015, Powell 2019, or Powell 2022): [Detailed comparison]
- Failure Mechanism: [Matching with Analog Match Score rubric]
- Current Cycle Takeaway: [Multi-asset transmission evaluation]

## 4. SEP Projection Deconstruction & Press Conference Tone Prediction
- Leadership Track Record & Communication Habits: [Data-dependent flexibility, stance stickiness]
- Projection Deconstruction (SEP Dot Plot / Staff Projections / Tenbo Report): [Terminal rate trajectory and inflation outlook]
- Action vs Forward Guidance Separation: [Classification into 4-Quadrant Matrix: Hawkish Continuation, Dovish Hike, Hawkish Cut, Dovish Easing]
- Press Conference Q&A Prediction: [Expected tone during presser Q&A]

## 5. Structured Multi-Scenario Trading Plan
- Scenario A: Base Case
  - Catalyst: [Consensus decision + Aligned forward guidance]
  - Asset Reaction: [DXY, Yields, Gold, Equities, Crypto]
  - Action Plan: [Timing execution: wait for initial spike liquidity sweep, confirm via FVG/MSS]
- Scenario B: Hawkish Shock
  - Catalyst: [Surprise hike or significantly more restrictive Dot Plot/Guidance]
  - Asset Reaction: [Sharp currency rally, yield surge, gold/risk asset dump]
  - Action Plan: [Short setups on inverse pairs, buy USD/yield continuation]
- Scenario C: Dovish Reversal / Sell-The-News
  - Catalyst: [Surprise cut, or hike with dovish forward guidance / terminal rate slashed]
  - Asset Reaction: [Currency sell-off, relief rally in gold/risk assets]
  - Action Plan: [Fade the move / liquidity sweep reclaim in H1 discount zone]

## 6. LangGraph Engine Handshake (user_market_intel)
- Persistence to user_market_intel: [Directive storage via save_market_intelligence]
- Mapping to Stage 1 & Stage 2: [Guiding macro bias and per-asset invalidation bounds]
- RiskGate Constraints: [Priced-in >= 8 (WAIT mandate) or 0.5x-0.7x lot sizing if priced-in 5-7]
```

> **CRITICAL CHAT DIRECTIVE ON TRADING PLANS:**
> 1. **Research Focus**: If the operator asks ONLY for event probability analysis, decision odds, history, or press conference predictions, the system **MUST NOT FORCE** technical trading plans (Entry, SL, TP) in the chat response. Provide a pure, rigorous, high-depth analytical response.
> 2. **Explicit Request Exception**: Granular technical trading plans (Entry, SL, TP) are ONLY provided if the operator explicitly requests a trading plan in their prompt (e.g. *"create a post-FOMC trading plan for XAUUSD"*).
> 3. **Background Auto-Persistence**: The system automatically persists the synthesized research to `user_market_intel` in the background, where it is consumed by **Stage 1 (Macro Analysis)** and **Stage 2 (Per-Asset Trading Plan)** during scheduled LangGraph cycles.

---

## SECTION 6: LANGGRAPH & DATABASE ENGINE INTEGRATION

1. **Storage Flow (Chat Agent → Database)**:
   - Chat Agent or operator persists market intelligence via `save_market_intelligence`:
     ```python
     save_market_intelligence(
         title="FOMC September Rate Decision Scenario Watch",
         summary="Base case 25bp hike with balanced Q&A. Watch XAUUSD sell-the-news reversal at 2500 OB.",
         full_content="[Full 3-Scenario Analysis]",
         intel_type="deep_research",
         affected_symbols="EURUSD,XAUUSD,USDJPY",
         directive="scenario_watch",
         target_cycle="until_event",
         expires_in_hours=24
     )
     ```
2. **Cycle Injection (Database → LangGraph Nodes)**:
   - Data is automatically loaded by `data_node.py` into state key `user_market_intel`.
   - `fundamental_node.py` (Stage 1) aligns global macro bias with scenario boundaries.
   - `per_asset_node.py` and `debate` nodes (Stage 2) validate technical SMC zones against scenario invalidation boundaries.
   - `risk_gate_node.py` enforces hard blocks when priced-in $\ge 9$, WAIT mandates when priced-in $\ge 8$ approaching events, and lot size reductions (0.5x–0.7x) with elevated confluence thresholds (+2) when priced-in score is 5–7 (LARGELY PRICED IN).

import re
from typing import Dict, Any

# Detailed setup documentation registry
SETUP_DOCS: Dict[str, Dict[str, Any]] = {
    "london_expansion": {
        "title": "London Open Volume Expansion Breakout",
        "regime": "breakout",
        "desc_template": "London open volume expansion breakout playbook for {symbol}.",
        "trigger": (
            "- Monitor market hours 07:00, 08:00, and 09:00 UTC during European liquidity surge.\n"
            "- Identify the 7-hour pre-London session high and low boundaries.\n"
            "- Long Trigger: H1 Close strictly exceeds the 7-hour high with tick volume >= 1.1x 20-MA.\n"
            "- Short Trigger: H1 Close strictly breaks below the 7-hour low with tick volume >= 1.1x 20-MA."
        ),
        "invalidation": (
            "- Invalidate if breakout bar closes with a rejection wick > 50% of total candle range.\n"
            "- Invalidate setup if macroeconomic news event occurs within 30 minutes of open."
        ),
    },
    "asian_range_breakout": {
        "title": "Asian Session Box Expansion Breakout",
        "regime": "breakout",
        "desc_template": "Asian session box expansion breakout playbook for {symbol}.",
        "trigger": (
            "- Identify the Asian consolidation high and low between 00:00 and 06:00 UTC.\n"
            "- Long Trigger: H1 Close at 07:00 or 08:00 UTC breaks above Asian high and Close > EMA 50.\n"
            "- Short Trigger: H1 Close at 07:00 or 08:00 UTC breaks below Asian low and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate setup if price prints an immediate false-break rejection pinbar back inside the range.\n"
            "- Invalidate if volume fails to expand on the breakout bar."
        ),
    },
    "ny_reversal": {
        "title": "New York Institutional Liquidity Reversal",
        "regime": "mean_reverting",
        "desc_template": "New York institutional opening reversal playbook for {symbol}.",
        "trigger": (
            "- Monitor New York open session between 13:00 and 16:00 UTC.\n"
            "- Map the previous 6-hour London high and low liquidity extremes.\n"
            "- Short Trigger: Price sweeps London high, rejects, closes lower than open, with RSI >= 56.\n"
            "- Long Trigger: Price sweeps London low, rejects, closes higher than open, with RSI <= 44."
        ),
        "invalidation": (
            "- Invalidate if price prints two consecutive H1 closes beyond the swept extreme.\n"
            "- Invalidate during major US FOMC interest rate decisions."
        ),
    },
    "asian_range_fade": {
        "title": "Asian Range Boundary Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Asian range boundary mean reversion playbook for {symbol}.",
        "trigger": (
            "- Active during low-volatility Asian hours (23:00 to 05:00 UTC).\n"
            "- Compute rolling 8-hour range high and low extremes.\n"
            "- Short Trigger: Price tests 99.95% of Asian high and prints a bearish rejection candle.\n"
            "- Long Trigger: Price tests 100.05% of Asian low and prints a bullish rejection candle."
        ),
        "invalidation": (
            "- Invalidate immediately if volume spikes > 2.0x volume MA indicating breakout regime.\n"
            "- Invalidate if trade is held past European open (06:00 UTC)."
        ),
    },
    "bollinger_reversion": {
        "title": "Bollinger Bands Volatility Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Bollinger Bands volatility mean reversion playbook for {symbol}.",
        "trigger": (
            "- Calculate 20-period Bollinger Bands (2.0 standard deviations) on H1.\n"
            "- Long Trigger: H1 Low pierces lower band, closes back inside, Close > Open, and RSI <= 42.\n"
            "- Short Trigger: H1 High pierces upper band, closes back inside, Close < Open, and RSI >= 58."
        ),
        "invalidation": (
            "- Invalidate if band width contracts below 0.25% indicating volatility squeeze rather than range.\n"
            "- Invalidate if price closes consecutively outside the bands."
        ),
    },
    "fvg_mitigation": {
        "title": "Institutional Fair Value Gap Mitigation",
        "regime": "trending",
        "desc_template": "Institutional Fair Value Gap mitigation playbook for {symbol}.",
        "trigger": (
            "- Identify 3-bar Fair Value Gap (FVG) imbalance on H1.\n"
            "- Long Trigger: Bullish FVG (Low[i-1] > High[i-3]), Close > EMA 50, retests FVG and bounces.\n"
            "- Short Trigger: Bearish FVG (High[i-1] < Low[i-3]), Close < EMA 50, retests FVG and rejects."
        ),
        "invalidation": (
            "- Invalidate if candle body closes completely through the FVG (invalidated imbalance).\n"
            "- Invalidate if higher timeframe trend flips against the FVG direction."
        ),
    },
    "donchian_breakout": {
        "title": "Volume-Expanded Donchian Channel Breakout",
        "regime": "breakout",
        "desc_template": "Volume-expanded Donchian channel breakout playbook for {symbol}.",
        "trigger": (
            "- Calculate 24-period Donchian Channel on H1 shifted by 1 bar to prevent lookahead.\n"
            "- Long Trigger: H1 Close breaks above upper channel, Close > EMA 50, with volume >= 1.15x MA.\n"
            "- Short Trigger: H1 Close breaks below lower channel, Close < EMA 50, with volume >= 1.15x MA."
        ),
        "invalidation": (
            "- Invalidate if breakout candle shows upper or lower rejection wick > 50% of range.\n"
            "- Invalidate if price re-enters channel midpoint."
        ),
    },
    "liquidity_sweep": {
        "title": "HTF Swing Liquidity Sweep & Displacement",
        "regime": "trending",
        "desc_template": "HTF swing liquidity sweep & displacement playbook for {symbol}.",
        "trigger": (
            "- Map rolling 48-hour swing high (BSL) and swing low (SSL) excluding latest 2 bars.\n"
            "- Long Trigger: H1 sweeps SSL, rejects, closes back above SSL with candle body >= 0.5x ATR.\n"
            "- Short Trigger: H1 sweeps BSL, rejects, closes back below BSL with candle body >= 0.5x ATR."
        ),
        "invalidation": (
            "- Invalidate if price prints a full body close beyond the sweep extreme.\n"
            "- Invalidate if trade remains stagnant without momentum for 12 bars."
        ),
    },
    "volatility_squeeze": {
        "title": "Carter Volatility Squeeze Expansion Breakout",
        "regime": "breakout",
        "desc_template": "Carter volatility squeeze expansion breakout for {symbol}.",
        "trigger": (
            "- Detect squeeze condition: Bollinger Bands compress strictly inside Keltner Channels.\n"
            "- Long Trigger: Squeeze fires long as Upper BB expands above Keltner and Close > EMA 50.\n"
            "- Short Trigger: Squeeze fires short as Lower BB expands below Keltner and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if squeeze fires and immediately reverses inside prior 2-bar low/high.\n"
            "- Invalidate if ATR contracts by more than 30% during the breakout candle."
        ),
    },
    "tsm_momentum": {
        "title": "Multi-Horizon Time-Series Momentum",
        "regime": "trending",
        "desc_template": "Multi-horizon time-series momentum playbook for {symbol}.",
        "trigger": (
            "- Compute 12-bar and 48-bar Rate of Change (ROC) momentum on H1.\n"
            "- Long Trigger: Both ROC12 and ROC48 positive above threshold and Close > EMA 20.\n"
            "- Short Trigger: Both ROC12 and ROC48 negative below threshold and Close < EMA 20."
        ),
        "invalidation": (
            "- Invalidate if shorter ROC flips opposite to longer ROC.\n"
            "- Invalidate if price closes across EMA 50 against momentum direction."
        ),
    },
    "smt_divergence": {
        "title": "Smart Money Technique (SMT) RSI Divergence",
        "regime": "mean_reverting",
        "desc_template": "Smart Money Technique RSI divergence playbook for {symbol}.",
        "trigger": (
            "- Identify divergence between price swings and 14-period RSI indicator.\n"
            "- Long Trigger: Price makes lower low over 8 bars but RSI prints higher low (+2.0 pts).\n"
            "- Short Trigger: Price makes higher high over 8 bars but RSI prints lower high (-2.0 pts)."
        ),
        "invalidation": (
            "- Invalidate if price continues running strongly against divergence for 2 bars.\n"
            "- Invalidate if RSI crosses midpoint (50.0) prior to entry execution."
        ),
    },
    "gap_fill_reversion": {
        "title": "Session Opening Gap Fill Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Session opening gap fill mean reversion for {symbol}.",
        "trigger": (
            "- Detect opening price gap relative to prior bar close >= 0.35x 14-period ATR.\n"
            "- Long Trigger: Downside gap opens below prior close and prints a bullish rejection candle.\n"
            "- Short Trigger: Upside gap opens above prior close and prints a bearish rejection candle."
        ),
        "invalidation": (
            "- Invalidate if gap extends beyond 1.5x ATR indicating fundamental runaway breakaway gap.\n"
            "- Invalidate if gap is not filled within specified holding horizon."
        ),
    },
    "ema_ribbon_momentum": {
        "title": "5-EMA Ribbon Trend Expansion Momentum",
        "regime": "trending",
        "desc_template": "5-EMA ribbon trend expansion momentum playbook for {symbol}.",
        "trigger": (
            "- Confirm perfect ribbon stacking: EMA 8 > 13 > 21 > 34 > 55 (Bull) or 8 < 13 < 21 < 34 < 55 (Bear).\n"
            "- Long Trigger: Low tests into EMA 21 buffer and candle closes above EMA 13.\n"
            "- Short Trigger: High tests into EMA 21 buffer and candle closes below EMA 13."
        ),
        "invalidation": (
            "- Invalidate if ribbon lines cross or tangle (indicating range regime).\n"
            "- Invalidate if candle body closes beyond EMA 55."
        ),
    },
    "multitimeframe_structure": {
        "title": "Multi-Timeframe H4 Trend & H1 CHoCH Structure",
        "regime": "trending",
        "desc_template": "Multi-timeframe H4 trend & H1 CHoCH structure playbook for {symbol}.",
        "trigger": (
            "- Higher timeframe alignment: H4 EMA 50 > H4 EMA 200 (Bull) or H4 EMA 50 < H4 EMA 200 (Bear).\n"
            "- Long Trigger: In H4 bull trend, H1 breaks above 5-bar swing high with expanding volume.\n"
            "- Short Trigger: In H4 bear trend, H1 breaks below 5-bar swing low with expanding volume."
        ),
        "invalidation": (
            "- Invalidate if H1 prints opposing CHoCH breaking structural swing low/high.\n"
            "- Invalidate if H4 trend structure flattens."
        ),
    },
    "macd_zero_cross": {
        "title": "MACD Zero-Line Momentum Expansion",
        "regime": "trending",
        "desc_template": "MACD zero-line momentum expansion playbook for {symbol}.",
        "trigger": (
            "- Calculate MACD (12, 26, 9) on H1.\n"
            "- Long Trigger: MACD line crosses strictly above zero line, Histogram > 0, and Close > EMA 50.\n"
            "- Short Trigger: MACD line crosses strictly below zero line, Histogram < 0, and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if MACD histogram prints a declining bar within 2 bars of entry.\n"
            "- Invalidate if price falls back across EMA 50."
        ),
    },
    "stochastic_reversal": {
        "title": "Stochastic Oscillator Exhaustion Reversal",
        "regime": "mean_reverting",
        "desc_template": "Stochastic oscillator exhaustion reversal for {symbol}.",
        "trigger": (
            "- Calculate Stochastic Oscillator (14, 3, 3) on H1.\n"
            "- Long Trigger: Stochastic %K <= 22, crosses above %D, and candle closes higher than open.\n"
            "- Short Trigger: Stochastic %K >= 78, crosses below %D, and candle closes lower than open."
        ),
        "invalidation": (
            "- Invalidate if price continues trending against signal while Stochastic stays pinned.\n"
            "- Invalidate if entry candle fails to close in direction of reversal."
        ),
    },
    "inside_bar_breakout": {
        "title": "Inside Bar Compression Volatility Breakout",
        "regime": "breakout",
        "desc_template": "Inside bar compression volatility breakout for {symbol}.",
        "trigger": (
            "- Identify Inside Bar: High[i-1] <= High[i-2] and Low[i-1] >= Low[i-2].\n"
            "- Long Trigger: H1 Close breaks strictly above inside bar high and Close > EMA 50.\n"
            "- Short Trigger: H1 Close breaks strictly below inside bar low and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if breakout bar fails to close beyond the mother bar boundary.\n"
            "- Invalidate if price chops inside the range for more than 4 bars after signal."
        ),
    },
    "pinbar_rejection": {
        "title": "Key Level Pinbar & Long Wick Exhaustion",
        "regime": "mean_reverting",
        "desc_template": "Key level pinbar & long wick exhaustion playbook for {symbol}.",
        "trigger": (
            "- Identify wide-range candle: High - Low >= 1.0x 14-period ATR.\n"
            "- Long Trigger: Lower rejection wick >= 55% of candle range and Close > EMA 50.\n"
            "- Short Trigger: Upper rejection wick >= 55% of candle range and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if subsequent candle breaks the extreme tip of the rejection wick.\n"
            "- Invalidate if pinbar occurs in low-volume dead-zone."
        ),
    },
    "keltner_bounce": {
        "title": "Keltner Channel Dynamic Boundary Bounce",
        "regime": "mean_reverting",
        "desc_template": "Keltner channel dynamic boundary bounce for {symbol}.",
        "trigger": (
            "- Calculate 20-period Keltner Channel with 1.5x ATR multiplier on H1.\n"
            "- Long Trigger: Low pierces lower Keltner boundary, closes back above it, with RSI <= 45.\n"
            "- Short Trigger: High pierces upper Keltner boundary, closes back below it, with RSI >= 55."
        ),
        "invalidation": (
            "- Invalidate if candle body closes fully outside the Keltner envelope.\n"
            "- Invalidate if midline slope is accelerating in direction of the breakout."
        ),
    },
    "orderblock_mitigation": {
        "title": "Institutional Orderblock Mitigation & Retest",
        "regime": "trending",
        "desc_template": "Institutional orderblock mitigation & retest for {symbol}.",
        "trigger": (
            "- Identify institutional orderblock (last opposing candle before sharp 2-bar displacement).\n"
            "- Long Trigger: Price mitigates into bullish orderblock zone, holds above OB low, and Close > EMA 50.\n"
            "- Short Trigger: Price mitigates into bearish orderblock zone, holds below OB high, and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if price prints a full body close through the distal boundary of the orderblock.\n"
            "- Invalidate if orderblock has been mitigated more than once."
        ),
    },
    "london_continuation": {
        "title": "Mid-London Session Trend Continuation",
        "regime": "trending",
        "desc_template": "Mid-London session trend continuation playbook for {symbol}.",
        "trigger": (
            "- Active during established London trend hours (10:00 to 12:00 UTC).\n"
            "- Long Trigger: EMA 20 > EMA 50, price pulls back to test EMA 20, and closes bullish.\n"
            "- Short Trigger: EMA 20 < EMA 50, price pulls back to test EMA 20, and closes bearish."
        ),
        "invalidation": (
            "- Invalidate if price closes beyond EMA 50 during European midday.\n"
            "- Invalidate before high-impact UK/European inflation or rate decisions."
        ),
    },
    "ny_drift": {
        "title": "New York Afternoon Trend Momentum Drift",
        "regime": "trending",
        "desc_template": "New York afternoon trend momentum drift for {symbol}.",
        "trigger": (
            "- Active during late US session hours (16:00 to 18:00 UTC).\n"
            "- Long Trigger: Close > EMA 50, candle closes higher than open, and RSI >= 52.\n"
            "- Short Trigger: Close < EMA 50, candle closes lower than open, and RSI <= 48."
        ),
        "invalidation": (
            "- Invalidate if price prints an evening star / morning star reversal pattern.\n"
            "- Invalidate during US bond market early close or low-liquidity holidays."
        ),
    },
    "engulfing_reversal": {
        "title": "High-Volume Engulfing Reversal Pattern",
        "regime": "mean_reverting",
        "desc_template": "High-volume engulfing reversal pattern playbook for {symbol}.",
        "trigger": (
            "- Current candle body >= 1.2x previous candle body and >= 0.6x 14-period ATR.\n"
            "- Long Trigger: Bearish candle followed by bullish engulfing closing above previous high with RSI <= 48.\n"
            "- Short Trigger: Bullish candle followed by bearish engulfing closing below previous low with RSI >= 52."
        ),
        "invalidation": (
            "- Invalidate if engulfing candle has an opposing wick > 40% of its body.\n"
            "- Invalidate if the preceding trend was fewer than 3 bars."
        ),
    },
    "ema_trend_retest": {
        "title": "Triple Moving Average Trend Retest",
        "regime": "trending",
        "desc_template": "Triple moving average trend retest playbook for {symbol}.",
        "trigger": (
            "- Confirm structural trend: EMA 20 > EMA 50 > EMA 200 (Bull) or EMA 20 < EMA 50 < EMA 200 (Bear).\n"
            "- Long Trigger: Price pulls back to test EMA 50 and closes strongly back above EMA 20.\n"
            "- Short Trigger: Price pulls back to test EMA 50 and closes strongly back below EMA 20."
        ),
        "invalidation": (
            "- Invalidate if price closes beyond the 200-period EMA.\n"
            "- Invalidate if EMA 20 crosses below EMA 50 before entry."
        ),
    },
    "tokyo_fix_expansion": {
        "title": "Tokyo Institutional Fix Trend Expansion",
        "regime": "trending",
        "desc_template": "Tokyo institutional fix trend expansion for {symbol}.",
        "trigger": (
            "- Active during Tokyo institutional fix window (00:00 to 02:00 UTC).\n"
            "- Long Trigger: H1 Close > Open, Close > EMA 20, and RSI >= 52.\n"
            "- Short Trigger: H1 Close < Open, Close < EMA 20, and RSI <= 48."
        ),
        "invalidation": (
            "- Invalidate if trade is held past Tokyo morning session without momentum.\n"
            "- Invalidate if Bank of Japan policy statement is scheduled."
        ),
    },
    "rsi_extreme_reversal": {
        "title": "RSI Deep Extreme Exhaustion Reversal",
        "regime": "mean_reverting",
        "desc_template": "RSI deep extreme exhaustion reversal for {symbol}.",
        "trigger": (
            "- Monitor 14-period RSI on H1 for structural exhaustion levels.\n"
            "- Long Trigger: RSI <= 32 and candle prints bullish close (Close > Open).\n"
            "- Short Trigger: RSI >= 68 and candle prints bearish close (Close < Open)."
        ),
        "invalidation": (
            "- Invalidate if RSI continues pushing deeper into extreme without divergence.\n"
            "- Invalidate if price fails to form a swing pivot within 2 bars."
        ),
    },
    "frankfurt_pre_open": {
        "title": "Frankfurt Pre-Open Liquidity Breakout",
        "regime": "breakout",
        "desc_template": "Frankfurt pre-open liquidity breakout playbook for {symbol}.",
        "trigger": (
            "- Active during Frankfurt opening hour (06:00 UTC) preceding London open.\n"
            "- Long Trigger: Price breaks above the 6-hour Asian range high and Close > Open.\n"
            "- Short Trigger: Price breaks below the 6-hour Asian range low and Close < Open."
        ),
        "invalidation": (
            "- Invalidate if price re-enters Asian box before 07:00 UTC.\n"
            "- Invalidate if spread widens abnormally during pre-market transition."
        ),
    },
    "ema9_21_cross": {
        "title": "Fast EMA 9/21 Trend Crossover & Expansion",
        "regime": "trending",
        "desc_template": "Fast EMA 9/21 trend crossover playbook for {symbol}.",
        "trigger": (
            "- Calculate 9-period and 21-period EMA on H1.\n"
            "- Long Trigger: EMA 9 crosses above EMA 21 and Close > EMA 50.\n"
            "- Short Trigger: EMA 9 crosses below EMA 21 and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if EMAs converge back together within 2 bars (whipsaw filter).\n"
            "- Invalidate if crossover occurs in flat 200 EMA slope."
        ),
    },
    "triple_ema_pullback": {
        "title": "Triple EMA Alignment Pullback Continuation",
        "regime": "trending",
        "desc_template": "Triple EMA alignment pullback continuation for {symbol}.",
        "trigger": (
            "- Bullish alignment: EMA 9 > EMA 21 > EMA 50.\n"
            "- Bearish alignment: EMA 9 < EMA 21 < EMA 50.\n"
            "- Long Trigger: Low tests EMA 21, candle closes higher than open and above EMA 21.\n"
            "- Short Trigger: High tests EMA 21, candle closes lower than open and below EMA 21."
        ),
        "invalidation": (
            "- Invalidate if price closes beyond EMA 50.\n- Invalidate if ribbon order flips prior to entry."
        ),
    },
    "london_ny_overlap": {
        "title": "London/New York Overlap Momentum Thrust",
        "regime": "trending",
        "desc_template": "London and New York overlap momentum thrust for {symbol}.",
        "trigger": (
            "- Active during heavy volume overlap window (12:00 to 15:00 UTC).\n"
            "- Volume surge: Volume >= 1.25x 20-period moving average and candle body >= 0.7x ATR.\n"
            "- Long Trigger: Strong bullish thrust candle with Close > EMA 50.\n"
            "- Short Trigger: Strong bearish thrust candle with Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if thrust candle is immediately erased by opposite candle.\n"
            "- Invalidate if US Non-Farm Payroll (NFP) release occurs during bar."
        ),
    },
    "vwap_mean_reversion": {
        "title": "Daily VWAP Extreme Stretch Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Daily VWAP extreme stretch mean reversion for {symbol}.",
        "trigger": (
            "- Measure standard deviation distance from Daily Institutional VWAP.\n"
            "- Long Trigger: Price extends <= -1.4 ATR below VWAP, Close > Open, and RSI <= 38.\n"
            "- Short Trigger: Price extends >= +1.4 ATR above VWAP, Close < Open, and RSI >= 62."
        ),
        "invalidation": (
            "- Invalidate if VWAP slope accelerates sharply in trend direction.\n"
            "- Invalidate if price does not reject within 2 bars."
        ),
    },
    "session_hl_fade": {
        "title": "Rolling 24-Hour High/Low Rejection Fade",
        "regime": "mean_reverting",
        "desc_template": "Rolling 24-hour high and low rejection fade for {symbol}.",
        "trigger": (
            "- Map rolling 24-hour swing high and low extremes.\n"
            "- Long Trigger: Price touches or sweeps 24-hour low and closes back above it.\n"
            "- Short Trigger: Price touches or sweeps 24-hour high and closes back below it."
        ),
        "invalidation": (
            "- Invalidate if candle body prints a full breakout close beyond the 24-hour extreme.\n"
            "- Invalidate during major scheduled interest rate announcements."
        ),
    },
    "two_bar_reversal": {
        "title": "Two-Bar Railway Track Swing Reversal",
        "regime": "mean_reverting",
        "desc_template": "Two-bar railway track swing reversal for {symbol}.",
        "trigger": (
            "- Two consecutive strong candles each with body >= 0.6x 14-period ATR.\n"
            "- Long Trigger: Down candle followed by immediate equal/larger up candle closing above prev open.\n"
            "- Short Trigger: Up candle followed by immediate equal/larger down candle closing below prev open."
        ),
        "invalidation": (
            "- Invalidate if second candle fails to recover at least 90% of the first candle body.\n"
            "- Invalidate if wick on reversal side exceeds 35% of total bar."
        ),
    },
    "ema50_trend_bounce": {
        "title": "Institutional 50-EMA Trend Boundary Bounce",
        "regime": "trending",
        "desc_template": "Institutional 50-EMA trend boundary bounce for {symbol}.",
        "trigger": (
            "- Macro trend filter: Close > EMA 200 (Bull) or Close < EMA 200 (Bear).\n"
            "- Long Trigger: Low touches EMA 50, rejects, and candle closes bullish above EMA 50.\n"
            "- Short Trigger: High touches EMA 50, rejects, and candle closes bearish below EMA 50."
        ),
        "invalidation": (
            "- Invalidate if candle body closes fully across EMA 50.\n"
            "- Invalidate if 200 EMA slope turns flat or opposing."
        ),
    },
    "asian_continuation": {
        "title": "Asian Mid-Session Trend Continuation",
        "regime": "trending",
        "desc_template": "Asian mid-session trend continuation for {symbol}.",
        "trigger": (
            "- Active during established Asian trading hours (03:00 to 05:00 UTC).\n"
            "- Long Trigger: Price holds above EMA 20, closes higher than open, with RSI >= 50.\n"
            "- Short Trigger: Price holds below EMA 20, closes lower than open, with RSI <= 50."
        ),
        "invalidation": (
            "- Invalidate if European pre-market volatility causes sudden trend break.\n"
            "- Invalidate if ATR drops below minimum liquidity threshold."
        ),
    },
    "donchian_midpoint": {
        "title": "Donchian Channel Midpoint Pullback Rebound",
        "regime": "trending",
        "desc_template": "Donchian channel midpoint pullback rebound for {symbol}.",
        "trigger": (
            "- Calculate 24-period Donchian Channel midpoint on H1.\n"
            "- Long Trigger: Close > EMA 50, low tests Donchian midpoint, and closes bullish above it.\n"
            "- Short Trigger: Close < EMA 50, high tests Donchian midpoint, and closes bearish below it."
        ),
        "invalidation": (
            "- Invalidate if price closes beyond the opposing Donchian boundary.\n"
            "- Invalidate if channel width is expanding rapidly against position."
        ),
    },
    "volume_thrust": {
        "title": "High-Volume Momentum Thrust Continuation",
        "regime": "trending",
        "desc_template": "High-volume momentum thrust continuation for {symbol}.",
        "trigger": (
            "- Volume surge: Tick volume >= 1.4x 20-period moving average and body >= 0.8x ATR.\n"
            "- Long Trigger: Bullish thrust candle with Close > EMA 20.\n"
            "- Short Trigger: Bearish thrust candle with Close < EMA 20."
        ),
        "invalidation": (
            "- Invalidate if next candle closes below the 50% retracement level of the thrust bar.\n"
            "- Invalidate if thrust bar exhibits exhaustion wicks > 40%."
        ),
    },
    "rsi_trend_pullback": {
        "title": "RSI Midpoint Trend Retest Continuation",
        "regime": "trending",
        "desc_template": "RSI midpoint trend retest continuation for {symbol}.",
        "trigger": (
            "- Trend filter: Close > EMA 50 (Bull) or Close < EMA 50 (Bear).\n"
            "- Long Trigger: RSI pulls back into 40-50 zone and candle closes higher than open.\n"
            "- Short Trigger: RSI pulls back into 50-60 zone and candle closes lower than open."
        ),
        "invalidation": (
            "- Invalidate if RSI drops below 35 in bull trend or rises above 65 in bear trend.\n"
            "- Invalidate if price prints structural lower low."
        ),
    },
    "london_afternoon_fade": {
        "title": "London Afternoon Liquidity Exhaustion Fade",
        "regime": "mean_reverting",
        "desc_template": "London afternoon liquidity exhaustion fade for {symbol}.",
        "trigger": (
            "- Active during London afternoon session (15:00 to 17:00 UTC).\n"
            "- Map the 8-hour London session high and low boundaries.\n"
            "- Short Trigger: High touches or exceeds 8-hour high and candle closes lower than open.\n"
            "- Long Trigger: Low touches or drops below 8-hour low and candle closes higher than open."
        ),
        "invalidation": (
            "- Invalidate if candle body expands beyond session high/low indicating trend run.\n"
            "- Invalidate during US macroeconomic news announcements."
        ),
    },
    "london_fix_reversal": {
        "title": "London 4PM Benchmark Fix Orderflow Reversal",
        "regime": "mean_reverting",
        "desc_template": "London 4PM benchmark fix orderflow reversal for {symbol}.",
        "trigger": (
            "- Active during London 4PM WM/Reuters benchmark fix window (15:00 to 16:00 UTC).\n"
            "- Short Trigger: RSI >= 56, price tests session highs, and candle prints bearish close.\n"
            "- Long Trigger: RSI <= 44, price tests session lows, and candle prints bullish close."
        ),
        "invalidation": (
            "- Invalidate if rebalancing flow creates runaway momentum rather than mean reversion.\n"
            "- Invalidate if fix window passes without execution."
        ),
    },
    "tokyo_afternoon_push": {
        "title": "Tokyo Afternoon Institutional Trend Push",
        "regime": "trending",
        "desc_template": "Tokyo afternoon institutional trend push for {symbol}.",
        "trigger": (
            "- Active during late Tokyo / Singapore afternoon session (05:00 to 07:00 UTC).\n"
            "- Long Trigger: Close > EMA 20, Close > Open, and RSI >= 50.\n"
            "- Short Trigger: Close < EMA 20, Close < Open, and RSI <= 50."
        ),
        "invalidation": (
            "- Invalidate if volatility collapses below minimum execution spread threshold.\n"
            "- Invalidate if European pre-market news disrupts trend structure."
        ),
    },
    "adr_extreme_fade": {
        "title": "Average Daily Range (ADR) Extreme Stretch Fade",
        "regime": "mean_reverting",
        "desc_template": "Average Daily Range extreme stretch fade for {symbol}.",
        "trigger": (
            "- Measure 12-hour intraday displacement relative to 14-period ATR.\n"
            "- Short Trigger: Intraday rise >= 1.5x ATR, Close < Open, and RSI >= 60.\n"
            "- Long Trigger: Intraday drop <= -1.5x ATR, Close > Open, and RSI <= 40."
        ),
        "invalidation": (
            "- Invalidate if fundamental catalyst causes expansion beyond 2.5x ATR.\n"
            "- Invalidate if reversal candle shows no buying/selling volume response."
        ),
    },
    "ema_ribbon_touch": {
        "title": "Dynamic EMA Ribbon Pullback & Touch",
        "regime": "trending",
        "desc_template": "Dynamic EMA ribbon pullback & touch playbook for {symbol}.",
        "trigger": (
            "- Trend filter: EMA 20 > EMA 50 (Bull) or EMA 20 < EMA 50 (Bear).\n"
            "- Long Trigger: Low touches EMA 20, rejects, and candle closes higher than open.\n"
            "- Short Trigger: High touches EMA 20, rejects, and candle closes lower than open."
        ),
        "invalidation": ("- Invalidate if price closes beyond EMA 50.\n- Invalidate if EMA 20 slope flattens."),
    },
    "asia_ny_sweep": {
        "title": "Asian High/Low Sweep During New York Open",
        "regime": "mean_reverting",
        "desc_template": "Asian high/low sweep during New York open for {symbol}.",
        "trigger": (
            "- Active during New York opening session (13:00 to 15:00 UTC).\n"
            "- Map the 24-hour Asian high and low liquidity boundaries.\n"
            "- Short Trigger: High sweeps above Asian high, rejects, and closes back below it.\n"
            "- Long Trigger: Low sweeps below Asian low, rejects, and closes back above it."
        ),
        "invalidation": (
            "- Invalidate if New York volume drives a full body close beyond the Asian boundary.\n"
            "- Invalidate during major US FOMC interest rate announcements."
        ),
    },
    "ema_stoch_confluence": {
        "title": "EMA Trend & Stochastic Momentum Confluence",
        "regime": "trending",
        "desc_template": "EMA trend and stochastic momentum confluence for {symbol}.",
        "trigger": (
            "- Trend filter: Close > EMA 50 (Bull) or Close < EMA 50 (Bear).\n"
            "- Long Trigger: Stochastic %K crosses above %D below 45, and candle closes higher than open.\n"
            "- Short Trigger: Stochastic %K crosses below %D above 55, and candle closes lower than open."
        ),
        "invalidation": (
            "- Invalidate if Stochastic %K recrosses %D within 2 bars.\n- Invalidate if price falls across EMA 50."
        ),
    },
    "aud_us_close_reversion": {
        "title": "US Session Close Range Exhaustion Reversion",
        "regime": "mean_reverting",
        "desc_template": "US session close range exhaustion reversion for {symbol}.",
        "trigger": (
            "- Active during US session close window (20:00 to 22:00 UTC) ahead of Sydney open.\n"
            "- Long Trigger: RSI <= 42 and candle prints bullish close (Close > Open).\n"
            "- Short Trigger: RSI >= 58 and candle prints bearish close (Close < Open)."
        ),
        "invalidation": (
            "- Invalidate if unexpected geopolitical news breaks during market rollover.\n"
            "- Invalidate if spread widens beyond 3.0 pips during 21:00-22:00 UTC transition."
        ),
    },
    "aud_london_break": {
        "title": "London Open Liquidity Breakout & Expansion",
        "regime": "breakout",
        "desc_template": "London open liquidity breakout and expansion for {symbol}.",
        "trigger": (
            "- Active during European session open (07:00 and 08:00 UTC).\n"
            "- Map the preceding 8-hour Asian consolidation high and low.\n"
            "- Long Trigger: H1 Close breaks strictly above the 8-hour high.\n"
            "- Short Trigger: H1 Close breaks strictly below the 8-hour low."
        ),
        "invalidation": (
            "- Invalidate if breakout candle exhibits an opposing wick > 50% of total range.\n"
            "- Invalidate if European market opens with zero volume expansion."
        ),
    },
    "tokyo_range_fade": {
        "title": "Tokyo Midday Range Boundary Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Tokyo midday range boundary mean reversion for {symbol}.",
        "trigger": (
            "- Active during quiet Tokyo midday session (02:00 to 05:00 UTC).\n"
            "- Compute rolling 4-hour local high and low boundaries.\n"
            "- Short Trigger: Price tests 4-hour high, closes lower than open, with RSI >= 55.\n"
            "- Long Trigger: Price tests 4-hour low, closes higher than open, with RSI <= 45."
        ),
        "invalidation": (
            "- Invalidate if Australian or Chinese macroeconomic data prints during the bar.\n"
            "- Invalidate if price closes beyond the 4-hour extreme."
        ),
    },
    "adx_di_cross": {
        "title": "ADX Directional Movement Trend Crossover",
        "regime": "trending",
        "desc_template": "ADX directional movement trend crossover for {symbol}.",
        "trigger": (
            "- Calculate 14-period Wilder Directional Movement Index (DI+ and DI-).\n"
            "- Long Trigger: DI+ crosses above DI- while H1 Close > 50-period EMA.\n"
            "- Short Trigger: DI+ crosses below DI- while H1 Close < 50-period EMA."
        ),
        "invalidation": (
            "- Invalidate if DI lines recross immediately in opposing direction within 2 bars.\n"
            "- Invalidate if price closes across the 50-period EMA benchmark."
        ),
    },
    "supertrend_cross": {
        "title": "SuperTrend Volatility Envelope Breakout",
        "regime": "breakout",
        "desc_template": "SuperTrend volatility envelope breakout for {symbol}.",
        "trigger": (
            "- Compute 20-period EMA and 2.0x ATR volatility envelope bands.\n"
            "- Long Trigger: Prior close was below upper band and current H1 Close breaks above.\n"
            "- Short Trigger: Prior close was above lower band and current H1 Close breaks below."
        ),
        "invalidation": (
            "- Invalidate if next candle closes back inside the envelope channel.\n"
            "- Invalidate if breakout bar candle range is less than 0.8x 14-period ATR."
        ),
    },
    "williams_r": {
        "title": "Williams %R Momentum Exhaustion Reversal",
        "regime": "mean_reverting",
        "desc_template": "Williams %R momentum exhaustion reversal for {symbol}.",
        "trigger": (
            "- Calculate 14-period Williams %R oscillator on H1 close.\n"
            "- Long Trigger: Williams %R rises above -80 from oversold and Close > Open.\n"
            "- Short Trigger: Williams %R drops below -20 from overbought and Close < Open."
        ),
        "invalidation": (
            "- Invalidate if oscillator recrosses the threshold within 2 bars.\n"
            "- Invalidate if breakout candle prints against the reversal direction."
        ),
    },
    "roc_burst": {
        "title": "Rate of Change Momentum Velocity Surge",
        "regime": "trending",
        "desc_template": "Rate of change momentum velocity surge for {symbol}.",
        "trigger": (
            "- Monitor 6-period Rate of Change (ROC) and 20-period volume moving average.\n"
            "- Long Trigger: ROC expands above surge threshold with Volume >= 1.25x 20-MA and Close > EMA 20.\n"
            "- Short Trigger: ROC drops below negative threshold with Volume >= 1.25x 20-MA and Close < EMA 20."
        ),
        "invalidation": (
            "- Invalidate if candle body retraces more than 50% on following bar.\n"
            "- Invalidate if volume fails to maintain institutional expansion."
        ),
    },
    "consecutive_exhaustion": {
        "title": "Four-Bar Momentum Exhaustion Reversal",
        "regime": "mean_reverting",
        "desc_template": "Four-bar momentum exhaustion reversal for {symbol}.",
        "trigger": (
            "- Long Trigger: Four consecutive bearish bars with RSI <= 40 followed by bullish close.\n"
            "- Short Trigger: Four consecutive bullish bars with RSI >= 60 followed by bearish close."
        ),
        "invalidation": (
            "- Invalidate if price prints a new extreme beyond the 4-bar exhaustion high/low.\n"
            "- Invalidate during major scheduled central bank rate announcements."
        ),
    },
    "atr_impulse": {
        "title": "ATR Expansion Large-Body Impulse Thrust",
        "regime": "trending",
        "desc_template": "ATR expansion large-body impulse thrust for {symbol}.",
        "trigger": (
            "- Filter for expansion candle with range >= 1.4x ATR and body >= 70% of candle range.\n"
            "- Long Trigger: Strong bullish impulse candle with Close > EMA 50.\n"
            "- Short Trigger: Strong bearish impulse candle with Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if subsequent bar closes past the 50% mark of the impulse candle.\n"
            "- Invalidate if impulse candle displays exhaustion wicks > 30% of total range."
        ),
    },
    "elder_triple_screen": {
        "title": "Alexander Elder Triple Screen Trend Pullback",
        "regime": "trending",
        "desc_template": "Alexander Elder triple screen pullback for {symbol}.",
        "trigger": (
            "- Higher Timeframe (H4) trend filter: EMA 50 > EMA 200 (Bull) or EMA 50 < EMA 200 (Bear).\n"
            "- Long Trigger: H4 Bull, H1 Stochastic %K <= 35, %K crosses above %D, and Close > Open.\n"
            "- Short Trigger: H4 Bear, H1 Stochastic %K >= 65, %K crosses below %D, and Close < Open."
        ),
        "invalidation": (
            "- Invalidate if H4 trend structure invalidates with EMA 50/200 cross.\n"
            "- Invalidate if Stochastic %K recrosses %D within 2 bars."
        ),
    },
    "asian_lunch_drift": {
        "title": "Asian Midday Institutional Drift Continuation",
        "regime": "trending",
        "desc_template": "Asian midday institutional drift for {symbol}.",
        "trigger": (
            "- Active during quiet Asian midday window (04:00 to 06:00 UTC).\n"
            "- Long Trigger: Close > EMA 20, Close > Open, and RSI >= 50.\n"
            "- Short Trigger: Close < EMA 20, Close < Open, and RSI <= 50."
        ),
        "invalidation": (
            "- Invalidate if European pre-market orderflow disrupts trend before 06:00 UTC.\n"
            "- Invalidate if price crosses back across the 20-period EMA."
        ),
    },
    "ny_morning_breakout": {
        "title": "New York Morning Session Expansion Breakout",
        "regime": "breakout",
        "desc_template": "New York morning session breakout for {symbol}.",
        "trigger": (
            "- Active during high-liquidity New York morning open (13:00 to 15:00 UTC).\n"
            "- Map the preceding 6-hour London consolidation high and low.\n"
            "- Long Trigger: Close breaks above 6-hour high and Close > EMA 50.\n"
            "- Short Trigger: Close breaks below 6-hour low and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if breakout candle fails to hold beyond the 6-hour boundary.\n"
            "- Invalidate during major US FOMC interest rate announcements."
        ),
    },
    "donchian_retest": {
        "title": "Donchian Midline Channel Pullback Bounce",
        "regime": "trending",
        "desc_template": "Donchian midline channel pullback bounce for {symbol}.",
        "trigger": (
            "- Calculate 24-period Donchian Channel midpoint on H1 timeframe.\n"
            "- Long Trigger: Close > EMA 50, Low tests Donchian midpoint, and closes bullish above it.\n"
            "- Short Trigger: Close < EMA 50, High tests Donchian midpoint, and closes bearish below it."
        ),
        "invalidation": (
            "- Invalidate if candle body closes completely across the Donchian midline.\n"
            "- Invalidate if Donchian channel boundaries contract into a tight squeeze."
        ),
    },
    "rejection_wick_extreme": {
        "title": "24-Hour Range Extreme Rejection Wick Sweep",
        "regime": "mean_reverting",
        "desc_template": "24-hour range extreme rejection wick sweep for {symbol}.",
        "trigger": (
            "- Candle total range >= 1.0x 14-period ATR.\n"
            "- Long Trigger: Lower wick >= 55% of candle range testing 24-hour low and closing higher.\n"
            "- Short Trigger: Upper wick >= 55% of candle range testing 24-hour high and closing lower."
        ),
        "invalidation": (
            "- Invalidate if subsequent candle breaks the extreme tip of the rejection wick.\n"
            "- Invalidate if spread widens beyond asset risk limit."
        ),
    },
    "macd_pullback": {
        "title": "MACD Zero-Line Trend Retest & Momentum Turn",
        "regime": "trending",
        "desc_template": "MACD zero-line trend retest momentum turn for {symbol}.",
        "trigger": (
            "- Long Trigger: MACD Line > 0, MACD Histogram turns positive (<=0 to >0), and Close > EMA 20.\n"
            "- Short Trigger: MACD Line < 0, MACD Histogram turns negative (>=0 to <0), and Close < EMA 20."
        ),
        "invalidation": (
            "- Invalidate if MACD line crosses zero into opposing territory.\n"
            "- Invalidate if price breaks opposite the 20-period EMA."
        ),
    },
    "tokyo_open_sweep": {
        "title": "Tokyo Open Session Liquidity Sweep",
        "regime": "mean_reverting",
        "desc_template": "Tokyo open liquidity sweep playbook for {symbol}.",
        "trigger": (
            "- Active during Tokyo open hours between 00:00 and 02:00 UTC.\n"
            "- Map rolling 12-hour high and low liquidity extremes.\n"
            "- Long Trigger: Low sweeps 12-hour low, closes back inside with bullish candle.\n"
            "- Short Trigger: High sweeps 12-hour high, closes back inside with bearish candle."
        ),
        "invalidation": (
            "- Invalidate if price closes consecutively beyond swept extreme.\n"
            "- Invalidate if volume surge exceeds 2.5x volume MA."
        ),
    },
    "frankfurt_continuation": {
        "title": "Frankfurt Pre-Market Momentum Continuation",
        "regime": "trending",
        "desc_template": "Frankfurt pre-market continuation playbook for {symbol}.",
        "trigger": (
            "- Active during European pre-market hours (06:00 to 07:00 UTC).\n"
            "- Long Trigger: Close > EMA 20, Close > Open, and volume >= 1.1x volume MA.\n"
            "- Short Trigger: Close < EMA 20, Close < Open, and volume >= 1.1x volume MA."
        ),
        "invalidation": (
            "- Invalidate if price closes back across EMA 20 before London open.\n"
            "- Invalidate during high-impact European economic releases."
        ),
    },
    "london_lunch_fade": {
        "title": "London Midday Session Mean Reversion Fade",
        "regime": "mean_reverting",
        "desc_template": "London midday session mean reversion for {symbol}.",
        "trigger": (
            "- Active during European midday lull (11:00 to 12:00 UTC).\n"
            "- Long Trigger: RSI <= 36 and candle prints bullish rejection close.\n"
            "- Short Trigger: RSI >= 64 and candle prints bearish rejection close."
        ),
        "invalidation": (
            "- Invalidate if price breaks session high/low with increasing volume.\n"
            "- Invalidate if held past New York open (13:00 UTC)."
        ),
    },
    "h4_trend_h1_pullback": {
        "title": "H4 Macro Trend Alignment & H1 EMA Pullback",
        "regime": "trending",
        "desc_template": "H4 macro trend and H1 pullback playbook for {symbol}.",
        "trigger": (
            "- Long Trigger: H4 EMA 50 > H4 EMA 200, H1 Low tests EMA 20, and closes bullish.\n"
            "- Short Trigger: H4 EMA 50 < H4 EMA 200, H1 High tests EMA 20, and closes bearish."
        ),
        "invalidation": (
            "- Invalidate if H1 candle body closes across EMA 50.\n- Invalidate if H4 trend structure breaks."
        ),
    },
    "asian_box_compression": {
        "title": "Asian Range Volatility Compression Breakout",
        "regime": "breakout",
        "desc_template": "Asian range box compression breakout for {symbol}.",
        "trigger": (
            "- Asian session 7-hour range contracts strictly <= 0.9x 14-period ATR.\n"
            "- Long Trigger: H1 Close at 07:00 or 08:00 UTC breaks above Asian range.\n"
            "- Short Trigger: H1 Close at 07:00 or 08:00 UTC breaks below Asian range."
        ),
        "invalidation": (
            "- Invalidate if price immediately re-enters the compressed range.\n"
            "- Invalidate if breakout bar displays long rejection wick."
        ),
    },
    "turtle_soup_sweep": {
        "title": "Turtle Soup 20-Bar False Breakout Reversal",
        "regime": "mean_reverting",
        "desc_template": "Turtle soup false breakout sweep for {symbol}.",
        "trigger": (
            "- Map 20-period swing high and swing low boundaries.\n"
            "- Long Trigger: Low pierces 20-bar low but closes back above with bullish bar.\n"
            "- Short Trigger: High pierces 20-bar high but closes back below with bearish bar."
        ),
        "invalidation": (
            "- Invalidate if subsequent candle breaks the extreme wick tip.\n"
            "- Invalidate if volume exceeds 2.0x 20-period volume MA."
        ),
    },
    "vwap_band_2std_fade": {
        "title": "VWAP Multi-Band Statistical Stretch Reversion",
        "regime": "mean_reverting",
        "desc_template": "VWAP 2-stddev boundary mean reversion for {symbol}.",
        "trigger": (
            "- Calculate intraday session VWAP and ATR-normalized deviation.\n"
            "- Long Trigger: Price extends <= -1.5x ATR from VWAP and prints bullish close.\n"
            "- Short Trigger: Price extends >= +1.5x ATR from VWAP and prints bearish close."
        ),
        "invalidation": (
            "- Invalidate if price prints two consecutive closes accelerating away from VWAP.\n"
            "- Invalidate during central bank rate announcements."
        ),
    },
    "double_inside_bar": {
        "title": "Double Inside Bar Coiling Spring Breakout",
        "regime": "breakout",
        "desc_template": "Double inside bar coiling breakout for {symbol}.",
        "trigger": (
            "- Detect two consecutive inside bars: Bar[i-1] inside Bar[i-2] inside Bar[i-3].\n"
            "- Long Trigger: H1 Close breaks above Bar[i-1] high with Close > Open.\n"
            "- Short Trigger: H1 Close breaks below Bar[i-1] low with Close < Open."
        ),
        "invalidation": (
            "- Invalidate if breakout candle fails to close outside the mother bar range.\n"
            "- Invalidate if volatility contracts below minimum trading threshold."
        ),
    },
    "three_candle_thrust": {
        "title": "Three-Bar Institutional Impulse Continuation",
        "regime": "trending",
        "desc_template": "Three candle institutional thrust for {symbol}.",
        "trigger": (
            "- Long Trigger: 3 consecutive bullish bars, Close > EMA 50, and expanding close.\n"
            "- Short Trigger: 3 consecutive bearish bars, Close < EMA 50, and expanding close."
        ),
        "invalidation": (
            "- Invalidate if subsequent candle fully engulfs the third thrust bar.\n"
            "- Invalidate if price stalls at major HTF support/resistance."
        ),
    },
    "supertrend_bounce": {
        "title": "Supertrend Trailing Dynamic Trend Bounce",
        "regime": "trending",
        "desc_template": "Supertrend ATR trail trend bounce for {symbol}.",
        "trigger": (
            "- Long Trigger: Close > EMA 50, Low tests dynamic EMA 50 buffer, and closes bullish.\n"
            "- Short Trigger: Close < EMA 50, High tests dynamic EMA 50 buffer, and closes bearish."
        ),
        "invalidation": (
            "- Invalidate if candle body closes fully across EMA 50 line.\n"
            "- Invalidate if higher timeframe MACD histogram turns divergent."
        ),
    },
    "adr_exhaustion_reversal": {
        "title": "24-Hour Range Exhaustion Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Average daily range exhaustion reversal for {symbol}.",
        "trigger": (
            "- Rolling 24-hour range expands >= 1.1x 14-period ATR.\n"
            "- Long Trigger: Low tests 24h low, RSI <= 40, and candle closes bullish.\n"
            "- Short Trigger: High tests 24h high, RSI >= 60, and candle closes bearish."
        ),
        "invalidation": (
            "- Invalidate if price prints a runaway trend candle closing beyond the extreme.\n"
            "- Invalidate if fundamental catalyst triggers sustained orderflow."
        ),
    },
    "fvg_discount_retest": {
        "title": "Fair Value Gap 50% Midpoint Mitigation",
        "regime": "trending",
        "desc_template": "Fair Value Gap discount retest for {symbol}.",
        "trigger": (
            "- Identify 3-bar Fair Value Gap imbalance on H1 chart.\n"
            "- Long Trigger: Bullish FVG, Low tests 50% midpoint, Close > EMA 50, bullish close.\n"
            "- Short Trigger: Bearish FVG, High tests 50% midpoint, Close < EMA 50, bearish close."
        ),
        "invalidation": (
            "- Invalidate if price closes completely through the FVG zone.\n"
            "- Invalidate if momentum reverses against the underlying trend."
        ),
    },
    "london_ny_transition": {
        "title": "London NY Overlap Transition Trend Momentum",
        "regime": "trending",
        "desc_template": "London NY session transition momentum for {symbol}.",
        "trigger": (
            "- Active during London close and NY continuation hours (15:00 to 16:00 UTC).\n"
            "- Long Trigger: Close > EMA 20, Close > Open, and RSI >= 52.\n"
            "- Short Trigger: Close < EMA 20, Close < Open, and RSI <= 48."
        ),
        "invalidation": (
            "- Invalidate if price reverses across EMA 20 prior to session close.\n"
            "- Invalidate if market volume dries up below 0.7x MA."
        ),
    },
    "aud_asia_tokyo_drift": {
        "title": "Asian Morning Session Institutional Trend Drift",
        "regime": "trending",
        "desc_template": "Asian session trend drift playbook for {symbol}.",
        "trigger": (
            "- Active during Tokyo liquidity build (02:00 to 04:00 UTC).\n"
            "- Long Trigger: Close > EMA 20, Close > Open, and volume >= 1.05x volume MA.\n"
            "- Short Trigger: Close < EMA 20, Close < Open, and volume >= 1.05x volume MA."
        ),
        "invalidation": (
            "- Invalidate if price crosses back across the 20-period EMA.\n"
            "- Invalidate if pre-London orderflow disrupts the trend."
        ),
    },
    "gbp_cable_breakout": {
        "title": "London Morning Opening Range Expansion Breakout",
        "regime": "breakout",
        "desc_template": "London morning cable range breakout for {symbol}.",
        "trigger": (
            "- Active during London market open (08:00 to 09:00 UTC).\n"
            "- Map preceding 6-hour pre-London high and low range.\n"
            "- Long Trigger: Close breaks above 6-hour high and Close > Open.\n"
            "- Short Trigger: Close breaks below 6-hour low and Close < Open."
        ),
        "invalidation": (
            "- Invalidate if price immediately re-enters pre-London range.\n"
            "- Invalidate if breakout bar prints rejection wick > 50% of range."
        ),
    },
    "ema_retest_macd": {
        "title": "EMA 21 Trend Retest with MACD Confluence",
        "regime": "trending",
        "desc_template": "EMA pullback with MACD confluence for {symbol}.",
        "trigger": (
            "- Long Trigger: Close > EMA 50, Low tests EMA 21, Close > EMA 21, MACD Hist > 0.\n"
            "- Short Trigger: Close < EMA 50, High tests EMA 21, Close < EMA 21, MACD Hist < 0."
        ),
        "invalidation": (
            "- Invalidate if candle body closes completely across EMA 50.\n"
            "- Invalidate if MACD histogram turns against trend direction."
        ),
    },
    "two_bar_thrust": {
        "title": "Two-Bar Consecutive Momentum Range Thrust",
        "regime": "trending",
        "desc_template": "Two-bar consecutive momentum thrust for {symbol}.",
        "trigger": (
            "- Two consecutive directional bars with bodies >= 0.5x 14-period ATR.\n"
            "- Long Trigger: Bar[i-1] and Bar[i] close higher, and Close breaks Bar[i-1] high.\n"
            "- Short Trigger: Bar[i-1] and Bar[i] close lower, and Close breaks Bar[i-1] low."
        ),
        "invalidation": (
            "- Invalidate if subsequent bar immediately retraces > 50% of thrust range.\n"
            "- Invalidate if volume contracts significantly on second bar."
        ),
    },
    "stoch_trend_pullback": {
        "title": "Stochastic Trend Retest & Dynamic Continuation",
        "regime": "trending",
        "desc_template": "Stochastic trend pullback playbook for {symbol}.",
        "trigger": (
            "- Long Trigger: Close > EMA 50, Stoch %K <= 32, turns above %D, Close > Open.\n"
            "- Short Trigger: Close < EMA 50, Stoch %K >= 68, turns below %D, Close < Open."
        ),
        "invalidation": (
            "- Invalidate if price breaks across EMA 50 before entry execution.\n"
            "- Invalidate if Stochastic indicator remains pinned at opposing extreme."
        ),
    },
    "asian_range_mean_revert": {
        "title": "Asian Session Outer Band Mean Reversion",
        "regime": "mean_reverting",
        "desc_template": "Asian session boundary range revert for {symbol}.",
        "trigger": (
            "- Active during low-volatility Asian hours (23:00 to 03:00 UTC).\n"
            "- Long Trigger: Close pierces below Lower Bollinger Band and closes bullish.\n"
            "- Short Trigger: Close pierces above Upper Bollinger Band and closes bearish."
        ),
        "invalidation": (
            "- Invalidate if Bollinger Bands expand sharply into volatility breakout.\n"
            "- Invalidate if held past European pre-market open (06:00 UTC)."
        ),
    },
    "aud_sydney_breakout": {
        "title": "Sydney Session Opening Liquidity Breakout",
        "regime": "breakout",
        "desc_template": "Sydney opening session range breakout for {symbol}.",
        "trigger": (
            "- Active during Sydney open hours (21:00 to 23:00 UTC).\n"
            "- Map preceding 4-hour consolidation high and low.\n"
            "- Long Trigger: Close breaks above 4-hour high and Close > Open.\n"
            "- Short Trigger: Close breaks below 4-hour low and Close < Open."
        ),
        "invalidation": (
            "- Invalidate if breakout candle fails to hold outside 4-hour range.\n"
            "- Invalidate if spread widens beyond asset risk limit."
        ),
    },
    "macd_zero_bounce": {
        "title": "MACD Zero-Line Trend Equilibrium Bounce",
        "regime": "trending",
        "desc_template": "MACD zero line trend bounce playbook for {symbol}.",
        "trigger": (
            "- Long Trigger: MACD Line > 0, tests zero line, MACD Hist > 0, Close > EMA 20.\n"
            "- Short Trigger: MACD Line < 0, tests zero line, MACD Hist < 0, Close < EMA 20."
        ),
        "invalidation": (
            "- Invalidate if MACD line crosses zero into opposing territory.\n"
            "- Invalidate if price breaks opposite the 20-period EMA."
        ),
    },
    "donchian12_breakout": {
        "title": "12-Period Donchian Dynamic Momentum Breakout",
        "regime": "breakout",
        "desc_template": "12-bar Donchian channel breakout for {symbol}.",
        "trigger": (
            "- Calculate 12-period Donchian Channel on H1 timeframe.\n"
            "- Long Trigger: Close breaks above 12-period high and Close > EMA 50.\n"
            "- Short Trigger: Close breaks below 12-period low and Close < EMA 50."
        ),
        "invalidation": (
            "- Invalidate if breakout bar prints rejection wick > 50% of candle range.\n"
            "- Invalidate if price re-enters channel midpoint."
        ),
    },
    "rsi_trend_zone_pullback": {
        "title": "RSI Equilibrium Zone Trend Pullback Continuation",
        "regime": "trending",
        "desc_template": "RSI trend continuation pullback for {symbol}.",
        "trigger": (
            "- Long Trigger: Close > EMA 50, RSI tests 40-48 zone, and closes bullish.\n"
            "- Short Trigger: Close < EMA 50, RSI tests 52-60 zone, and closes bearish."
        ),
        "invalidation": (
            "- Invalidate if RSI crosses opposite zone extreme (<35 or >65).\n"
            "- Invalidate if candle body closes across EMA 50."
        ),
    },
    "ema9_21_pullback": {
        "title": "Dual EMA 9/21 Dynamic Trend Pullback",
        "regime": "trending",
        "desc_template": "EMA 9/21 trend pullback playbook for {symbol}.",
        "trigger": (
            "- Long Trigger: EMA 9 > EMA 21, Low tests EMA 9, Close > EMA 9, bullish close.\n"
            "- Short Trigger: EMA 9 < EMA 21, High tests EMA 9, Close < EMA 9, bearish close."
        ),
        "invalidation": (
            "- Invalidate if candle body closes completely across EMA 21.\n"
            "- Invalidate if EMA 9 crosses back across EMA 21."
        ),
    },
}


def get_setup_metadata(setup_id: str, symbol: str) -> Dict[str, Any]:
    """Retrieves authoritative metadata or dynamically generates compliant specifications."""
    if setup_id in SETUP_DOCS:
        return dict(SETUP_DOCS[setup_id])

    sid_lower = setup_id.lower()

    if any(k in sid_lower for k in ("break", "breakout", "expansion")):
        regime = "breakout"
    elif any(
        k in sid_lower for k in ("fade", "range", "reversion", "revert", "dip", "exhaustion", "consec", "bb", "stoch")
    ):
        regime = "ranging"
    elif any(
        k in sid_lower for k in ("trend", "thrust", "surge", "bounce", "pb", "pullback", "momentum", "drift", "ema")
    ):
        regime = "trending"
    else:
        regime = "trending"

    words = setup_id.replace("_", " ").split()
    clean_words = []
    for w in words:
        if w.upper() in (
            "GBP",
            "USD",
            "EUR",
            "JPY",
            "AUD",
            "BTC",
            "XTI",
            "XBR",
            "EMA",
            "RSI",
            "BB",
            "VWAP",
            "MACD",
            "ATR",
            "NY",
        ):
            clean_words.append(w.upper())
        elif re.match(r"^w\d+$", w.lower()):
            clean_words.append(f"Window {w[1:]}")
        elif re.match(r"^dch\d+$", w.lower()):
            clean_words.append(f"Donchian {w[3:]}")
        elif re.match(r"^ema\d+$", w.lower()):
            clean_words.append(f"EMA {w[3:]}")
        elif re.match(r"^rsi\d+$", w.lower()):
            clean_words.append(f"RSI {w[3:]}")
        elif re.match(r"^stoch\d+$", w.lower()):
            clean_words.append(f"Stochastic {w[5:]}")
        else:
            clean_words.append(w.capitalize())
    title = f"{' '.join(clean_words)} Strategy"

    desc = f"Verified {regime} tactical execution playbook for {symbol.upper()}."
    if len(desc) > 80:
        desc = f"{symbol.upper()} {regime.capitalize()} institutional playbook."

    if regime == "ranging":
        trigger = (
            f"- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.\n"
            f"- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1."
        )
        invalidation = (
            "- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.\n"
            "- Invalidate if opposite structural momentum triggers before trade execution fill."
        )
    elif regime == "breakout":
        trigger = (
            f"- Long Trigger: Price expands above upper boundary with tick volume confirmation and bullish close.\n"
            f"- Short Trigger: Price expands below lower boundary with tick volume confirmation and bearish close."
        )
        invalidation = (
            "- Invalidate if breakout candle prints rejection wick > 50% of candle range.\n"
            "- Invalidate if price re-enters channel midpoint on subsequent bar."
        )
    else:
        trigger = (
            f"- Long Trigger: Price pulls back to dynamic EMA support while in higher-timeframe uptrend, printing bullish confirmation.\n"
            f"- Short Trigger: Price pulls back to dynamic EMA resistance while in higher-timeframe downtrend, printing bearish confirmation."
        )
        invalidation = (
            "- Invalidate if candle body closes across dynamic trend support by > 0.40x ATR.\n"
            "- Invalidate if trend filter reverses slope on subsequent H1 bar."
        )

    return {
        "title": title,
        "regime": regime,
        "desc_template": desc,
        "trigger": trigger,
        "invalidation": invalidation,
    }

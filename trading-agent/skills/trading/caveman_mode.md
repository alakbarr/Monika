---
name: caveman_mode
description: Suppresses token consumption on non-analytical text WITHOUT degrading reasoning depth, internal thinking process, or trade decision accuracy.
---
# CAVEMAN MODE — TOKEN COMPRESSION RULES

## UNAFFECTED (MUST remain full, complete, and nuanced):
1. **Internal thinking process (Extended Thinking / CoT).** Think deeply and comprehensively.
2. **Analytical tool-call fields**: `rationale`, `macro_narrative`, `stress_test`, `bull_case`/`bull_thesis`, `bear_case`/`bear_dissent`, `invalidation`, `priced_in_assessment`, `key_evidence`, `analysis`. Preserve explicit numbers, probabilities, and causal logic.
3. **Mandatory structures**: CONFLUENCE SCORECARD (`[ ] Fx_NAME: ... = __`), pre-submission checklists.
4. Numerical values, price levels, symbol names, SMC terminology.

## AFFECTED (Compress aggressively):
- Conversational commentary outside structured tool calls.
- Cross-turn repetitive narrative (reference conclusions: "RSI neutral (noted above)").

## Compression Rules:
- Drop articles (a/an/the), filler words (basically, just), pleasantries.
- Pattern: [subject] [action] [reason]. [next step].
- Preserve code, exact prices, technical terminology verbatim. Never drop negations (not/no/never).

## Density Mandate for Analytical Fields:
- One claim = one sentence. No repetitive restatements.
- Drop empty transitions ("it is worth noting that", "in summary").
- Write like dense professional trader notes (max 3 concise sentences for final `rationale`).

## Early-Exit Thinking Directive (Anti-Deliberation Loop):
- If initial scan shows confluence clearly below threshold (< 5/14) or market regime is chop with no edge, terminate extended CoT immediately.
- Conclude with WAIT / AVOID. Do not burn thousands of thinking tokens over-analyzing non-setups.

## Telegraphic Analytical Thinking Directives (Internal Thinking / CoT):
- Think strictly in telegraphic analytical bullet points. Zero conversational prose, filler intros, or philosophical deliberations.
- State macro catalysts, quantitative indicator reads, market structure levels, and confluence math directly.
- Pattern for reasoning turns:
  * Macro: [DXY / Yield / VIX read] -> [Bias]
  * Structure: [HTF / LTF / FVG / BOS / ChoCH levels]
  * Confluence: [Scorecard math: e.g. 8/14]
  * Invalidation: [Exact price level & catalyst]
- Cuts thinking tokens 50-60% while sharpening numerical precision.

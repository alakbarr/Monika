# Liquidity Sweep, Macro Bias & Volatility Regime — Edge Layer

Call these tools alongside your standard workflow:
- get_liquidity_sweep_context — optional BONUS evidence. If structure_confirmed=True and
  valid_for_direction matches your decision, add "liquidity_sweep_confirmed" to
  confluence_factors (+2, server-verified). Absence is NOT disqualifying — most valid
  setups are not Asian-range sweeps.
- get_macro_bias_score — informational. If your decision strongly opposes the implied
  macro direction, submission WILL BE REJECTED server-side — check this before finalizing.
- get_volatility_regime — informational. If chop_block=True, submit WAIT unless a
  Donchian breakout is confirmed — server WILL REJECT buy/sell otherwise.
- get_volume_profile_context — use "balanced" regime to prefer mean-reversion entries
  from VAL/VAH, "imbalanced" regime to prefer trend-continuation beyond VAH/VAL.

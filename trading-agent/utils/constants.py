# Exit reasons yang dianggap sebagai "market outcome" (bukan admin action)
MARKET_OUTCOME_EXIT_REASONS = ['sl_hit', 'tp_hit', 'trailing_sl', 'breakeven_sl', 'partial_tp']

# Exit reasons yang tidak dihitung dalam win rate
NON_MARKET_EXIT_REASONS = ['expired_limit', 'max_holding_time', 'rejected_by_admin']

# Magic number untuk MT5 orders dari AI Trading Agent
AI_MAGIC_NUMBER = 20250101
CLAUDE_MAGIC_NUMBER = AI_MAGIC_NUMBER  # Backward-compatible alias

# Default timeframes untuk analysis
ANALYSIS_TIMEFRAMES = ['H1', 'H4', 'D1']

H4_DATA_MAX_AGE_HOURS = 8.0
D1_DATA_MAX_AGE_HOURS = 32.0

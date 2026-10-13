# ==============================================================================
# File: application/analysis/tools/definitions/trading.py
# ==============================================================================

"""
Trading execution, fundamental brief, asset analysis, position, and risk tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.schemas.schemas import (
    SubmitAssetAnalysisSchema,
    SubmitFundamentalBriefSchema,
    get_tool_schema,
)
from monika.application.analysis.tools.definitions.base import _tool

_fundamental_brief_schema = get_tool_schema(SubmitFundamentalBriefSchema)


_asset_analysis_schema = get_tool_schema(SubmitAssetAnalysisSchema)


SUBMIT_FUNDAMENTAL_BRIEF = _tool(
    name="submit_fundamental_brief",
    description=(
        "Submit your completed fundamental analysis brief. "
        "Call this ONCE after you have gathered all necessary data and formed your analysis. "
        "This saves the structured brief to the database for use in the per-asset analysis stage. "
        "WAJIB mengisi field 'priced_in_assessment' secara komprehensif, jangan pernah dibiarkan kosong. "
        "Do NOT submit until you are confident in your analysis."
    ),
    properties=_fundamental_brief_schema["properties"],
    required=[
        r
        for r in _fundamental_brief_schema.get("required", [])
        if r
        in {
            "macro_narrative",
            "currency_bias",
            "macro_regime",
            "risk_sentiment",
            "confidence",
            "priced_in_assessment",
            "strongest_counter_thesis",
        }
    ],
)


GET_FUNDAMENTAL_BRIEF = _tool(
    name="get_fundamental_brief",
    description=(
        "Fetch the most recent fundamental brief generated in Stage 1 analysis. "
        "This gives you the macro context (currency biases, risk sentiment, key risks) "
        "to inform your per-asset technical analysis."
    ),
    properties={},
    required=[],
)


SUBMIT_ASSET_ANALYSIS = _tool(
    name="submit_asset_analysis",
    description=(
        "Submit your completed per-asset analysis decision. "
        "Call this ONCE per asset after you have reviewed all relevant data. "
        "IMPORTANT RULES:\n"
        "- If decision is 'buy' or 'sell': calculate_position_size MUST be called first to register verified sizing evidence in the ledger. entry_condition, stop_loss, take_profit, confluence_score, priced_in_score, invalidation_price, AND invalidation_direction ('above' or 'below') are REQUIRED. R:R must be >= 1.3.\n"
        "- confluence_factors: only use exact active IDs: 'fundamental_bias', 'dxy_confirms', 'd1_trend', 'rsi_neutral', 'near_fvg', 'near_order_block', 'in_ote_zone', 'near_sr_zone', 'cot_aligned', 'vix_ok', 'liquidity_sweep_confirmed', 'session_prime', 'microstructure_ok', 'historical_pattern_consensus'.\n"
        "- If SSVP warning or macro divergence active: rationale MUST explicitly state 'I trust price action because...' or 'I trust the brief because...'.\n"
        "- If specialists disagree on direction: 'specialist_adjudication' is REQUIRED.\n"
        "- If decision is 'wait': reevaluation_trigger is required (auto-defaults to 4h time review if omitted).\n"
        "- If decision is 'avoid': only rationale is required.\n"
        "The backend will validate these rules and reject incomplete submissions."
    ),
    properties=_asset_analysis_schema["properties"],
    required=_asset_analysis_schema.get("required", []),
)


GET_ASSET_ANALYSIS = _tool(
    name="get_asset_analysis",
    description="Fetch the most recent analysis decision for a specific asset or all assets.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: specific symbol (e.g. 'XAUUSD'). Leave empty to get all assets.",
        },
        "limit": {"type": "integer", "description": "Max number of analyses to return. Default: 5."},
    },
    required=[],
)


GET_ACCOUNT_INFO = _tool(
    name="get_account_info",
    description="Fetch current account information: balance, equity, margin, free margin, and floating PnL (for live MT5 and/or simulated paper account).",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Account mode to inspect: 'live' for MT5 account, 'paper' for simulated paper trading portfolio ($10k baseline), 'all' for both. Default: 'all'.",
        },
    },
    required=[],
)


GET_OPEN_POSITIONS = _tool(
    name="get_open_positions",
    description="Fetch currently open trading positions (paper trades and/or live MT5 positions) with real-time floating PnL.",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by mode: 'paper' for paper trading simulation, 'live' for MT5 live positions, 'all' for both. Default: 'all'.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'XAUUSD'). Leave empty for all open positions.",
        },
    },
    required=[],
)


GET_PENDING_ORDERS = _tool(
    name="get_pending_orders",
    description="Fetch active pending limit/stop orders from MT5 broker terminal with tickets, order types, prices, SL/TP, and volume.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD', 'XAUUSD'). Leave empty for all pending orders.",
        },
    },
    required=[],
)


GET_PORTFOLIO_EXPOSURE = _tool(
    name="get_portfolio_exposure",
    description="Fetch portfolio-wide exposure metrics: gross/net lots, long vs short distribution, per-symbol breakdown, and aggregate unrealized PnL.",
    properties={
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by trading mode: 'paper', 'live', or 'all'. Default: 'all'.",
        },
    },
    required=[],
)


GET_SWAP_RATES = _tool(
    name="get_swap_rates",
    description="Fetch overnight rollover swap rates (long and short) for trading symbols, including Wednesday 3x rollover info.",
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: trading symbol (e.g. 'XAUUSD', 'EURUSD'). If omitted, returns all tracked symbol swap rates.",
        },
    },
    required=[],
)


RUN_MONTE_CARLO_SIMULATION = _tool(
    name="run_monte_carlo_simulation",
    description="Run institutional Monte Carlo simulation (bootstrap / permutation) on closed trade returns to calculate VaR 95% Drawdown, Probability of Ruin, and final equity distributions.",
    properties={
        "num_simulations": {
            "type": "integer",
            "description": "Number of simulation iterations (default: 1000).",
        },
        "mode": {
            "type": "string",
            "enum": ["permutation", "bootstrap", "block_bootstrap"],
            "description": "Simulation mode (default: 'permutation').",
        },
        "initial_equity": {
            "type": "number",
            "description": "Initial account equity for simulation baseline (default: 10000.0).",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter simulation trades by symbol.",
        },
    },
    required=[],
)


GET_PAPER_TRADING_PERFORMANCE = _tool(
    name="get_paper_trading_performance",
    description=(
        "Fetch comprehensive trading performance metrics and PnL statistics. "
        "Returns: total_trades, wins, losses, win_rate_pct, total_pnl, profit_factor, avg_pnl, "
        "expectancy_per_trade_R, has_positive_edge, by_symbol breakdown, and trade history."
    ),
    properties={
        "mode": {
            "type": "string",
            "enum": ["paper", "live", "all"],
            "description": "Trading performance mode: 'paper' for simulated tracker, 'live' for MT5 broker positions, or 'all'. Default: 'paper'.",
        },
        "days_back": {
            "type": "integer",
            "description": "Optional: number of days back to calculate statistics (e.g. 7 for past week, 30 for past month). Leave empty for all-time.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD', 'XAUUSD').",
        },
    },
    required=[],
)


GET_TRADE_HISTORY = _tool(
    name="get_trade_history",
    description=(
        "Fetch history of executed trades (closed and open, paper and live). "
        "Returns list of trade records with symbol, direction, entry_price, exit_price, SL, TP, "
        "pnl_pct, exit_reason (tp_hit, sl_hit, manual), holding_hours, and timestamps."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'XAUUSD'). Leave empty for all.",
        },
        "status": {
            "type": "string",
            "enum": ["all", "open", "closed"],
            "description": "Filter by trade status. Default: 'closed'.",
        },
        "mode": {
            "type": "string",
            "enum": ["all", "live", "paper"],
            "description": "Filter by mode: 'paper' for dry-run simulation, 'live' for MT5, 'all' for both. Default: 'all'.",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of records to return. Default: 10, max: 50.",
        },
        "days_back": {
            "type": "integer",
            "description": "Optional: filter trades closed within last N days.",
        },
    },
    required=[],
)


GET_ACTIVE_TRIGGERS = _tool(
    name="get_active_triggers",
    description=(
        "Fetch active and pending trade triggers and re-evaluation conditions. "
        "Returns trigger_type (price_level, time, event), condition details, target symbol, "
        "current market price, and distance to trigger level."
    ),
    properties={
        "symbol": {
            "type": "string",
            "description": "Optional: filter by symbol (e.g. 'EURUSD'). Leave empty for all.",
        },
        "status": {
            "type": "string",
            "enum": ["pending", "triggered", "cancelled", "all"],
            "description": "Filter by trigger status. Default: 'pending'.",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of triggers to return. Default: 10.",
        },
    },
    required=[],
)


GET_EDGE_TRACKER_STATUS = _tool(
    name="get_edge_tracker_status",
    description=(
        "Fetch statistical edge evaluation, Z-score, confidence intervals, and win rates by confluence factor."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Period to evaluate statistical edge. Default: 30 days.",
        },
    },
    required=[],
)


GET_CALIBRATION_STATUS = _tool(
    name="get_calibration_status",
    description=(
        "Fetch active system calibration directives: news impact directives, currency confidence ceilings, "
        "SSVP CDS thresholds, and specialist (technical/macro/sentiment) trust weights."
    ),
    properties={},
    required=[],
)


GET_TRADE_DETAILS = _tool(
    name="get_trade_details",
    description=(
        "Fetch deep trade autopsy and context for a specific trade: original analysis rationale, "
        "confluence factors, specialist debate transcript, execution data, exit outcome, and reflection."
    ),
    properties={
        "trade_id": {
            "type": "integer",
            "description": "PaperTradeRecord ID or Position ID.",
        },
        "analysis_id": {
            "type": "integer",
            "description": "AssetAnalysis ID.",
        },
        "ticket": {
            "type": "integer",
            "description": "MT5 ticket number.",
        },
    },
    required=[],
)


GET_RISK_STATE = _tool(
    name="get_risk_state",
    description="Fetch current risk state: daily PnL, current drawdown, whether trading is paused, and reason.",
    properties={},
    required=[],
)


PROPOSE_ACTION = _tool(
    name="propose_action",
    description=(
        "Propose an action that requires human confirmation before execution. "
        "This sends a Telegram message with inline Yes/Cancel buttons. "
        "Use for: closing a live/paper position, partial close and breakeven, placing orders, bulk breakeven, trailing stops, pausing/resuming trading, modifying SL/TP, cancelling pending MT5 orders, cancelling pending triggers, terminal commands, GUI automation, or proposing database mutations."
    ),
    properties={
        "action_type": {
            "type": "string",
            "enum": [
                "place_order",
                "close_position",
                "close_all_positions",
                "close_paper_trade",
                "pause_trading",
                "resume_trading",
                "modify_sl_tp",
                "modify_paper_sl_tp",
                "cancel_order",
                "cancel_trigger",
                "save_market_intelligence",
                "db_mutation",
                "bulk_breakeven",
                "secure_positions",
                "set_trailing_stop",
                "cancel_stale_pending_orders",
                "update_config",
                "update_user_preference",
                "execute_terminal_command",
                "desktop_gui_action",
                "partial_close_and_breakeven",
            ],
            "description": "Type of action to propose.",
        },
        "params": {
            "type": "object",
            "description": "Action parameters. For place_order: {symbol, direction: 'buy'|'sell', order_type: 'market'|'limit', entry_price, stop_loss, take_profit, rationale}. For close_position: {ticket, volume (optional float for partial close)}. For partial_close_and_breakeven: {ticket, volume: float, reason}. For bulk_breakeven/secure_positions: {symbol (optional), only_profit: bool}. For set_trailing_stop: {symbol (optional), trailing_pips: float}. For close_all_positions: {reason (optional)}. For close_paper_trade: {paper_trade_id or symbol, volume (optional)}. For modify_sl_tp/modify_paper_sl_tp: {ticket or paper_trade_id, sl, tp}. For cancel_order: {ticket (integer MT5 order ticket), symbol (optional)}. For cancel_trigger: {trigger_id}. For save_market_intelligence: {title, summary, intel_type, affected_symbols, directive, target_cycle}. For db_mutation: {table_name: str, operation: 'insert'|'update'|'delete', target_id: Optional[str|int], data: Optional[dict], reason: str}. For execute_terminal_command: {command: str}. For desktop_gui_action: {action: 'screenshot'|'left_click'|'type_text'|'key_press', coordinate, text, key}.",
        },
        "reason": {
            "type": "string",
            "description": "Explanation for why you are proposing this action.",
        },
    },
    required=["action_type", "params", "reason"],
)


CALCULATE_POSITION_SIZE = _tool(
    name="calculate_position_size",
    description=(
        "Deterministic position sizing calculator. Given symbol, entry, stop_loss, direction, and risk percentage, "
        "calculates verified mathematical lot sizing, risk in USD, and pip distance based on Stop Loss. "
        "MANDATORY: LLM must use this tool and NOT calculate lot sizes manually."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'EURUSD', 'XAUUSD')"},
        "entry_price": {"type": "number", "description": "Proposed entry price"},
        "stop_loss": {"type": "number", "description": "Proposed stop loss price"},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Trade direction (optional)"},
        "risk_pct": {"type": "number", "description": "Account risk percentage (default: 1.0%)"},
        "account_equity": {
            "type": "number",
            "description": "Custom account equity / capital in USD (optional, defaults to live broker equity or paper balance)",
        },
    },
    required=["symbol", "entry_price", "stop_loss"],
)


TRANSITION_PHASE = _tool(
    name="transition_analysis_phase",
    description=(
        "Transitions agent execution to the next analytical phase (Phase 1: Recon -> "
        "Phase 2: Structure & Confluence -> Phase 3: Sizing & Submission)."
    ),
    properties={
        "target_phase": {
            "type": "integer",
            "enum": [1, 2, 3],
            "description": "Target phase number to unlock corresponding tools",
        },
        "rationale": {"type": "string", "description": "Reason for advancing phase"},
    },
    required=["target_phase"],
)


CALCULATE_MARGIN = _tool(
    name="calculate_margin",
    description=(
        "Calculates exact broker margin requirement in USD for a specified lot size and symbol. "
        "Accounts for leverage, broker contract size, and current market price."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'XAUUSD', 'EURUSD')"},
        "lot_size": {"type": "number", "description": "Lot size volume (e.g. 0.5, 1.0)"},
        "action": {"type": "string", "enum": ["buy", "sell"], "description": "Trade action (default 'buy')"},
        "price": {"type": "number", "description": "Current price (optional)"},
    },
    required=["symbol", "lot_size"],
)


CREATE_PRICE_ALERT = _tool(
    name="create_price_alert",
    description=(
        "Creates an ad-hoc price alert trigger that notifies the operator via Telegram when market price "
        "crosses a specific level (break above / break below)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading instrument (e.g. 'EURUSD', 'XAUUSD')"},
        "price_level": {"type": "number", "description": "Price level target to trigger alert"},
        "condition": {
            "type": "string",
            "enum": ["above", "below"],
            "description": "Trigger when price goes above or below level",
        },
        "note": {"type": "string", "description": "Optional memo or description for the alert"},
    },
    required=["symbol", "price_level", "condition"],
)


RUN_TRADE_COUNTERFACTUAL = _tool(
    name="run_trade_counterfactual",
    description=(
        "Run a counterfactual replay on a specific historical trade setup or ticket to evaluate what would have happened "
        "if stop loss or take profit were wider/narrower (e.g. SL +10 pips). "
        "Use when user asks 'what if SL was wider', 'counterfactual analysis for trade #X', or post-trade what-if scenarios."
    ),
    properties={
        "trade_id": {
            "type": "integer",
            "description": "Ticket ID or Database ID of the trade/position to replay.",
        },
        "sl_pips_delta": {
            "type": "number",
            "description": "Additional pips added to Stop Loss distance (positive means wider SL, e.g. 10.0 for 10 pips wider). Default: 0.0.",
        },
        "tp_pips_delta": {
            "type": "number",
            "description": "Additional pips added to Take Profit distance (positive means wider TP, e.g. 20.0). Default: 0.0.",
        },
    },
    required=["trade_id"],
)


QUERY_SIGNAL_PERFORMANCE = _tool(
    name="query_signal_performance",
    description=(
        "Query trade signals joined with execution outcomes with flexible filters. "
        "Allows finding signals by confidence threshold (e.g. confidence > 0.8), outcome ('win'/'loss'), symbol, and time range."
    ),
    properties={
        "min_confidence": {"type": "number", "description": "Minimum AI signal confidence (0.0 - 1.0). Default: 0.0."},
        "max_confidence": {"type": "number", "description": "Maximum AI signal confidence. Default: 1.0."},
        "outcome": {
            "type": "string",
            "enum": ["all", "win", "loss"],
            "description": "Filter by outcome: 'win' (positive pnl), 'loss' (negative pnl), or 'all'.",
        },
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."},
        "days_back": {"type": "integer", "description": "Lookback window in days (default: 30)."},
        "limit": {"type": "integer", "description": "Maximum records to return (default: 20)."},
    },
    required=[],
)


GET_LATEST_RISK_VERDICT = _tool(
    name="get_latest_risk_verdict",
    description=(
        "Retrieve recent RiskGate trade rejection reasons, failed check criteria, and risk audit logs for a symbol or account."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'XAUUSD', 'EURUSD')."},
    },
    required=[],
)


SET_TRAILING_STOP = _tool(
    name="set_trailing_stop",
    description=(
        "Set or update trailing stop and breakeven configurations for active positions (either by ticket, symbol, or all profitable positions)."
    ),
    properties={
        "ticket": {"type": "integer", "description": "Optional MT5 ticket number for specific position."},
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."},
        "trailing_pips": {"type": "number", "description": "Static trailing stop distance in pips (e.g. 20.0)."},
        "breakeven_pips": {
            "type": "number",
            "description": "Profit threshold in pips to move SL to breakeven (e.g. 15.0).",
        },
        "trail_atr_multiple": {"type": "number", "description": "Dynamic ATR multiple for trailing stop (e.g. 1.5)."},
        "only_profit": {
            "type": "boolean",
            "description": "If true, applies only to currently profitable positions (default: false).",
        },
        "disabled": {"type": "boolean", "description": "Set true to disable trailing stop on target positions."},
    },
    required=[],
)


CANCEL_STALE_PENDING_ORDERS = _tool(
    name="cancel_stale_pending_orders",
    description="Cancel resting MT5 pending orders older than max_age_hours.",
    properties={
        "max_age_hours": {
            "type": "number",
            "description": "Cancel pending orders older than this age in hours (default: 4.0).",
        },
    },
    required=[],
)


CLOSE_POSITIONS_BATCH = _tool(
    name="close_positions_batch",
    description="Close open positions filtered by profit, loss, or all without triggering emergency daemon pause.",
    properties={
        "filter_type": {
            "type": "string",
            "enum": ["profit_only", "loss_only", "all"],
            "description": "Filter criteria for closing positions.",
        },
        "reason": {"type": "string", "description": "Reason for batch closing positions."},
    },
    required=["filter_type"],
)


GET_BROKER_EXPENSES_SUMMARY = _tool(
    name="get_broker_expenses_summary",
    description="Aggregates broker expenses (commissions, overnight swap fees, and account financing charges) over a time window.",
    properties={
        "days": {"type": "integer", "description": "Lookback window in days (default 30)."},
        "symbol": {"type": "string", "description": "Optional symbol filter (e.g. 'EURUSD')."},
    },
    required=[],
)


GET_ACTIVE_NEGATIVE_CONSTRAINTS = _tool(
    name="get_active_negative_constraints",
    description="List active negative constraints ('DO NOT' rules) derived from past trade reflections to prevent recurring errors.",
    properties={"symbol": {"type": "string", "description": "Optional symbol to filter constraints (e.g. 'EURUSD')."}},
    required=[],
)


CALCULATE_CONFLUENCE_TOOL = _tool(
    name="calculate_confluence",
    description="Calculates multi-layer analytical confluence score (0.0 to 1.0) and technical alignment across HTF/LTF, market regime, order blocks, and momentum.",
    properties={
        "symbol": {"type": "string", "description": "Trading pair or instrument (e.g. 'EURUSD', 'XAUUSD')."},
        "direction": {"type": "string", "enum": ["buy", "sell"], "description": "Trade setup direction to evaluate."},
    },
    required=["symbol", "direction"],
)


GET_SLIPPAGE_SUMMARY_TOOL = _tool(
    name="get_slippage_summary",
    description="Retrieve execution slippage telemetry, average positive/negative slippage, and execution drift statistics across broker fills.",
    properties={
        "symbol": {"type": "string", "description": "Optional symbol filter."},
        "days_back": {"type": "integer", "description": "Lookback window in days (default: 30)."},
    },
    required=[],
)


SIMULATE_PORTFOLIO_DRAWDOWN_TOOL = _tool(
    name="simulate_portfolio_drawdown",
    description="Simulate combined margin, SL loss in USD, and correlated portfolio heat for hypothetical simultaneous positions (Q099).",
    properties={
        "positions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "direction": {"type": "string", "enum": ["buy", "sell"]},
                    "lots": {"type": "number"},
                    "entry": {"type": "number"},
                    "sl": {"type": "number"},
                },
                "required": ["symbol", "direction", "lots"],
            },
            "description": "List of hypothetical positions to evaluate simultaneously.",
        }
    },
    required=["positions"],
)


CALCULATE_KELLY_CRITERION_TOOL = _tool(
    name="calculate_kelly_criterion",
    description="Calculates Full Kelly, Half Kelly fraction, and risk sizing from closed trade win rate and payoff ratio (Q100).",
    properties={
        "symbol": {"type": "string", "description": "Optional symbol filter."},
        "horizon": {
            "type": "string",
            "enum": ["all_time", "90d", "30d"],
            "description": "Lookback horizon (default: 'all_time').",
        },
    },
    required=[],
)


GET_CARRY_TRADE_RANKINGS_TOOL = _tool(
    name="get_carry_trade_rankings",
    description="Calculate risk-adjusted carry trade attractiveness (Rate Spread / Realized Volatility) across currency pairs (Q074).",
    properties={
        "min_spread": {"type": "number", "description": "Minimum nominal rate spread in percent (default: 0.5)."}
    },
    required=[],
)


__all__ = [
    "_fundamental_brief_schema",
    "_asset_analysis_schema",
    "SUBMIT_FUNDAMENTAL_BRIEF",
    "GET_FUNDAMENTAL_BRIEF",
    "SUBMIT_ASSET_ANALYSIS",
    "GET_ASSET_ANALYSIS",
    "GET_ACCOUNT_INFO",
    "GET_OPEN_POSITIONS",
    "GET_PENDING_ORDERS",
    "GET_PORTFOLIO_EXPOSURE",
    "GET_SWAP_RATES",
    "RUN_MONTE_CARLO_SIMULATION",
    "GET_PAPER_TRADING_PERFORMANCE",
    "GET_TRADE_HISTORY",
    "GET_ACTIVE_TRIGGERS",
    "GET_EDGE_TRACKER_STATUS",
    "GET_CALIBRATION_STATUS",
    "GET_TRADE_DETAILS",
    "GET_RISK_STATE",
    "PROPOSE_ACTION",
    "CALCULATE_POSITION_SIZE",
    "TRANSITION_PHASE",
    "CALCULATE_MARGIN",
    "CREATE_PRICE_ALERT",
    "RUN_TRADE_COUNTERFACTUAL",
    "QUERY_SIGNAL_PERFORMANCE",
    "GET_LATEST_RISK_VERDICT",
    "SET_TRAILING_STOP",
    "CANCEL_STALE_PENDING_ORDERS",
    "CLOSE_POSITIONS_BATCH",
    "GET_BROKER_EXPENSES_SUMMARY",
    "GET_ACTIVE_NEGATIVE_CONSTRAINTS",
    "CALCULATE_CONFLUENCE_TOOL",
    "GET_SLIPPAGE_SUMMARY_TOOL",
    "SIMULATE_PORTFOLIO_DRAWDOWN_TOOL",
    "CALCULATE_KELLY_CRITERION_TOOL",
    "GET_CARRY_TRADE_RANKINGS_TOOL",
]

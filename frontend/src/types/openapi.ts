/* eslint-disable */
/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY.
 * Generated from FastAPI OpenAPI schema via scripts/generate_openapi_types.py
 */

export interface ActionStatusResponse {
  /** Optional extra execution details */
  details?: Record<string, unknown> | null;
  /** Descriptive outcome message */
  message?: string;
  /** Action outcome: ok, success, error, or killed */
  status: string;
}

export interface AuthRoleResponse {
  authenticated?: boolean;
  is_localhost?: boolean;
  /** Active RBAC role */
  role?: string;
  username?: string | null;
}

export interface BacktestRunRequest {
  /** Lookback days */
  days?: number;
  /** Initial account equity */
  initial_equity?: number;
  /** Backtest mode: full, replay, walk_forward */
  mode?: string;
  /** Step hours */
  step_hours?: number;
}

export interface BatchCloseRequest {
  /** 'all', 'profit_only', or 'loss_only' */
  filter_type?: string;
  reason?: string;
  /** Optional symbol filter */
  symbol?: string | null;
  /** Specific MT5 position tickets to close */
  tickets?: number[];
}

export interface BenchmarkRunRequest {
  /** Test router matrix (direct vs OpenRouter vs 9router) */
  compare_routers?: boolean | null;
  /** Async job concurrency */
  concurrency?: number | null;
  /** Judge model name */
  judge_model?: string | null;
  /** Judge ensemble model names */
  judge_models?: string[] | null;
  /** Subset model names/IDs to evaluate */
  models?: string[] | null;
  /** Provider router/prefix: direct, openrouter, 9router, groq, gemini, etc. */
  provider_route?: string | null;
  /** Upstream reference model */
  reference_model?: string | null;
  /** Asset symbols for per-asset analysis */
  symbols?: string[] | null;
  /** Single task role ID to evaluate */
  task_id?: string | null;
  /** Subset task IDs to evaluate */
  tasks?: string[] | null;
  /** Tier filter: system_one, cheap_efficient, cheap_smart, high_intelligence */
  tier?: string | null;
  /** Use synthetic September 2026 market fixtures */
  use_fixtures?: boolean | null;
}

export interface BulkBreakevenRequest {
  /** Only move positions currently in profit to breakeven */
  only_profit?: boolean;
  /** Optional symbol filter, e.g. EURUSD */
  symbol?: string | null;
}

export interface ChatCompletionRequest {
  max_tokens?: number | null;
  messages: ChatMessage[];
  model?: string;
  stream?: boolean | null;
  temperature?: number | null;
  tools?: Record<string, unknown>[] | null;
  top_p?: number | null;
}

export interface ChatMessage {
  content: unknown;
  role: string;
}

export interface ClosePositionRequest {
  /** PaperTradeRecord ID */
  paper_trade_id?: number | null;
  /** Percentage of position to close (1-100) */
  percentage?: number | null;
  /** Database Position record ID */
  position_id?: number | null;
  /** Closure reason */
  reason?: string;
  /** Currency symbol */
  symbol?: string | null;
  /** MT5 deal/order ticket number */
  ticket?: number | null;
  /** Partial volume/lots to close */
  volume?: number | null;
}

export interface ConfigUpdateRequest {
  /** Reason for activity audit log */
  reason?: string | null;
  /** Full settings dictionary to validate and persist */
  settings: Record<string, unknown>;
}

export interface CrystallizeSkillRequest {
  /** Optional symbol filter, e.g. EURUSD */
  symbol?: string | null;
}

export interface DeprecateSkillRequest {
  /** Reason for deprecating skill */
  reason?: string | null;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface HarnessCycleRequest {
  /** Market domain or regime */
  domain?: string | null;
  /** Number of candidate proposals */
  k_candidates?: number;
}

export interface HealthDiagnostics {
  active_tasks?: number;
  active_threads?: number;
  disk_usage_gb?: number | null;
  memory_usage_mb?: number | null;
  python_version?: string;
}

export interface HealthStatusResponse {
  db_connected?: boolean;
  diagnostics?: HealthDiagnostics | null;
  gemini_api_available?: boolean;
  heartbeat_age_seconds?: number | null;
  last_analysis_cycle?: string | null;
  last_scraper_run?: string | null;
  mt5_connected?: boolean;
  status?: string;
  timestamp?: string;
  uptime_seconds?: number;
}

export interface ManualOrderPreviewRequest {
  /** 'buy' or 'sell' */
  direction?: string;
  /** Entry price (or current market price) */
  entry_price?: number | null;
  /** Fixed lots override */
  fixed_lots?: number | null;
  /** Alias for entry_price */
  price?: number | null;
  /** Risk percentage override */
  risk_percent?: number | null;
  /** Stop loss price */
  sl?: number | null;
  /** Trading instrument symbol */
  symbol: string;
  /** Take profit price */
  tp?: number | null;
  /** Alias for fixed_lots */
  volume?: number | null;
}

export interface ManualOrderSubmitRequest {
  /** Order comment */
  comment?: string;
  /** 'buy' or 'sell' */
  direction?: string;
  /** Explicit paper trading toggle */
  is_paper?: boolean | null;
  /** Order volume in lots */
  lots?: number | null;
  /** 'buy', 'sell', 'buy_limit', 'sell_limit', 'buy_stop', 'sell_stop' */
  order_type?: string;
  /** Order execution/limit/stop price */
  price?: number | null;
  /** Stop loss price */
  sl?: number | null;
  symbol: string;
  /** Take profit price */
  tp?: number | null;
  /** Order volume alias */
  volume?: number | null;
}

export interface MemorySearchRequest {
  limit?: number;
  /** Keyword or phrase to search across reflections and lessons */
  query: string;
  symbol?: string | null;
}

export interface ModifyPositionRequest {
  /** Audit note or comment */
  comment?: string | null;
  /** New stop loss price */
  sl?: number | null;
  /** New take profit price */
  tp?: number | null;
}

export interface OverrideRiskRequest {
  auto_execute?: boolean | null;
  /** Arbitrary additional risk parameters */
  custom_overrides?: Record<string, unknown> | null;
  /** TTL duration in seconds before override reverts */
  duration_seconds?: number | null;
  /** ISO timestamp when override expires */
  expires_at?: string | null;
  /** Max open concurrent positions */
  max_concurrent_positions?: number | null;
  /** Max daily drawdown limit in % (e.g. 0.5 - 20.0) */
  max_daily_drawdown_percent?: number | null;
  /** Max lot size per symbol */
  max_lot_per_symbol?: number | null;
  max_risk_amount_usd?: number | null;
  /** Max weekly drawdown limit in % */
  max_weekly_drawdown_percent?: number | null;
  /** Audit reason for risk override */
  reason?: string | null;
  /** Risk percent per trade (e.g. 0.1 - 5.0) */
  risk_percent_per_trade?: number | null;
  system_paused?: boolean | null;
}

export interface PingResponse {
  status?: string;
  timestamp?: string;
}

export interface PlaybookRollbackRequest {
  reason?: string | null;
  target_hash?: string | null;
}

export interface PluginInstallRequest {
  /** Pip package name, GitHub URL, or .whl path */
  package_name: string;
}

export interface PluginToggleRequest {
  /** Plugin category (e.g. analysis_pipeline, broker, scheduler) */
  category?: string;
  /** Desired activation state */
  enabled: boolean;
  /** Unique ID of the plugin to toggle */
  plugin_id: string;
}

export interface PluginUninstallRequest {
  /** Package name to uninstall via pip */
  package_name: string;
}

export interface SteerRequest {
  /** Steering instruction or tactical directive for analysis cycle */
  message: string;
  /** Delivery mode ('steer' or 'follow_up') */
  mode?: string | null;
  /** Optional target symbols affected */
  symbols?: string[] | null;
}

export interface TrailingOverrideRequest {
  /** Trailing stop ATR multiplier (e.g. 1.5) */
  atr_multiplier?: number | null;
  /** ATR multiple to trigger BE */
  breakeven_atr_multiple?: number | null;
  /** Fixed profit in pips to trigger BE */
  breakeven_pips?: number | null;
  /** Enable or disable trailing stop */
  enabled?: boolean;
  /** Reset trailing stop to system defaults */
  reset_to_default?: boolean;
  /** Alias for atr_multiplier */
  trail_atr_multiple?: number | null;
  /** Fixed trailing distance in pips */
  trailing_pips?: number | null;
}

export interface TriggerCycleRequest {
  /** Ad-hoc context or specific hypothesis to analyze */
  context?: string | null;
  /** Force execution even if scheduled time hasn't arrived */
  forced?: boolean;
  /** Reason for triggering cycle */
  reason?: string;
  /** Optional target symbol for ad-hoc analysis */
  symbol?: string | null;
}

export interface ValidationError {
  ctx?: Record<string, unknown>;
  input?: unknown;
  loc: string | number[];
  msg: string;
  type: string;
}

/** Registered API Routes and Methods */
export interface ApiEndpoints {
  'POST /api/v1/actions/approve-trade/{trade_id}': {
    summary: 'Action Approve Trade';
  };
  'POST /api/v1/actions/bulk-breakeven': {
    summary: 'Action Bulk Breakeven';
  };
  'POST /api/v1/actions/close-batch': {
    summary: 'Action Close Batch';
  };
  'POST /api/v1/actions/close-position': {
    summary: 'Action Close Position';
  };
  'POST /api/v1/actions/emergency-kill': {
    summary: 'Action Emergency Kill';
  };
  'POST /api/v1/actions/kill-symbol/{symbol}': {
    summary: 'Action Kill Symbol';
  };
  'POST /api/v1/actions/override-risk': {
    summary: 'Action Override Risk';
  };
  'POST /api/v1/actions/pause': {
    summary: 'Action Pause Trading';
  };
  'POST /api/v1/actions/pause-trading': {
    summary: 'Action Pause Trading';
  };
  'POST /api/v1/actions/resume': {
    summary: 'Action Resume Trading';
  };
  'POST /api/v1/actions/resume-trading': {
    summary: 'Action Resume Trading';
  };
  'POST /api/v1/actions/shutdown': {
    summary: 'Shutdown System';
  };
  'POST /api/v1/actions/steer': {
    summary: 'Action Steer';
  };
  'POST /api/v1/actions/trigger-cycle': {
    summary: 'Action Trigger Cycle';
  };
  'POST /api/v1/actions/unsuspend': {
    summary: 'Action Unsuspend Symbols';
  };
  'GET /api/v1/activity': {
    summary: 'Get Activity';
  };
  'GET /api/v1/analysis': {
    summary: 'Get Analysis';
  };
  'GET /api/v1/analysis-quality-realtime': {
    summary: 'Get Analysis Quality Realtime';
  };
  'GET /api/v1/analysis/decision-dossier/{analysis_id}': {
    summary: 'Get Decision Dossier';
  };
  'GET /api/v1/auth/role': {
    summary: 'Get Auth Role';
  };
  'POST /api/v1/backtest/run': {
    summary: 'Trigger Backtest Run';
  };
  'GET /api/v1/backtest/runs': {
    summary: 'List Backtest Runs';
  };
  'GET /api/v1/backtest/runs/{run_id}': {
    summary: 'Get Backtest Run Details';
  };
  'GET /api/v1/benchmark/compare': {
    summary: 'Compare Task Benchmarks';
  };
  'GET /api/v1/benchmark/leaderboard': {
    summary: 'Get Benchmark Leaderboard';
  };
  'GET /api/v1/benchmark/models': {
    summary: 'List Benchmark Models';
  };
  'GET /api/v1/benchmark/quadrant/{run_id}': {
    summary: 'Get Benchmark Quadrant Chart Data';
  };
  'POST /api/v1/benchmark/run': {
    summary: 'Trigger Benchmark Run';
  };
  'GET /api/v1/benchmark/runs': {
    summary: 'List Benchmark Runs';
  };
  'GET /api/v1/benchmark/runs/{run_id}': {
    summary: 'Get Benchmark Run Detail';
  };
  'GET /api/v1/benchmark/tasks': {
    summary: 'List Benchmark Tasks';
  };
  'GET /api/v1/brief': {
    summary: 'Get Brief';
  };
  'GET /api/v1/calendar/events': {
    summary: 'Get Calendar Events';
  };
  'GET /api/v1/calendar/upcoming': {
    summary: 'Get Upcoming High Impact Events';
  };
  'GET /api/v1/config/plugins/schemas': {
    summary: 'Get All Plugin Config Schemas';
  };
  'GET /api/v1/config/plugins/{plugin_id}/schema': {
    summary: 'Get Plugin Config Schema';
  };
  'GET /api/v1/config/schema': {
    summary: 'Get Config Schema';
  };
  'GET /api/v1/config/settings': {
    summary: 'Get Config Settings';
  };
  'PUT /api/v1/config/settings': {
    summary: 'Update Config Settings';
  };
  'GET /api/v1/debate-outcomes': {
    summary: 'Get Debate Outcomes';
  };
  'GET /api/v1/decision-distribution': {
    summary: 'Get Decision Distribution';
  };
  'GET /api/v1/edge-metrics': {
    summary: 'Get Edge Metrics';
  };
  'GET /api/v1/factor-analysis': {
    summary: 'Get Factor Analysis';
  };
  'GET /api/v1/gemini-quota': {
    summary: 'Get Gemini Quota';
  };
  'POST /api/v1/harness/cycle': {
    summary: 'Trigger Harness Cycle';
  };
  'GET /api/v1/harness/library': {
    summary: 'Get Harness Library';
  };
  'GET /api/v1/harness/tree': {
    summary: 'Get Harness Tree';
  };
  'GET /api/v1/health': {
    summary: 'Get Health';
  };
  'GET /api/v1/health/diagnostics': {
    summary: 'Get Health Diagnostics';
  };
  'POST /api/v1/kill': {
    summary: 'Action Emergency Kill';
  };
  'GET /api/v1/market/candles/{symbol}': {
    summary: 'Get Market Candles';
  };
  'GET /api/v1/market/cot': {
    summary: 'Get Cot Reports';
  };
  'GET /api/v1/market/fear-greed': {
    summary: 'Get Market Fear Greed';
  };
  'GET /api/v1/market/fedwatch': {
    summary: 'Get Market Fedwatch';
  };
  'GET /api/v1/market/indicators/{symbol}': {
    summary: 'Get Technical Indicators Snapshot';
  };
  'GET /api/v1/market/sentiment-composite': {
    summary: 'Get Market Sentiment Composite';
  };
  'GET /api/v1/market/structure/{symbol}': {
    summary: 'Get Market Structure Levels';
  };
  'GET /api/v1/market/yields': {
    summary: 'Get Market Yields';
  };
  'POST /api/v1/mcp/messages': {
    summary: 'Mcp Post Message';
  };
  'GET /api/v1/mcp/sse': {
    summary: 'Mcp Sse Endpoint';
  };
  'GET /api/v1/mcp/tools': {
    summary: 'List Mcp Tools';
  };
  'GET /api/v1/memory/lessons': {
    summary: 'Get Lessons';
  };
  'GET /api/v1/memory/playbooks': {
    summary: 'Get Playbooks';
  };
  'GET /api/v1/memory/playbooks/{name}/history': {
    summary: 'Get Playbook History';
  };
  'POST /api/v1/memory/playbooks/{name}/rollback': {
    summary: 'Rollback Playbook';
  };
  'GET /api/v1/memory/reflections': {
    summary: 'Get Reflections';
  };
  'POST /api/v1/memory/search': {
    summary: 'Search Memory';
  };
  'GET /api/v1/metrics': {
    summary: 'Get Metrics';
  };
  'GET /api/v1/news/classified': {
    summary: 'Get Classified News';
  };
  'GET /api/v1/news/sentiment': {
    summary: 'Get Aggregated Sentiment';
  };
  'GET /api/v1/observability/cycles/{cycle_id}/lineage': {
    summary: 'Get Cycle Decision Lineage';
  };
  'GET /api/v1/observability/graph-state': {
    summary: 'Get Graph State';
  };
  'GET /api/v1/observability/playbook-tree': {
    summary: 'Get Playbook Tree';
  };
  'GET /api/v1/observability/prompt-cache-metrics': {
    summary: 'Get Prompt Cache Metrics';
  };
  'GET /api/v1/observability/tool-latencies': {
    summary: 'Get Tool Latencies';
  };
  'GET /api/v1/observability/trajectories': {
    summary: 'Get Trade Trajectories';
  };
  'GET /api/v1/orders': {
    summary: 'Get Orders';
  };
  'POST /api/v1/orders/preview': {
    summary: 'Preview Manual Order';
  };
  'POST /api/v1/orders/submit': {
    summary: 'Submit Manual Order';
  };
  'GET /api/v1/overview': {
    summary: 'Get Overview';
  };
  'GET /api/v1/paper-trading': {
    summary: 'Get Paper Trading Stats';
  };
  'GET /api/v1/ping': {
    summary: 'Ping';
  };
  'GET /api/v1/plugins': {
    summary: 'Get Plugins';
  };
  'GET /api/v1/plugins/': {
    summary: 'Get Plugins';
  };
  'GET /api/v1/plugins/catalog': {
    summary: 'Get Plugin Catalog';
  };
  'POST /api/v1/plugins/install': {
    summary: 'Install Plugin';
  };
  'POST /api/v1/plugins/toggle': {
    summary: 'Toggle Plugin';
  };
  'POST /api/v1/plugins/uninstall': {
    summary: 'Uninstall Plugin';
  };
  'GET /api/v1/positions': {
    summary: 'Get Positions';
  };
  'POST /api/v1/positions/{ticket}/breakeven': {
    summary: 'Action Position Breakeven';
  };
  'POST /api/v1/positions/{ticket}/modify': {
    summary: 'Modify Position';
  };
  'POST /api/v1/positions/{ticket}/trailing': {
    summary: 'Action Trailing Override';
  };
  'GET /api/v1/reports/tearsheet/latest': {
    summary: 'Get Latest Tearsheet';
  };
  'POST /api/v1/resume': {
    summary: 'Action Resume Trading';
  };
  'GET /api/v1/risk': {
    summary: 'Get Risk';
  };
  'GET /api/v1/risk/correlation-matrix': {
    summary: 'Get Risk Correlation Matrix';
  };
  'GET /api/v1/risk/scorecard': {
    summary: 'Get Risk Scorecard';
  };
  'GET /api/v1/sessions': {
    summary: 'List Sessions';
  };
  'GET /api/v1/sessions/{session_id}/messages': {
    summary: 'Get Session Messages';
  };
  'POST /api/v1/setup/submit': {
    summary: 'Submit Setup Configuration';
  };
  'GET /api/v1/signals/mt5': {
    summary: 'Get Mt5 Signals';
  };
  'GET /api/v1/skills': {
    summary: 'Get Skills Catalog';
  };
  'POST /api/v1/skills/crystallize': {
    summary: 'Crystallize Skills Now';
  };
  'GET /api/v1/skills/crystallized': {
    summary: 'Get Crystallized Skills';
  };
  'POST /api/v1/skills/curate': {
    summary: 'Curate Crystallized Skills';
  };
  'POST /api/v1/skills/{name}/deprecate': {
    summary: 'Deprecate Crystallized Skill';
  };
  'GET /api/v1/skills/{name}/stats': {
    summary: 'Get Skill Stats';
  };
  'GET /api/v1/ssvp-health': {
    summary: 'Get Ssvp Health';
  };
  'GET /api/v1/tokens/context-tracker': {
    summary: 'Get Context Tracker Metrics';
  };
  'GET /api/v1/tokens/cycles': {
    summary: 'Get Tokens By Cycle';
  };
  'GET /api/v1/tokens/per-turn-cost': {
    summary: 'Get Per Turn Cost Metrics';
  };
  'GET /api/v1/tokens/recent': {
    summary: 'Get Tokens Recent';
  };
  'GET /api/v1/tokens/roles': {
    summary: 'Get Tokens By Role';
  };
  'GET /api/v1/tokens/subsystems': {
    summary: 'Get Tokens By Subsystem';
  };
  'GET /api/v1/tokens/summary': {
    summary: 'Get Tokens Summary';
  };
  'GET /api/v1/tokens/symbols': {
    summary: 'Get Tokens By Symbol';
  };
  'GET /api/v1/traces': {
    summary: 'Get Traces';
  };
  'GET /api/v1/traces/cycle/{cycle_id}': {
    summary: 'Get Cycle Trace Summary';
  };
  'GET /api/v1/traces/search': {
    summary: 'Search Traces';
  };
  'GET /api/v1/traces/slow-llm': {
    summary: 'Slow Llm Calls';
  };
  'GET /api/v1/traces/{trace_id}': {
    summary: 'Get Trace Tree';
  };
  'GET /api/v1/triggers': {
    summary: 'Get Trade Triggers';
  };
  'GET /api/v1/vix': {
    summary: 'Get Vix';
  };
  'POST /api/v1/webhooks/ingress': {
    summary: 'General Webhook Ingress';
  };
  'POST /api/v1/webhooks/tradingview': {
    summary: 'Tradingview Webhook';
  };
  'POST /api/v1/ws/ticket': {
    summary: 'Create Ws Ticket';
  };
  'GET /health': {
    summary: 'Health Check';
  };
  'POST /v1/chat/completions': {
    summary: 'Chat Completions';
  };
  'GET /v1/models': {
    summary: 'List Models';
  };
  'GET /v1/status': {
    summary: 'Health Check';
  };
  'POST /webhooks/ingress': {
    summary: 'General Webhook Ingress';
  };
  'POST /webhooks/tradingview': {
    summary: 'Tradingview Webhook';
  };
}

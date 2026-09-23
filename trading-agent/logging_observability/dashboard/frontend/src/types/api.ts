export interface HealthStatus {
  status: 'ok' | 'degraded' | 'error';
  uptime_seconds: number;
  db_connected: boolean;
  mt5_connected: boolean;
  heartbeat_age_seconds: number | null;
  last_scraper_run: string | null;
  last_analysis_cycle: string | null;
  gemini_api_available: boolean;
  gemini_quota: {
    flash: { used: number; remaining: number; max_rpd: number };
    flash_lite: { used: number; remaining: number; max_rpd: number };
  };
  data_freshness: {
    news_hours_old: number | null;
    calendar_hours_old: number | null;
    vix_days_old: number | null;
    cot_days_old: number | null;
  };
  api_cost_ytd_usd: number;
  timestamp: string;
}

export interface Overview {
  agent_status: 'active' | 'paused' | 'error';
  open_positions_count: number;
  daily_pnl: number;
  daily_pnl_pct: number | null;
  current_drawdown: number;
  drawdown_pct: number | null;
  trading_paused: boolean;
  pause_reason: string | null;
  vix: number | null;
  vix_date: string | null;
  last_analysis_at: string | null;
  timestamp: string;
}

export interface Position {
  id: number;
  mt5_ticket: number | null;
  symbol: string;
  direction: 'buy' | 'sell';
  volume: number;
  entry_price: number;
  sl: number | null;
  tp: number | null;
  opened_at: string | null;
  closed_at: string | null;
  status: 'open' | 'closed';
  pnl: number | null;
  current_price?: number;
  floating_pnl?: number;
}

export interface ActivityLog {
  id: number;
  timestamp: string;
  category: 'trading' | 'analysis' | 'risk' | 'system' | 'scraping' | 'telegram';
  description: string;
  related_id: number | null;
  actor: string;
}

export interface Analysis {
  id: number;
  symbol: string;
  decision: 'buy' | 'sell' | 'wait' | 'avoid' | 'skip';
  confidence: number | null;
  generated_at: string;
  stop_loss: number | null;
  take_profit: number | null;
  rationale: string;
  reevaluation_trigger: string | null;
  invalidation: string | null;
}

export interface PaperTradingStats {
  total_trades: number;
  market_trades: number;
  wins: number;
  losses: number;
  win_rate_market_pct: number;
  win_rate_pct: number;
  avg_pnl_pct: number;
  total_pnl_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  avg_rr_achieved: number;
  expectancy_per_trade_pct: number;
  expectancy_per_trade_R: number;
  has_positive_edge: boolean;
  edge_alert: boolean;
  by_symbol: Record<string, {
    trades: number;
    wins: number;
    losses: number;
    pnl_pct: number;
    win_rate: number;
  }>;
  by_confluence: Record<string, { wins: number; total: number }>;
  by_priced_in: Record<string, { score: number; wins: number; total: number }>;
  session_buckets: Record<string, {
    label: string;
    wins: number;
    total: number;
  }>;
  avg_win_hold_hours: number;
  avg_loss_hold_hours: number;
  recent_20: Array<{
    symbol: string;
    exit_reason: string;
    pnl_pct: number;
  }>;
}

export interface FactorAnalysis {
  days_analyzed: number;
  total_trades_analyzed: number;
  factor_effectiveness: Record<string, {
    win_rate: number;
    total: number;
    wins: number;
    assessment: 'STRONG_PREDICTOR' | 'MODERATE' | 'WEAK_PREDICTOR' | 'NEGATIVE_PREDICTOR';
  }>;
  insufficient_data?: boolean;
}

export interface EdgeMetrics {
  edge_metrics: Record<string, {
    total_trades: number;
    win_rate_pct: number;
    avg_rr_achieved: number;
    expectancy_per_trade_R: number;
    is_profitable: boolean;
    avg_holding_hours: number | null;
    insufficient_data?: boolean;
  }>;
  alert: boolean;
  timestamp: string;
}

export interface VixDataPoint {
  date: string;
  close: number;
}

export interface Brief {
  id: number;
  generated_at: string;
  valid_until: string | null;
  content_markdown: string;
  structured: {
    macro_narrative: string;
    currency_bias: Record<string, 'bullish' | 'bearish' | 'neutral'>;
    key_upcoming_risks: Array<{
      event: string;
      time?: string;
      expected_impact: 'high' | 'medium' | 'low';
    }>;
    risk_sentiment: 'risk-on' | 'risk-off' | 'mixed';
    confidence: number;
    priced_in_assessment?: {
      dominant_driver: string;
      priced_in_score: number;
      sell_the_news_risk: string;
    };
  } | null;
}

export interface RiskState {
  date: string;
  daily_pnl: number;
  daily_pnl_pct: number;
  current_drawdown: number;
  trading_paused: boolean;
  reason: string | null;
}

export interface DecisionDistribution {
  [symbol: string]: {
    buy: number;
    sell: number;
    wait: number;
    avoid: number;
    skip: number;
    total: number;
    trade_rate_pct: number;
  };
}

export interface GeminiQuota {
  flash: { used: number; remaining: number; max_rpd: number; pct_used: number };
  flash_lite: { used: number; remaining: number; max_rpd: number; pct_used: number };
  timestamp: string;
}

export interface AnalysisQualityRealtime {
  period: string;
  total_actionable_analyses: number;
  missing_confluence_score_pct: number;
  missing_priced_in_score_pct: number;
  avg_confluence_score: number | null;
  avg_priced_in_score: number | null;
  compliance_rate_pct: number;
  confluence_score_distribution: { high: number; medium: number; low: number };
  closed_trades_7d: number;
  win_rate_pct: number | null;
  alert: boolean;
}

// ---------------------------------------------------------------------------
// Token Audit & Observability Types
// ---------------------------------------------------------------------------

export interface TokenSummary {
  time_window_hours: number;
  total_calls: number;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  pure_content_tokens: number;
  thinking_pct_of_output: number;
  total_tokens: number;
  cached_tokens: number;
  cache_creation_tokens: number;
  cache_hit_rate_pct: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  success_count: number;
  fallback_count: number;
  rate_limit_count: number;
  error_count: number;
}

export interface TokenRoleItem {
  task_role: string;
  subsystem: string;
  calls: number;
  avg_input: number;
  avg_output: number;
  avg_thinking: number;
  sum_thinking: number;
  thinking_pct: number;
  avg_total: number;
  sum_total: number;
  sum_cached: number;
  sum_cost_usd: number;
  avg_latency_ms: number;
  fallback_calls: number;
}

export interface TokenSubsystemItem {
  subsystem: string;
  calls: number;
  sum_input: number;
  sum_output: number;
  sum_thinking: number;
  sum_total: number;
  sum_cached: number;
  sum_cost_usd: number;
  pct_tokens: number;
  pct_cost: number;
}

export interface TokenSymbolItem {
  symbol: string;
  calls: number;
  sum_total: number;
  sum_thinking: number;
  sum_cached: number;
  sum_cost_usd: number;
}

export interface TokenRecentLog {
  id: number;
  timestamp: string | null;
  provider: string;
  model_name: string;
  task_name: string | null;
  task_role: string | null;
  subsystem: string | null;
  symbol: string | null;
  cycle_id: string | null;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cost_estimate: number;
  execution_time_ms: number;
  status: string;
  slot_name: string | null;
}

// ---------------------------------------------------------------------------
// Execution & Signal Tracking Types
// ---------------------------------------------------------------------------

export interface MT5SignalItem {
  id: number;
  asset_analysis_id: number | null;
  symbol: string;
  action: string;
  status: string;
  mt5_ticket: number | null;
  created_at: string | null;
  executed_at: string | null;
  error_message: string | null;
}

export interface TradeTriggerItem {
  id: number;
  asset_analysis_id: number | null;
  trigger_type: string;
  status: string;
  condition: Record<string, unknown> | string | null;
  created_at: string | null;
  fired_at: string | null;
}

// ---------------------------------------------------------------------------
// Debate Outcomes & Specialist Adjudication Types
// ---------------------------------------------------------------------------

export interface DebateOutcomeItem {
  id: number;
  symbol: string;
  decision: string;
  confidence: number | null;
  confluence_score: number | null;
  risk_multiplier: number | null;
  rationale: string;
  specialist_adjudication: Record<string, unknown> | string | null;
  debate_bull_thesis?: Record<string, unknown> | string | null;
  debate_bear_dissent?: Record<string, unknown> | string | null;
  debate_verdict?: string | null;
  debate_reason?: string | null;
  generated_at: string | null;
  execution_status: string | null;
}

// ---------------------------------------------------------------------------
// Phase 2: RBAC, Config, Sessions & Agent Chat Types
// ---------------------------------------------------------------------------

export type UserRole = 'viewer' | 'operator' | 'admin';

export interface AuthRoleResponse {
  role: UserRole;
  is_localhost: boolean;
}

export interface ConfigResponse {
  status: string;
  settings: Record<string, any>;
  raw_yaml?: string;
  file_path?: string;
}

export interface ConfigUpdateResult {
  status: string;
  message: string;
  backup_path?: string;
  reloaded?: boolean;
}

export interface ConversationSession {
  session_id: string;
  source: 'telegram' | 'dashboard';
  message_count: number;
  last_active: string | null;
  first_active: string | null;
  last_message: string;
  last_role: string;
}

export interface ConversationMessage {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  message: string;
  timestamp: string | null;
}

export interface ChatProposedAction {
  action_id: string;
  action_type: string;
  params: Record<string, any>;
  description: string;
  created_at?: string;
  expires_at?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
  isStreaming?: boolean;
  toolsUsed?: string[];
  pendingAction?: ChatProposedAction | null;
  status?: string;
}

export interface ChatToolEvent {
  type: 'tool_start' | 'tool_result';
  tool: string;
  input?: Record<string, any>;
  summary?: string;
  timestamp?: string;
}

// -----------------------------------------------------------------------------
// Phase 5: LangGraph DAG Visualizer Types
// -----------------------------------------------------------------------------
export type GraphNodeStatus = 'done' | 'running' | 'pending' | 'failed';

export interface GraphNodeTokens {
  input: number;
  output: number;
  total: number;
  cost_usd: number;
}

export interface GraphNode {
  id: string;
  name: string;
  stage: 'stage1' | 'prefetch' | 'debate' | 'risk' | 'execution';
  status: GraphNodeStatus;
  duration_ms: number;
  tokens: GraphNodeTokens;
  input_summary: string;
  output_payload: Record<string, any> | null;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface GraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface CycleItem {
  cycle_id: string;
  label?: string;
  status: 'completed' | 'running' | 'failed';
  timestamp?: string;
  duration_ms?: number;
}

export interface GraphStateResponse {
  cycle_id: string;
  status: 'completed' | 'running' | 'failed';
  started_at?: string | null;
  completed_at?: string | null;
  total_duration_ms: number;
  total_tokens: GraphNodeTokens;
  available_cycles: CycleItem[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CycleTraceSummaryResponse {
  cycle_id: string;
  summary: {
    cycle_id: string;
    total_spans: number;
    total_input_tokens: number;
    total_output_tokens: number;
    total_cost_usd: number;
    tool_call_counts: Record<string, number>;
    node_durations_ms: Record<string, number>;
  };
  spans: Array<{
    trace_id: string;
    span_id: string;
    parent_span_id?: string | null;
    name: string;
    kind: string;
    start_time: string;
    end_time?: string | null;
    duration_ms: number;
    attributes: Record<string, any>;
    status: string;
    error?: string | null;
  }>;
  graph_state?: GraphStateResponse;
}

export interface DecisionReflectionItem {
  id: number;
  symbol: string;
  decision: string;
  confidence: number;
  confluence_score?: number | null;
  rationale_summary?: string | null;
  outcome_pnl_usd?: number | null;
  holding_hours?: number | null;
  exit_reason?: string | null;
  was_profitable?: boolean | null;
  reflection_text?: string | null;
  next_trade_adjustment?: string | null;
  specific_lesson?: string | null;
  lesson_tags?: string | null;
  alpha_return?: number | null;
  process_was_sound?: boolean | null;
  outcome_process_classification?: string | null;
  macro_thesis_correct?: boolean | null;
  debate_verdict?: string | null;
  debate_summary?: string | null;
  is_paper_whatif: boolean;
  whatif_reason?: string | null;
}

export interface CandidateLessonItem {
  id: number;
  symbol: string;
  lesson_text: string;
  status: 'shadow' | 'promoted' | 'rejected' | string;
  proposed_at?: string | null;
  evaluated_trades_count: number;
  win_rate_delta: number;
  sharpe_delta: number;
  promoted_at?: string | null;
  rejection_reason?: string | null;
  condition_tags?: string | null;
}

export interface MemorySearchResult {
  query: string;
  total_matches: number;
  reflections: Array<{
    id: number;
    symbol: string;
    decision: string;
    outcome_pnl_usd?: number | null;
    reflection_text?: string | null;
    specific_lesson?: string | null;
    next_trade_adjustment?: string | null;
    was_profitable?: boolean | null;
  }>;
  lessons: Array<{
    id: number;
    symbol: string;
    lesson_text: string;
    status: string;
    win_rate_delta: number;
  }>;
}

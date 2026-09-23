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
      dominant_driver?: string;
      priced_in_score?: number;
      sell_the_news_risk?: string;
    } | string;
    contrarian_opportunities?: Array<{
      asset?: string;
      rationale?: string;
      opportunity?: string;
    }> | string[];
    cross_asset_confirmations?: Array<{
      pair?: string;
      status?: string;
      confirmation?: string;
    }> | string[];
  } | null;
}

export interface RiskState {
  date: string;
  daily_pnl: number;
  daily_pnl_pct: number;
  current_drawdown: number;
  trading_paused: boolean;
  reason: string | null;
  margin_used?: number;
  margin_free?: number;
  margin_level_pct?: number;
  margin_usage_pct?: number;
  total_open_risk_pct?: number;
  consecutive_losses?: number;
  max_consecutive_losses?: number;
  max_risk_pct?: number;
  max_daily_drawdown_pct?: number;
  max_positions?: number;
  avg_spread_pips?: number;
  avg_rr_ratio?: number;
  is_weekend?: boolean;
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

export interface BacktestRunItem {
  id: number;
  mode: string;
  start_date: string | null;
  end_date: string | null;
  initial_equity: number;
  final_equity: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  created_at: string | null;
}

export interface BacktestTradeItem {
  id: number;
  symbol: string;
  direction: string;
  entry_time: string | null;
  entry_price: number;
  exit_time: string | null;
  exit_price: number;
  exit_reason: string;
  pnl_pips: number;
  pnl_pct: number;
  executed_lots: number;
  confidence: number;
  rationale: string;
}

export interface BacktestRunDetails {
  run: BacktestRunItem & { step_hours?: number };
  trades_count: number;
  trades: BacktestTradeItem[];
}

export interface TraceSpanItem {
  name: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  kind: string;
  start_time: string;
  end_time?: string | null;
  duration_ms: number;
  status: string;
  error?: string | null;
  attributes: Record<string, any>;
}

export interface SlowLlmSpanItem {
  name: string;
  provider?: string | null;
  model?: string | null;
  duration_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_usd?: number | null;
  cycle_id?: string | null;
  status: string;
  error?: string | null;
  start_time: string;
}

export interface TokenTurnCostMetrics {
  time_window_hours: number;
  total_turns: number;
  total_cost_usd: number;
  avg_cost_per_turn_usd: number;
  cycle_count: number;
}

export interface OrderLogItem {
  id: number;
  action: string;
  symbol: string;
  params: Record<string, any> | string | null;
  requested_by?: string | null;
  approved_by?: string | null;
  result: Record<string, any> | string | null;
  timestamp: string | null;
}

export interface SSVPHealthMetrics {
  calibration: Record<string, any>;
  inflation: Record<string, any>;
  status: 'healthy' | 'warning' | 'degraded';
  timestamp: string;
}

export interface PlaybookRuleItem {
  id: number;
  rule_hash: string;
  symbol: string;
  rule_text: string;
  status: 'active' | 'golden' | 'deprecated' | 'candidate' | string;
  times_triggered: number;
  wins_count: number;
  losses_count: number;
  total_pnl: number;
  win_rate: number;
  last_triggered_at: string | null;
  promoted_at: string | null;
  deprecated_at: string | null;
  deprecation_reason: string | null;
}

export interface CalendarEventItem {
  id: number;
  event_name: string;
  country: string;
  currency: string;
  impact: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  event_time: string | null;
  surprise_score: number | null;
}

export interface COTReportItem {
  id: number;
  report_date: string | null;
  market_code: string;
  dealer_long: number;
  dealer_short: number;
  asset_mgr_long: number;
  asset_mgr_short: number;
  leveraged_long: number;
  leveraged_short: number;
  net_position: number;
}

export interface ClassifiedNewsItem {
  id: number;
  source: string;
  title: string;
  summary: string;
  url: string | null;
  published_at: string | null;
  currency_tags: string | null;
  fetched_at: string | null;
  impact: string | null;
  sentiment: string | null;
  key_data_point: string | null;
}

export interface AggregatedSentimentItem {
  period_hours: number;
  total_articles: number;
  currencies: Record<string, {
    bullish: number;
    bearish: number;
    neutral: number;
    total: number;
  }>;
  timestamp: string;
}

export interface SkillCatalogItem {
  name: string;
  description: string;
  markets: string[];
  requires_tools: string[];
  fallback_for_tools: string[];
  is_playbook: boolean;
}

export interface PluginCatalogItem {
  [key: string]: any;
}

export interface QuantTearsheetItem {
  initial_equity: number;
  final_equity: number;
  total_net_pnl: number;
  total_return_pct: number;
  annualized_return_pct: number;
  annualized_sharpe: number;
  annualized_sortino: number;
  calmar_ratio: number;
  gain_to_pain_ratio: number;
  max_drawdown_pct: number;
  current_drawdown_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  payoff_ratio: number;
  expectancy_r: number;
  expectancy_usd: number;
  generated_at: string;
}

export interface RiskScorecardItem {
  symbol: string;
  account_equity: number;
  total_checks: number;
  passed_count: number;
  failed_count: number;
  pass_rate_pct: number;
  checks_passed: string[];
  checks_failed: string[];
  checks: Record<string, { passed: boolean; reason: string }>;
  timestamp: string;
}

export interface CorrelationMatrixItem {
  symbols: string[];
  matrix: Record<string, Record<string, number>>;
  portfolio_heat: number;
  status: string;
  correlated_pairs: Array<{
    pair: string;
    correlation: number;
    effective_risk: number;
    weight: number;
  }>;
  timestamp: string;
}

export interface PlaybookHistoryEntry {
  timestamp: string;
  action: string;
  playbook_name: string;
  sha256_hash: string;
  reason: string;
  author: string;
}

export interface FedWatchItem {
  id: number;
  meeting_date: string;
  probabilities: Record<string, number>;
  fetched_at: string | null;
}

export interface CentralBankExpectationItem {
  id: number;
  bank: string;
  meeting_date: string;
  current_rate: number;
  prob_hike: number;
  prob_hold: number;
  prob_cut: number;
  source: string;
  fetched_at: string | null;
}

export interface FedWatchResponse {
  fedwatch: FedWatchItem[];
  central_banks: CentralBankExpectationItem[];
  total_fedwatch: number;
  total_central_banks: number;
}

export interface TreasuryYieldItem {
  tenor: string;
  yield_percent: number;
  date: string | null;
}

export interface GlobalBondItem {
  country_tenor: string;
  yield_percent: number;
  date: string | null;
}

export interface YieldsResponse {
  treasury_yields: TreasuryYieldItem[];
  spread_2s10s: number | null;
  is_inverted: boolean;
  global_bonds: GlobalBondItem[];
}

export interface FearGreedResponse {
  current_value: number;
  classification: string;
  wow_change: number | null;
  history_7d: Array<{
    value: number;
    classification: string;
    timestamp: string;
  }>;
  interpretation: string;
  fetched_at: string;
}

export interface SentimentCompositeResponse {
  crypto: any;
  forex_myfxbook: any;
  forex_fxssi: any;
  institutional_cot: Array<{
    market_code: string;
    report_date: string | null;
    dealer_long: number;
    dealer_short: number;
    asset_mgr_long: number;
    asset_mgr_short: number;
    leveraged_long: number;
    leveraged_short: number;
    net_position: number;
  }>;
  timestamp: string;
}

export interface TechnicalIndicatorsResponse {
  symbol: string;
  timeframe: string;
  indicators: Record<string, any>;
  total_indicators: number;
  timestamp: string;
}

export interface OrderBlockItem {
  id: number;
  direction: string;
  price_high: number;
  price_low: number;
  formed_at: string | null;
}

export interface StructureBreakItem {
  id: number;
  type: string;
  direction: string;
  price: number;
  formed_at: string | null;
}

export interface FVGItem {
  id: number;
  direction: string;
  gap_high?: number;
  gap_low?: number;
  top_price?: number;
  bottom_price?: number;
  formed_at: string | null;
}

export interface MarketStructureResponse {
  symbol: string;
  timeframe: string;
  order_blocks: OrderBlockItem[];
  structure_breaks: StructureBreakItem[];
  fair_value_gaps: FVGItem[];
  timestamp: string;
}

export interface ModifyPositionResponse {
  status: string;
  result: any;
}

export interface CrystallizedSkillItem {
  name: string;
  file: string;
  symbol: string;
  description: string;
  status: 'active' | 'deprecated';
  is_deprecated: boolean;
  deprecation_reason?: string | null;
  win_count: number;
  total_trades: number;
  win_rate: number;
  recent_win_rate?: number | null;
  total_pnl_usd: number;
  avg_confidence?: number | null;
  last_crystallized_at?: string | null;
}

export interface SkillStatsItem {
  skill_name: string;
  times_triggered: number;
  wins_count: number;
  losses_count: number;
  total_pnl: number;
  win_rate: number;
  recent_win_rate?: number;
  recent_outcomes: boolean[];
  status: string;
  deprecation_reason?: string;
  updated_at: string;
}

export interface TradeTrajectoryItem {
  symbol: string;
  decision: string;
  ticket?: number | null;
  timestamp: string;
  fundamental_brief?: Record<string, any>;
  specialist_outputs?: Record<string, any>;
  debate_verdict?: Record<string, any>;
  risk_decision?: Record<string, any>;
  execution_details?: Record<string, any>;
  pnl_pct?: number | null;
  pnl_usd?: number | null;
  mae_points?: number | null;
  mfe_points?: number | null;
  reflection_tags?: string[];
}

export interface TrajectoriesResponse {
  total: number;
  trajectories: TradeTrajectoryItem[];
}

export interface CycleEventItem {
  seq: number;
  cycle_id: string;
  event_type: string;
  timestamp: string;
  payload: Record<string, any>;
  source_event_seqs: number[];
  prev_hash?: string | null;
  chain_hash?: string | null;
}

export interface CycleLineageResponse {
  cycle_id: string;
  integrity_valid: boolean;
  integrity_error?: string | null;
  total_events: number;
  events: CycleEventItem[];
  lineage: CycleEventItem[];
  start_time?: string | null;
  end_time?: string | null;
}

// Plugin Marketplace & Harness Lifecycle Types
export interface PluginItem {
  id: string;
  name: string;
  category: string;
  version: string;
  origin: string;
  enabled: boolean;
  status: string;
  status_message?: string;
  description: string;
  author?: string;
  can_uninstall: boolean;
  can_toggle: boolean;
}

export interface PluginsResponse {
  status: string;
  count: number;
  plugins: PluginItem[];
}

export interface PluginCatalogItem {
  id: string;
  name: string;
  package: string;
  category: string;
  version: string;
  author: string;
  description: string;
  default_enabled: boolean;
}

export interface PluginCatalogResponse {
  status: string;
  count: number;
  catalog: PluginCatalogItem[];
}

export interface PluginToggleResponse {
  status: string;
  message: string;
  plugin_id: string;
  enabled: boolean;
  plugins: PluginItem[];
}

export interface PluginInstallResponse {
  status: string;
  package_name: string;
  output: string;
  plugins: PluginItem[];
}


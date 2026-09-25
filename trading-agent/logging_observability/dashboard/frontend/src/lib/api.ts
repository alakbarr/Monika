const BASE = '/api';

export type TokenStorageType = 'session' | 'memory' | 'local';

let inMemoryToken: string | null = null;
let preferredStorage: TokenStorageType = 'session';

export function setTokenStorageType(type: TokenStorageType) {
  preferredStorage = type;
}

export function getStoredToken(): string {
  if (typeof window === 'undefined') return inMemoryToken || '';
  if (inMemoryToken) return inMemoryToken;
  try {
    const sessionVal = sessionStorage.getItem('dashboard_api_key');
    if (sessionVal) return sessionVal;
    const localVal = localStorage.getItem('dashboard_api_key');
    if (localVal) return localVal;
  } catch {
    // Storage access blocked or unavailable
  }
  return '';
}

export function setStoredToken(token: string, storageType: TokenStorageType = preferredStorage) {
  inMemoryToken = token;
  if (typeof window === 'undefined') return;
  try {
    if (storageType === 'session') {
      sessionStorage.setItem('dashboard_api_key', token);
      localStorage.removeItem('dashboard_api_key');
    } else if (storageType === 'local') {
      localStorage.setItem('dashboard_api_key', token);
    } else if (storageType === 'memory') {
      sessionStorage.removeItem('dashboard_api_key');
      localStorage.removeItem('dashboard_api_key');
    }
  } catch {
    // Storage access blocked
  }
}

export function clearStoredToken() {
  inMemoryToken = null;
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem('dashboard_api_key');
    localStorage.removeItem('dashboard_api_key');
  } catch {
    // Storage access blocked
  }
}

function getHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const apiKey = getStoredToken();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  return headers;
}

async function get<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${BASE}${endpoint}`, {
    headers: getHeaders(),
  });
  if (res.status === 401 || res.status === 403) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('dashboard-auth-error', { detail: { status: res.status } }));
    }
  }
  if (!res.ok) throw new Error(`API ${endpoint}: ${res.status}`);
  return res.json();
}

async function post<T>(endpoint: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${endpoint}`, {
    method: 'POST',
    headers: getHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 || res.status === 403) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('dashboard-auth-error', { detail: { status: res.status } }));
    }
  }
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.message || `API POST ${endpoint}: ${res.status}`);
  }
  return res.json();
}

async function put<T>(endpoint: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${endpoint}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 || res.status === 403) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('dashboard-auth-error', { detail: { status: res.status } }));
    }
  }
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.message || `API PUT ${endpoint}: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => get<import('../types/api').HealthStatus>('/health/diagnostics'),
  overview: () => get<import('../types/api').Overview>('/overview'),
  positions: (status: 'open' | 'closed' | 'all' = 'open') =>
    get<import('../types/api').Position[]>(`/positions?status=${status}`),
  activity: (limit = 50, category?: string) =>
    get<import('../types/api').ActivityLog[]>(
      `/activity?limit=${limit}${category ? `&category=${category}` : ''}`
    ),
  analysis: (limit = 20, symbol?: string) =>
    get<import('../types/api').Analysis[]>(
      `/analysis?limit=${limit}${symbol ? `&symbol=${symbol}` : ''}`
    ),
  paperTrading: () =>
    get<import('../types/api').PaperTradingStats>('/paper-trading'),
  factorAnalysis: () =>
    get<import('../types/api').FactorAnalysis>('/factor-analysis'),
  edgeMetrics: () =>
    get<import('../types/api').EdgeMetrics>('/edge-metrics'),
  vix: (limit = 30) =>
    get<import('../types/api').VixDataPoint[]>(`/vix?limit=${limit}`),
  brief: () => get<{ brief: import('../types/api').Brief | null }>('/brief'),
  risk: () => get<import('../types/api').RiskState>('/risk'),
  geminiQuota: () =>
    get<import('../types/api').GeminiQuota>('/gemini-quota'),
  decisionDistribution: () =>
    get<import('../types/api').DecisionDistribution>('/decision-distribution'),
  analysisQuality: () =>
    get<import('../types/api').AnalysisQualityRealtime>('/analysis-quality-realtime'),

  // Token Audit & Observability
  tokensSummary: (hours = 24) =>
    get<import('../types/api').TokenSummary>(`/v1/tokens/summary?hours=${hours}`),
  tokensRoles: (hours = 24) =>
    get<{ total_roles: number; items: import('../types/api').TokenRoleItem[] }>(
      `/v1/tokens/roles?hours=${hours}`
    ),
  tokensSubsystems: (hours = 24) =>
    get<{ total_subsystems: number; items: import('../types/api').TokenSubsystemItem[] }>(
      `/v1/tokens/subsystems?hours=${hours}`
    ),
  tokensSymbols: (hours = 24) =>
    get<{ total_symbols: number; items: import('../types/api').TokenSymbolItem[] }>(
      `/v1/tokens/symbols?hours=${hours}`
    ),
  tokensRecent: (limit = 50) =>
    get<{ total: number; items: import('../types/api').TokenRecentLog[] }>(
      `/v1/tokens/recent?limit=${limit}`
    ),

  // Signals, Triggers & Debate Outcomes
  mt5Signals: (limit = 50) =>
    get<{ total: number; items: import('../types/api').MT5SignalItem[] }>(
      `/signals/mt5?limit=${limit}`
    ),
  triggers: (status?: string, limit = 50) =>
    get<{ total: number; items: import('../types/api').TradeTriggerItem[] }>(
      `/triggers?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ''}`
    ),
  debateOutcomes: (limit = 20) =>
    get<{ total: number; items: import('../types/api').DebateOutcomeItem[] }>(
      `/debate-outcomes?limit=${limit}`
    ),

  // Phase 2: RBAC & Auth
  authRole: () =>
    get<import('../types/api').AuthRoleResponse>('/auth/role'),

  // Phase 2: Full Config Editor
  configSettings: () =>
    get<import('../types/api').ConfigResponse>('/config/settings'),
  configSchema: () =>
    get<Record<string, unknown>>('/config/schema'),
  updateConfigSettings: (settings: Record<string, unknown>, reason?: string) =>
    put<import('../types/api').ConfigUpdateResult>('/config/settings', { settings, reason }),

  // Phase 2: Session Browser
  sessions: (source?: string, limit = 50) =>
    get<import('../types/api').ConversationSession[]>(
      `/sessions?limit=${limit}${source ? `&source=${encodeURIComponent(source)}` : ''}`
    ),
  sessionMessages: (sessionId: string, limit = 100) =>
    get<import('../types/api').ConversationMessage[]>(
      `/sessions/${encodeURIComponent(sessionId)}/messages?limit=${limit}`
    ),

  // Operational Actions
  triggerCycle: (forced = true, reason = 'Triggered from Dashboard') =>
    post<{ status: string; message: string }>('/actions/trigger-cycle', { forced, reason }),
  overrideRisk: (payload: Record<string, unknown>) =>
    post<{ status: string; message: string }>('/actions/override-risk', payload),
  emergencyKill: () =>
    post<{ status: string; message: string }>('/actions/emergency-kill', {}),
  closePosition: (ticketOrId: { ticket?: number; position_id?: number; reason?: string }) =>
    post<{ status: string; result: unknown }>('/actions/close-position', ticketOrId),
  approveTrade: (tradeId: number) =>
    post<{ status: string; message?: string }>(`/actions/approve-trade/${tradeId}`),

  // Phase 5: LangGraph Pipeline Visualizer
  graphState: (cycleId?: string) =>
    get<import('../types/api').GraphStateResponse>(
      `/observability/graph-state${cycleId ? `?cycle_id=${encodeURIComponent(cycleId)}` : ''}`
    ),
  cycleTraceSummary: (cycleId: string) =>
    get<import('../types/api').CycleTraceSummaryResponse>(
      `/traces/cycle/${encodeURIComponent(cycleId)}`
    ),
  playbookTree: () =>
    get<any>('/observability/playbook-tree'),
  promptCacheMetrics: (limit = 10) =>
    get<any>(`/observability/prompt-cache-metrics?limit=${limit}`),
  toolLatencies: () =>
    get<{ tools: any[] }>('/observability/tool-latencies'),

  // Phase 5: Memory System Browser & Search
  memoryReflections: (params?: {
    symbol?: string;
    limit?: number;
    profitable_only?: boolean;
    whatif_only?: boolean;
    search?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.symbol) sp.append('symbol', params.symbol);
    if (params?.limit) sp.append('limit', String(params.limit));
    if (params?.profitable_only !== undefined) sp.append('profitable_only', String(params.profitable_only));
    if (params?.whatif_only !== undefined) sp.append('whatif_only', String(params.whatif_only));
    if (params?.search) sp.append('search', params.search);
    const qs = sp.toString();
    return get<import('../types/api').DecisionReflectionItem[]>(`/memory/reflections${qs ? `?${qs}` : ''}`);
  },
  memoryLessons: (params?: { symbol?: string; status?: string; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.symbol) sp.append('symbol', params.symbol);
    if (params?.status) sp.append('status', params.status);
    if (params?.limit) sp.append('limit', String(params.limit));
    const qs = sp.toString();
    return get<import('../types/api').CandidateLessonItem[]>(`/memory/lessons${qs ? `?${qs}` : ''}`);
  },
  memorySearch: (query: string, symbol?: string, limit = 50) =>
    post<import('../types/api').MemorySearchResult>('/memory/search', { query, symbol, limit }),
  memoryPlaybooks: (limit = 50) =>
    get<import('../types/api').PlaybookRuleItem[]>(`/memory/playbooks?limit=${limit}`),

  // Backtest Management & Telemetry
  backtestRuns: (limit = 20, offset = 0) =>
    get<{ total: number; runs: import('../types/api').BacktestRunItem[] }>(
      `/backtest/runs?limit=${limit}&offset=${offset}`
    ),
  backtestRunDetails: (runId: number) =>
    get<import('../types/api').BacktestRunDetails>(`/backtest/runs/${runId}`),
  triggerBacktest: (body: { days: number; mode: string; initial_equity: number; step_hours: number }) =>
    post<{ status: string; message: string }>('/backtest/run', body),

  // Trace Search & Distributed Spans
  searchTraces: (params?: {
    kind?: string;
    min_duration_ms?: number;
    status?: string;
    provider?: string;
    model?: string;
    limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.kind) sp.append('kind', params.kind);
    if (params?.min_duration_ms !== undefined) sp.append('min_duration_ms', String(params.min_duration_ms));
    if (params?.status) sp.append('status', params.status);
    if (params?.provider) sp.append('provider', params.provider);
    if (params?.model) sp.append('model', params.model);
    if (params?.limit) sp.append('limit', String(params.limit));
    const qs = sp.toString();
    return get<{ count: number; spans: import('../types/api').TraceSpanItem[] }>(`/traces/search${qs ? `?${qs}` : ''}`);
  },
  slowLlmCalls: (thresholdMs = 15000, limit = 20) =>
    get<{ threshold_ms: number; count: number; spans: import('../types/api').SlowLlmSpanItem[] }>(
      `/traces/slow-llm?threshold_ms=${thresholdMs}&limit=${limit}`
    ),
  traceTree: (traceId: string) =>
    get<{ trace_id: string; roots: any[] }>(`/traces/${encodeURIComponent(traceId)}`),

  // Token Context & Turn Cost
  tokenContextTracker: () =>
    get<Record<string, any>>('/v1/tokens/context-tracker'),
  tokenCycles: (cycleId?: string, hours = 24) => {
    const sp = new URLSearchParams();
    if (cycleId) sp.append('cycle_id', cycleId);
    sp.append('hours', String(hours));
    return get<Record<string, any>>(`/v1/tokens/cycles?${sp.toString()}`);
  },
  tokenPerTurnCost: (hours = 24) =>
    get<import('../types/api').TokenTurnCostMetrics>(`/v1/tokens/per-turn-cost?hours=${hours}`),

  // Orders Audit Trail
  orders: (limit = 50, action?: string) =>
    get<import('../types/api').OrderLogItem[]>(
      `/orders?limit=${limit}${action ? `&action=${encodeURIComponent(action)}` : ''}`
    ),

  // SSVP Health Telemetry
  ssvpHealth: () =>
    get<import('../types/api').SSVPHealthMetrics>('/ssvp-health'),

  // Steer Directive
  steer: (body: { message: string; mode?: string; symbols?: string[] }) =>
    post<{ status: string; message: string; mode?: string; injected_at?: string }>('/actions/steer', body),

  // Market Intelligence & Calendar
  calendarEvents: (params?: { currency?: string; impact?: string; days_ahead?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.currency) sp.append('currency', params.currency);
    if (params?.impact) sp.append('impact', params.impact);
    if (params?.days_ahead !== undefined) sp.append('days_ahead', String(params.days_ahead));
    if (params?.limit !== undefined) sp.append('limit', String(params.limit));
    const qs = sp.toString();
    return get<import('../types/api').CalendarEventItem[]>(`/calendar/events${qs ? `?${qs}` : ''}`);
  },
  calendarUpcoming: () =>
    get<import('../types/api').CalendarEventItem[]>('/calendar/upcoming'),
  marketCot: (marketCode?: string, limit = 20) =>
    get<import('../types/api').COTReportItem[]>(
      `/market/cot?limit=${limit}${marketCode ? `&market_code=${encodeURIComponent(marketCode)}` : ''}`
    ),
  newsClassified: (params?: { symbol?: string; sentiment?: string; impact?: string; hours?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.symbol) sp.append('symbol', params.symbol);
    if (params?.sentiment) sp.append('sentiment', params.sentiment);
    if (params?.impact) sp.append('impact', params.impact);
    if (params?.hours !== undefined) sp.append('hours', String(params.hours));
    if (params?.limit !== undefined) sp.append('limit', String(params.limit));
    const qs = sp.toString();
    return get<import('../types/api').ClassifiedNewsItem[]>(`/news/classified${qs ? `?${qs}` : ''}`);
  },
  newsSentiment: () =>
    get<import('../types/api').AggregatedSentimentItem>('/news/sentiment'),
  skillsList: () =>
    get<{ skills: import('../types/api').SkillCatalogItem[]; total: number }>('/skills'),
  pluginsList: () =>
    get<{ plugins: import('../types/api').PluginCatalogItem[]; total: number }>('/plugins'),
  tearsheetLatest: () =>
    get<import('../types/api').QuantTearsheetItem>('/reports/tearsheet/latest'),

  // Risk Scorecard & Correlation Matrix
  riskScorecard: (symbol = 'EURUSD') =>
    get<import('../types/api').RiskScorecardItem>(`/risk/scorecard?symbol=${encodeURIComponent(symbol)}`),
  riskCorrelationMatrix: () =>
    get<import('../types/api').CorrelationMatrixItem>('/risk/correlation-matrix'),

  // Playbook Mutation History & 1-Click Rollback
  playbookHistory: (name: string) =>
    get<import('../types/api').PlaybookHistoryEntry[]>(`/memory/playbooks/${encodeURIComponent(name)}/history`),
  playbookRollback: (name: string, targetHash?: string) =>
    post<{ status: string; message: string; target_hash?: string }>(
      `/memory/playbooks/${encodeURIComponent(name)}/rollback`,
      { target_hash: targetHash, reason: 'Operator rollback from dashboard' }
    ),

  // Market Intelligence & Sentiment
  marketFedWatch: () =>
    get<import('../types/api').FedWatchResponse>('/market/fedwatch'),
  marketYields: () =>
    get<import('../types/api').YieldsResponse>('/market/yields'),
  marketFearGreed: () =>
    get<import('../types/api').FearGreedResponse>('/market/fear-greed'),
  marketSentimentComposite: () =>
    get<import('../types/api').SentimentCompositeResponse>('/market/sentiment-composite'),

  // Technical Indicators & SMC Structure
  marketIndicators: (symbol: string, timeframe = 'H1') =>
    get<import('../types/api').TechnicalIndicatorsResponse>(
      `/market/indicators/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`
    ),
  marketStructure: (symbol: string, timeframe = 'H4') =>
    get<import('../types/api').MarketStructureResponse>(
      `/market/structure/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`
    ),

  // Position Management & Modification
  positionModify: (ticket: number, body: { sl?: number; tp?: number; comment?: string }) =>
    post<import('../types/api').ModifyPositionResponse>(`/positions/${ticket}/modify`, body),

  // Autonomous Skill Crystallizer & Lifecycle
  skillsCrystallized: () =>
    get<{ skills: import('../types/api').CrystallizedSkillItem[]; total: number }>('/skills/crystallized'),
  skillStats: (name: string) =>
    get<import('../types/api').SkillStatsItem>(`/skills/${encodeURIComponent(name)}/stats`),
  skillCurate: () =>
    post<{ status: string; pruned_skills: any[]; pruned_count: number }>('/skills/curate', {}),
  skillDeprecate: (name: string, reason?: string) =>
    post<{ status: string; skill_name: string; success: boolean }>(
      `/skills/${encodeURIComponent(name)}/deprecate`,
      { reason: reason || 'Operator manual deprecation' }
    ),
  skillCrystallize: (symbol?: string) =>
    post<{ status: string; new_skills: any[]; count: number }>(
      '/skills/crystallize',
      symbol ? { symbol } : {}
    ),

  // Trajectories & Decision Lineage (FASE 5)
  tradeTrajectories: (limit = 50) =>
    get<import('../types/api').TrajectoriesResponse>(`/observability/trajectories?limit=${limit}`),
  cycleLineage: (cycleId: string, targetSeq?: number) =>
    get<import('../types/api').CycleLineageResponse>(
      `/observability/cycles/${encodeURIComponent(cycleId)}/lineage${targetSeq !== undefined ? `?target_seq=${targetSeq}` : ''}`
    ),

  // Plugin Marketplace & Harness Lifecycle
  plugins: () =>
    get<import('../types/api').PluginsResponse>('/plugins'),
  pluginCatalog: () =>
    get<import('../types/api').PluginCatalogResponse>('/plugins/catalog'),
  pluginToggle: (pluginId: string, category: string, enabled: boolean) =>
    post<import('../types/api').PluginToggleResponse>('/plugins/toggle', {
      plugin_id: pluginId,
      category,
      enabled,
    }),
  pluginInstall: (packageName: string) =>
    post<import('../types/api').PluginInstallResponse>('/plugins/install', {
      package_name: packageName,
    }),
  pluginUninstall: (packageName: string) =>
    post<{ status: string; output: string; plugins: import('../types/api').PluginItem[] }>('/plugins/uninstall', {
      package_name: packageName,
    }),

  // Benchmark & Model Lab
  benchmarkTasks: () =>
    get<{ total: number; tasks: any[]; categories: string[] }>('/benchmark/tasks'),
  benchmarkModels: () =>
    get<{ candidates: string[]; tiers: Record<string, any>; router_matrix: Record<string, string[]>; defaults: any }>('/benchmark/models'),
  benchmarkRuns: (limit = 20, offset = 0) =>
    get<{ total: number; runs: any[] }>(`/benchmark/runs?limit=${limit}&offset=${offset}`),
  benchmarkRunDetail: (runId: number) =>
    get<{ run: any; total_results: number; report_markdown: string; results: any[] }>(`/benchmark/runs/${runId}`),
  benchmarkQuadrant: (runId: number) =>
    get<{ run_id: number; points: any[] }>(`/benchmark/quadrant/${runId}`),
  benchmarkLeaderboard: (runId?: number) =>
    get<{ run_id: number; leaderboard: any[] }>(runId ? `/benchmark/leaderboard?run_id=${runId}` : '/benchmark/leaderboard'),
  benchmarkRunTrigger: (req: any) =>
    post<{ status: string; message: string; tasks_count: number; models_count: number }>('/benchmark/run', req),
};




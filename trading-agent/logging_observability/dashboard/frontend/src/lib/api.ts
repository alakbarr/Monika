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
};




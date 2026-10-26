import { create } from 'zustand';
import { api } from '../lib/api';
import type {
  HealthStatus, Overview, Position, ActivityLog,
  Analysis, PaperTradingStats, FactorAnalysis,
  EdgeMetrics, VixDataPoint, Brief, RiskState,
  DecisionDistribution, GeminiQuota, AnalysisQualityRealtime,
  ChartPresetId, ChartWorkspaceConfig,
} from '../types/api';
import {
  CHART_PRESETS,
  DEFAULT_CHART_WORKSPACE_CONFIG,
  normalizeChartWorkspaceConfig,
} from '../lib/chartIndicatorsClientMath';

const CHART_CONFIGS_STORAGE_KEY = 'monika_chart_configs_v1';

function getInitialChartConfigs(): {
  global: ChartWorkspaceConfig;
  symbols: Record<string, ChartWorkspaceConfig>;
  loadedFromServer: boolean;
} {
  let global = DEFAULT_CHART_WORKSPACE_CONFIG;
  const symbols: Record<string, ChartWorkspaceConfig> = {};

  if (typeof window !== 'undefined') {
    try {
      const stored = localStorage.getItem(CHART_CONFIGS_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.global) {
          global = normalizeChartWorkspaceConfig(parsed.global);
        }
        if (parsed.symbols && typeof parsed.symbols === 'object') {
          for (const [sym, cfg] of Object.entries(parsed.symbols)) {
            symbols[sym] = normalizeChartWorkspaceConfig(cfg as Partial<ChartWorkspaceConfig>);
          }
        }
      }
    } catch {
      // storage unreadable or corrupt
    }
  }

  return {
    global,
    symbols,
    loadedFromServer: false,
  };
}

function persistChartConfigsLocally(data: {
  global: ChartWorkspaceConfig;
  symbols: Record<string, ChartWorkspaceConfig>;
}) {
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(CHART_CONFIGS_STORAGE_KEY, JSON.stringify(data));
    } catch {
      // storage unavailable
    }
  }
}

const CHAPTER_DEFAULTS: Record<string, string> = {
  capital: 'overview',
  journal: 'debates',
  risk: 'risk',
  lab: 'backtest',
  atelier: 'config',
};

const resolveTab = (raw: string | null | undefined): string => {
  if (!raw) return 'overview';
  if (CHAPTER_DEFAULTS[raw]) return CHAPTER_DEFAULTS[raw];
  return raw;
};

interface DashboardState {
  // Data
  health: HealthStatus | null;
  overview: Overview | null;
  positions: Position[];
  activity: ActivityLog[];
  analyses: Analysis[];
  paperStats: PaperTradingStats | null;
  factorAnalysis: FactorAnalysis | null;
  edgeMetrics: EdgeMetrics | null;
  vixHistory: VixDataPoint[];
  brief: Brief | null;
  riskState: RiskState | null;
  geminiQuota: GeminiQuota | null;
  decisionDist: DecisionDistribution | null;
  analysisQuality: AnalysisQualityRealtime | null;
  marketQuotes: Record<string, { price: number; changePct: number }>;

  // Chart Workspace & Indicator Studio State
  chartConfigs: {
    global: ChartWorkspaceConfig;
    symbols: Record<string, ChartWorkspaceConfig>;
    loadedFromServer: boolean;
  };
  lastTickBySymbol: Record<string, { bid: number; ask: number; spread: number; timestamp: string }>;

  // UI State
  loading: boolean;
  error: string | null;
  lastRefresh: Date | null;
  selectedSymbol: string | null;
  activeTab: string;
  agentSheetOpen: boolean;
  wsConnected: boolean;
  userRole: import('../types/api').UserRole | null;
  theme: 'light' | 'dark';
  timeZoneDisplay: 'UTC' | 'LOCAL';

  // Actions
  setTheme: (theme: 'light' | 'dark') => void;
  setTimeZoneDisplay: (tz: 'UTC' | 'LOCAL') => void;
  fetchAll: () => Promise<void>;
  fetchQuick: () => Promise<void>;
  fetchUserRole: () => Promise<void>;
  setActiveTab: (tab: string) => void;
  setAgentSheetOpen: (open: boolean) => void;
  toggleAgentSheet: () => void;
  setSelectedSymbol: (symbol: string | null) => void;
  setWsConnected: (connected: boolean) => void;
  updateTickPrice: (tick: Record<string, unknown>) => void;
  addActivity: (event: Record<string, unknown>) => void;

  // Chart Workspace Actions
  loadChartConfigsFromServer: () => Promise<void>;
  getEffectiveChartConfig: (symbol: string) => { config: ChartWorkspaceConfig; isSymbolOverride: boolean };
  saveChartWorkspaceConfig: (symbol: string, config: ChartWorkspaceConfig, scope: 'global' | 'symbol') => Promise<void>;
  applyChartPreset: (symbol: string, presetId: ChartPresetId, scope: 'global' | 'symbol') => Promise<void>;
  resetSymbolChartOverride: (symbol: string) => Promise<void>;
}

let pendingTicks: Record<string, Record<string, unknown>> = {};
let tickRafId: number | null = null;

export const useDashboardStore = create<DashboardState>((set, get) => ({
  health: null,
  overview: null,
  positions: [],
  activity: [],
  analyses: [],
  paperStats: null,
  factorAnalysis: null,
  edgeMetrics: null,
  vixHistory: [],
  brief: null,
  riskState: null,
  geminiQuota: null,
  decisionDist: null,
  analysisQuality: null,
  marketQuotes: {},
  chartConfigs: getInitialChartConfigs(),
  lastTickBySymbol: {},
  loading: true,
  error: null,
  lastRefresh: null,
  selectedSymbol: null,
  activeTab: resolveTab(typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('tab') : 'overview'),
  agentSheetOpen: false,
  wsConnected: false,
  userRole: null,
  theme: (typeof window !== 'undefined' && (new URLSearchParams(window.location.search).get('theme') as 'light' | 'dark' || localStorage.getItem('monika_theme') as 'light' | 'dark')) || 'light',
  timeZoneDisplay: (typeof window !== 'undefined' && (localStorage.getItem('monika_timezone') as 'UTC' | 'LOCAL')) || 'UTC',

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('monika_theme', theme);
    set({ theme });
  },

  setTimeZoneDisplay: (timeZoneDisplay) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('monika_timezone', timeZoneDisplay);
    }
    set({ timeZoneDisplay });
  },

  fetchUserRole: async () => {
    try {
      const res = await api.authRole();
      if (res && res.role) {
        set({ userRole: res.role });
      }
    } catch {
      set({ userRole: 'viewer' });
    }
  },

  fetchQuick: async () => {
    try {
      const [overview, positions, activity, health] = await Promise.allSettled([
        api.overview(),
        api.positions('all'),
        api.activity(30),
        api.health(),
      ]);
      const rejectedCount = [overview, positions, activity, health].filter(r => r.status === 'rejected').length;
      if (rejectedCount === 4) {
        set({ error: 'Connection lost. Backend unreachable.' });
      } else {
        set({
          overview: overview.status === 'fulfilled' ? overview.value : get().overview,
          positions: positions.status === 'fulfilled' ? positions.value : get().positions,
          activity: activity.status === 'fulfilled' ? activity.value : get().activity,
          health: health.status === 'fulfilled' ? health.value : get().health,
          lastRefresh: new Date(),
          error: null,
        });
      }
    } catch {
      set({ error: 'Connection lost. Retrying...' });
    }
  },

  fetchAll: async () => {
    if (get().overview === null) {
      set({ loading: true });
    }
    try {
      const [
        overview, positions, activity, analyses,
        paperStats, factorAnalysis, edgeMetrics,
        vixHistory, briefRes, riskState,
        geminiQuota, decisionDist, analysisQuality, health,
      ] = await Promise.allSettled([
        api.overview(),
        api.positions('all'),
        api.activity(50),
        api.analysis(20),
        api.paperTrading(),
        api.factorAnalysis(),
        api.edgeMetrics(),
        api.vix(30),
        api.brief(),
        api.risk(),
        api.geminiQuota(),
        api.decisionDistribution(),
        api.analysisQuality(),
        api.health(),
      ]);

      const criticalFailures = [overview, positions, health].filter(r => r.status === 'rejected');
      const allFailures = [
        overview, positions, activity, analyses,
        paperStats, factorAnalysis, edgeMetrics,
        vixHistory, briefRes, riskState,
        geminiQuota, decisionDist, analysisQuality, health,
      ].filter(r => r.status === 'rejected');

      const errorMessage = criticalFailures.length >= 2
        ? 'Failed to connect to backend API. Please verify the service is running.'
        : allFailures.length > 5
        ? `Warning: ${allFailures.length} dashboard feed(s) failed to load.`
        : null;

      set((state) => ({
        overview: overview.status === 'fulfilled' ? overview.value : state.overview,
        positions: positions.status === 'fulfilled' ? positions.value : state.positions,
        activity: activity.status === 'fulfilled' ? activity.value : state.activity,
        analyses: analyses.status === 'fulfilled' ? analyses.value : state.analyses,
        paperStats: paperStats.status === 'fulfilled' ? paperStats.value : state.paperStats,
        factorAnalysis: factorAnalysis.status === 'fulfilled' ? factorAnalysis.value : state.factorAnalysis,
        edgeMetrics: edgeMetrics.status === 'fulfilled' ? edgeMetrics.value : state.edgeMetrics,
        vixHistory: vixHistory.status === 'fulfilled' ? vixHistory.value : state.vixHistory,
        brief: briefRes.status === 'fulfilled' ? briefRes.value.brief : state.brief,
        riskState: riskState.status === 'fulfilled' ? riskState.value : state.riskState,
        geminiQuota: geminiQuota.status === 'fulfilled' ? geminiQuota.value : state.geminiQuota,
        decisionDist: decisionDist.status === 'fulfilled' ? decisionDist.value : state.decisionDist,
        analysisQuality: analysisQuality.status === 'fulfilled' ? analysisQuality.value : state.analysisQuality,
        health: health.status === 'fulfilled' ? health.value : state.health,
        loading: false,
        lastRefresh: new Date(),
        error: errorMessage,
      }));
      get().loadChartConfigsFromServer().catch(() => {});
    } catch {
      set({ loading: false, error: 'Failed to load dashboard data.' });
    }
  },

  setActiveTab: (tab) => {
    const resolved = resolveTab(tab);
    set({ activeTab: resolved });
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', resolved);
      window.history.replaceState({}, '', url.toString());
    }
  },

  setAgentSheetOpen: (open) => set({ agentSheetOpen: open }),
  toggleAgentSheet: () => set((state) => ({ agentSheetOpen: !state.agentSheetOpen })),
  setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),
  setWsConnected: (connected) => set({ wsConnected: connected }),

  updateTickPrice: (tick) => {
    const sym = tick.symbol as string;
    if (!sym) return;

    pendingTicks[sym] = tick;

    const flushTicks = () => {
      tickRafId = null;
      const ticksToApply = pendingTicks;
      pendingTicks = {};

      let positions = get().positions;
      const marketQuotes = { ...get().marketQuotes };
      const lastTickBySymbol = { ...get().lastTickBySymbol };

      for (const [s, t] of Object.entries(ticksToApply)) {
        const bid = typeof t.bid === 'number' ? t.bid : Number(t.bid) || 0;
        const ask = typeof t.ask === 'number' ? t.ask : Number(t.ask) || bid;
        const spread = typeof t.spread === 'number' ? t.spread : Math.max(0, ask - bid);
        const timestamp = (t.timestamp as string) || (t.time as string) || new Date().toISOString();

        lastTickBySymbol[s] = { bid, ask, spread, timestamp };

        const floatingPnl =
          typeof t.floating_pnl === 'number'
            ? t.floating_pnl
            : t.floating_pnl != null
              ? Number(t.floating_pnl)
              : undefined;

        const tickTicket = t.ticket ? Number(t.ticket) : (t.mt5_ticket ? Number(t.mt5_ticket) : undefined);

        positions = positions.map((p) => {
          if (p.symbol !== s) return p;
          if (tickTicket !== undefined && p.mt5_ticket !== tickTicket && p.id !== tickTicket) {
            return p;
          }
          const posPnl = tickTicket !== undefined && floatingPnl !== undefined ? floatingPnl : p.pnl;
          return {
            ...p,
            current_price: bid,
            floating_pnl: posPnl !== null ? posPnl : undefined,
            pnl: posPnl,
          };
        });

        const existingQuote = marketQuotes[s];
        const rawChange = t.change_pct ?? t.changePct ?? t.pct_change;
        const changePct =
          typeof rawChange === 'number'
            ? rawChange
            : rawChange != null
              ? Number(rawChange) || 0
              : existingQuote?.changePct ?? 0;

        marketQuotes[s] = { price: bid, changePct };
      }

      set({ positions, marketQuotes, lastTickBySymbol });
    };

    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      if (tickRafId === null) {
        if (typeof document !== 'undefined' && document.hidden) {
          tickRafId = window.setTimeout(flushTicks, 100) as unknown as number;
        } else {
          tickRafId = window.requestAnimationFrame(flushTicks);
        }
      }
    } else {
      flushTicks();
    }
  },

  addActivity: (event) => {
    const relatedId =
      typeof event.related_id === 'number'
        ? event.related_id
        : typeof event.trade_id === 'number'
          ? event.trade_id
          : null;
    const desc =
      (event.description as string) ||
      (event.message as string) ||
      (event.trade_id
        ? `${(event.type as string) || 'Trade'} #${event.trade_id} ${event.status || 'approved'}`
        : JSON.stringify(event));

    const activityLog: ActivityLog = {
      id: typeof event.id === 'number' ? event.id : Date.now() + Math.random(),
      timestamp: (event.timestamp as string) || new Date().toISOString(),
      category: (event.category as ActivityLog['category']) || 'trading',
      description: desc,
      related_id: relatedId,
      actor: (event.actor as string) || 'dashboard',
    };
    const activity = [activityLog, ...get().activity].slice(0, 50);
    set({ activity });
  },

  loadChartConfigsFromServer: async () => {
    try {
      const res = await api.getChartConfig();
      if (res && res.global) {
        const globalNorm = normalizeChartWorkspaceConfig(res.global);
        const symbolsNorm: Record<string, ChartWorkspaceConfig> = {};
        if (res.symbols && typeof res.symbols === 'object') {
          for (const [sym, cfg] of Object.entries(res.symbols)) {
            symbolsNorm[sym] = normalizeChartWorkspaceConfig(cfg);
          }
        }
        const updated = {
          global: globalNorm,
          symbols: symbolsNorm,
          loadedFromServer: true,
        };
        persistChartConfigsLocally({ global: globalNorm, symbols: symbolsNorm });
        set({ chartConfigs: updated });
      }
    } catch {
      // Non-blocking fallback: local configs stay active
      set((state) => ({
        chartConfigs: { ...state.chartConfigs, loadedFromServer: false },
      }));
    }
  },

  getEffectiveChartConfig: (symbol: string) => {
    const { chartConfigs } = get();
    if (symbol && chartConfigs.symbols[symbol]) {
      return {
        config: chartConfigs.symbols[symbol],
        isSymbolOverride: true,
      };
    }
    return {
      config: chartConfigs.global,
      isSymbolOverride: false,
    };
  },

  saveChartWorkspaceConfig: async (
    symbol: string,
    config: ChartWorkspaceConfig,
    scope: 'global' | 'symbol'
  ) => {
    const norm = normalizeChartWorkspaceConfig(config);
    const prev = get().chartConfigs;

    let nextGlobal = prev.global;
    const nextSymbols = { ...prev.symbols };

    if (scope === 'global') {
      nextGlobal = norm;
    } else {
      nextSymbols[symbol] = norm;
    }

    const nextState = {
      global: nextGlobal,
      symbols: nextSymbols,
      loadedFromServer: prev.loadedFromServer,
    };

    // Immediate optimistic update to Zustand state and localStorage
    set({ chartConfigs: nextState });
    persistChartConfigsLocally({ global: nextGlobal, symbols: nextSymbols });

    // Non-blocking server persistence
    try {
      await api.saveChartConfig(scope, norm, symbol);
    } catch {
      // Optimistic state remains locally valid even if server persistence temporarily fails
    }
  },

  applyChartPreset: async (symbol: string, presetId: ChartPresetId, scope: 'global' | 'symbol') => {
    const template = CHART_PRESETS[presetId] || CHART_PRESETS.smc_institutional;
    const currentConfig = get().getEffectiveChartConfig(symbol).config;

    const merged: ChartWorkspaceConfig = {
      ...template,
      preset_id: presetId,
      timeframe: currentConfig.timeframe || template.timeframe,
      vision_sync_enabled: currentConfig.vision_sync_enabled ?? template.vision_sync_enabled,
      scope,
      symbol: scope === 'symbol' ? symbol : undefined,
    };

    await get().saveChartWorkspaceConfig(symbol, merged, scope);
  },

  resetSymbolChartOverride: async (symbol: string) => {
    if (!symbol) return;
    const prev = get().chartConfigs;
    if (!prev.symbols[symbol]) return;

    const nextSymbols = { ...prev.symbols };
    delete nextSymbols[symbol];

    const nextState = {
      global: prev.global,
      symbols: nextSymbols,
      loadedFromServer: prev.loadedFromServer,
    };

    set({ chartConfigs: nextState });
    persistChartConfigsLocally({ global: prev.global, symbols: nextSymbols });

    try {
      await api.deleteChartConfigOverride(symbol);
    } catch {
      // Local removal remains effective
    }
  },
}));

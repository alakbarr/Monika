import { create } from 'zustand';
import { api } from '../lib/api';
import type {
  HealthStatus, Overview, Position, ActivityLog,
  Analysis, PaperTradingStats, FactorAnalysis,
  EdgeMetrics, VixDataPoint, Brief, RiskState,
  DecisionDistribution, GeminiQuota, AnalysisQualityRealtime
} from '../types/api';

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

  // UI State
  loading: boolean;
  error: string | null;
  lastRefresh: Date | null;
  selectedSymbol: string | null;
  activeTab: string;
  wsConnected: boolean;
  userRole: import('../types/api').UserRole | null;
  theme: 'light' | 'dark';
  timeZoneDisplay: 'UTC' | 'LOCAL';

  // Actions
  setTheme: (theme: 'light' | 'dark') => void;
  setTimeZoneDisplay: (tz: 'UTC' | 'LOCAL') => void;
  fetchAll: () => Promise<void>;
  fetchQuick: () => Promise<void>; // fast-refresh subset
  fetchUserRole: () => Promise<void>;
  setActiveTab: (tab: string) => void;
  setSelectedSymbol: (symbol: string | null) => void;
  setWsConnected: (connected: boolean) => void;
  updateTickPrice: (tick: Record<string, unknown>) => void;
  addActivity: (event: Record<string, unknown>) => void;
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
  loading: true,
  error: null,
  lastRefresh: null,
  selectedSymbol: null,
  activeTab: (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab')) || 'overview',
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
      // Default to viewer if unable to resolve
      set({ userRole: 'viewer' });
    }
  },

  fetchQuick: async () => {
    // 5-second refresh: only critical live data
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
    } catch {
      set({ loading: false, error: 'Failed to load dashboard data.' });
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),
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
      let marketQuotes = { ...get().marketQuotes };

      for (const [s, t] of Object.entries(ticksToApply)) {
        const bid = typeof t.bid === 'number' ? t.bid : Number(t.bid) || 0;
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

      set({ positions, marketQuotes });
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
}));

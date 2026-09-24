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

  // Actions
  setTheme: (theme: 'light' | 'dark') => void;
  fetchAll: () => Promise<void>;
  fetchQuick: () => Promise<void>; // fast-refresh subset
  fetchUserRole: () => Promise<void>;
  setActiveTab: (tab: string) => void;
  setSelectedSymbol: (symbol: string | null) => void;
  setWsConnected: (connected: boolean) => void;
  updateTickPrice: (tick: Record<string, unknown>) => void;
  addActivity: (event: Record<string, unknown>) => void;
}

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

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('monika_theme', theme);
    set({ theme });
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
    set({ loading: true });
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

      set({
        overview: overview.status === 'fulfilled' ? overview.value : null,
        positions: positions.status === 'fulfilled' ? positions.value : [],
        activity: activity.status === 'fulfilled' ? activity.value : [],
        analyses: analyses.status === 'fulfilled' ? analyses.value : [],
        paperStats: paperStats.status === 'fulfilled' ? paperStats.value : null,
        factorAnalysis: factorAnalysis.status === 'fulfilled' ? factorAnalysis.value : null,
        edgeMetrics: edgeMetrics.status === 'fulfilled' ? edgeMetrics.value : null,
        vixHistory: vixHistory.status === 'fulfilled' ? vixHistory.value : [],
        brief: briefRes.status === 'fulfilled' ? briefRes.value.brief : null,
        riskState: riskState.status === 'fulfilled' ? riskState.value : null,
        geminiQuota: geminiQuota.status === 'fulfilled' ? geminiQuota.value : null,
        decisionDist: decisionDist.status === 'fulfilled' ? decisionDist.value : null,
        analysisQuality: analysisQuality.status === 'fulfilled' ? analysisQuality.value : null,
        health: health.status === 'fulfilled' ? health.value : null,
        loading: false,
        lastRefresh: new Date(),
        error: errorMessage,
      });
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
    const bid = typeof tick.bid === 'number' ? tick.bid : Number(tick.bid) || 0;
    const floatingPnl =
      typeof tick.floating_pnl === 'number'
        ? tick.floating_pnl
        : tick.floating_pnl != null
          ? Number(tick.floating_pnl)
          : undefined;

    const positions = get().positions.map((p) =>
      p.symbol === sym
        ? {
            ...p,
            current_price: bid,
            floating_pnl: floatingPnl,
            pnl: floatingPnl !== undefined ? floatingPnl : p.pnl,
          }
        : p
    );
    const existingQuote = get().marketQuotes[sym];
    const rawChange = tick.change_pct ?? tick.changePct ?? tick.pct_change;
    const changePct =
      typeof rawChange === 'number'
        ? rawChange
        : rawChange != null
          ? Number(rawChange) || 0
          : existingQuote && existingQuote.price > 0
            ? ((bid - existingQuote.price) / existingQuote.price) * 100
            : 0;

    const marketQuotes = {
      ...get().marketQuotes,
      [sym]: { price: bid, changePct },
    };
    set({ positions, marketQuotes });
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
      id: typeof event.id === 'number' ? event.id : Date.now(),
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


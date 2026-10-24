import React, { Suspense, useEffect, useState } from 'react';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { NAV_ITEMS } from './components/layout/navigation';
import { BreadcrumbBar } from './components/layout/BreadcrumbBar';
import { GlobalStatusBar } from './components/layout/GlobalStatusBar';
import { MobileNavDrawer } from './components/layout/MobileNavDrawer';
import { BootSequence } from './components/ui/BootSequence';
import { WindowFrame } from './components/ui/WindowFrame';
import { TickerTape } from './components/ui/TickerTape';
import { WeekendGapBanner } from './components/ui/WeekendGapBanner';
import { CockpitBar } from './components/panels/CockpitBar';
import { PositionsTable } from './components/panels/PositionsTable';
import { ActivityFeed } from './components/panels/ActivityFeed';
import { AnalysisGrid } from './components/panels/AnalysisGrid';
import { PerformancePanel } from './components/panels/PerformancePanel';
import { EdgeMetricsPanel } from './components/panels/EdgeMetricsPanel';
import { MarketDataPanel } from './components/panels/MarketDataPanel';
import { SystemPanel } from './components/panels/SystemPanel';
import { AgentChatPanel } from './components/panels/AgentChatPanel';
import { RiskPanel } from './components/panels/RiskPanel';

const ObservabilityPanel = React.lazy(() => import('./components/panels/ObservabilityPanel').then(m => ({ default: m.ObservabilityPanel })));
const TokenAuditPanel = React.lazy(() => import('./components/panels/TokenAuditPanel').then(m => ({ default: m.TokenAuditPanel })));
const SignalsTriggersPanel = React.lazy(() => import('./components/panels/SignalsTriggersPanel').then(m => ({ default: m.SignalsTriggersPanel })));
const DebateOutcomesPanel = React.lazy(() => import('./components/panels/DebateOutcomesPanel').then(m => ({ default: m.DebateOutcomesPanel })));
const SessionBrowserPanel = React.lazy(() => import('./components/panels/SessionBrowserPanel').then(m => ({ default: m.SessionBrowserPanel })));
const ConfigEditorPanel = React.lazy(() => import('./components/panels/ConfigEditorPanel').then(m => ({ default: m.ConfigEditorPanel })));
const GraphVisualizerPanel = React.lazy(() => import('./components/panels/GraphVisualizerPanel').then(m => ({ default: m.GraphVisualizerPanel })));
const MemoryBrowserPanel = React.lazy(() => import('./components/panels/MemoryBrowserPanel').then(m => ({ default: m.MemoryBrowserPanel })));
const BacktestPanel = React.lazy(() => import('./components/panels/BacktestPanel').then(m => ({ default: m.BacktestPanel })));
const SkillManagerPanel = React.lazy(() => import('./components/panels/SkillManagerPanel').then(m => ({ default: m.SkillManagerPanel })));
const PluginManagerPanel = React.lazy(() => import('./components/panels/PluginManagerPanel').then(m => ({ default: m.PluginManagerPanel })));
const BenchmarkPanel = React.lazy(() => import('./components/panels/BenchmarkPanel').then(m => ({ default: m.BenchmarkPanel })));
const TerminalPanel = React.lazy(() => import('./components/panels/TerminalPanel').then(m => ({ default: m.TerminalPanel })));
import { CommandPalette } from './components/ui/CommandPalette';
import { MarkdownRenderer } from './components/ui/MarkdownRenderer';
import { useDashboardStore } from './store/dashboardStore';
import { usePolling } from './hooks/usePolling';
import { useWebSocket } from './hooks/useWebSocket';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { sounds } from './lib/soundEffects';

const OverviewTab: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
    <CockpitBar />
    <div className="overview-grid">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <PositionsTable />
        <AnalysisGrid />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <ActivityFeed />
      </div>
    </div>
  </div>
);

const PositionsTab: React.FC = () => (
  <div>
    <PositionsTable />
  </div>
);

const AnalysisTab: React.FC = () => <AnalysisGrid />;
const PerformanceTab: React.FC = () => <PerformancePanel />;
const EdgeTab: React.FC = () => <EdgeMetricsPanel />;
const RiskTab: React.FC = () => <RiskPanel />;

const BriefTab: React.FC = () => {
  const { brief } = useDashboardStore();
  if (!brief) {
    return (
      <div
        className="win-window ledger-card"
        style={{
          color: 'var(--color-ink-soft)',
          textAlign: 'center',
          padding: '36px',
          fontFamily: 'var(--font-precision)',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        — No macroeconomic intelligence brief currently archived —
      </div>
    );
  }
  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      <WindowFrame
        title="Macro Intelligence Brief — Monika Document"
        variant="salmon"
        padding="20px"
      >
        <MarkdownRenderer content={brief.content_markdown || ''} />
      </WindowFrame>
    </div>
  );
};

const MarketTab: React.FC = () => <MarketDataPanel />;
const ObservabilityTab: React.FC = () => <ObservabilityPanel />;
const GraphTab: React.FC = () => <GraphVisualizerPanel />;
const TokenAuditTab: React.FC = () => <TokenAuditPanel />;
const SignalsTriggersTab: React.FC = () => <SignalsTriggersPanel />;
const DebateOutcomesTab: React.FC = () => <DebateOutcomesPanel />;
const ChatTab: React.FC = () => <AgentChatPanel />;
const SessionsTab: React.FC = () => <SessionBrowserPanel />;
const ConfigTab: React.FC = () => <ConfigEditorPanel />;
const SystemTab: React.FC = () => <SystemPanel />;
const MemoryTab: React.FC = () => <MemoryBrowserPanel />;
const BacktestTab: React.FC = () => <BacktestPanel />;
const SkillsTab: React.FC = () => <SkillManagerPanel />;
const PluginsTab: React.FC = () => <PluginManagerPanel />;
const BenchmarkTab: React.FC = () => <BenchmarkPanel />;
const TerminalTab: React.FC = () => <TerminalPanel />;

const TAB_MAP: Record<string, React.FC> = {
  overview: OverviewTab,
  positions: PositionsTab,
  analysis: AnalysisTab,
  performance: PerformanceTab,
  edge: EdgeTab,
  risk: RiskTab,
  brief: BriefTab,
  market: MarketTab,
  observability: ObservabilityTab,
  graph: GraphTab,
  tokens: TokenAuditTab,
  signals: SignalsTriggersTab,
  debates: DebateOutcomesTab,
  chat: ChatTab,
  terminal: TerminalTab,
  sessions: SessionsTab,
  config: ConfigTab,
  system: SystemTab,
  memory: MemoryTab,
  backtest: BacktestTab,
  skills: SkillsTab,
  plugins: PluginsTab,
  benchmark: BenchmarkTab,
};

const SkeletonFallback: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
    <div className="ledger-card" style={{ height: 80, background: 'var(--color-paper-raised)' }} />
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div className="ledger-card" style={{ height: 260, background: 'var(--color-paper-raised)' }} />
        <div className="ledger-card" style={{ height: 320, background: 'var(--color-paper-raised)' }} />
      </div>
      <div className="ledger-card" style={{ height: 600, background: 'var(--color-paper-raised)' }} />
    </div>
  </div>
);

const App: React.FC = () => {
  useWebSocket();
  usePolling(5_000, 60_000);
  const { activeTab, setActiveTab, error, marketQuotes } = useDashboardStore();
  const TabComponent = TAB_MAP[activeTab] || OverviewTab;

  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [showError, setShowError] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    if (error) {
      setShowError(true);
      sounds.playAlert();
      const t = setTimeout(() => setShowError(false), 5000);
      return () => clearTimeout(t);
    }
  }, [error]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        sounds.playClick('typewriter');
        setCommandPaletteOpen((prev) => !prev);
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
      ) {
        return;
      }
      if (e.key === '1') {
        sounds.playClick('typewriter');
        setActiveTab('overview');
      } else if (e.key === '2') {
        sounds.playClick('typewriter');
        setActiveTab('graph');
      } else if (e.key === '3') {
        sounds.playClick('typewriter');
        setActiveTab('performance');
      } else if (e.key === '4') {
        sounds.playClick('typewriter');
        setActiveTab('chat');
      } else if (e.key === '5') {
        sounds.playClick('typewriter');
        setActiveTab('config');
      } else if (e.key === 't' || e.key === 'T') {
        const currentTheme = useDashboardStore.getState().theme;
        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
        useDashboardStore.getState().setTheme(nextTheme);
        sounds.playClick('toggle');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveTab]);

  // Convert marketQuotes dictionary to TickerItem array
  const tickerItems = Object.entries(marketQuotes || {}).map(([symbol, q]: [string, any]) => ({
    symbol,
    price: q.price || q.bid || q.close || 0,
    changePct: q.changePct ?? q.change_pct ?? q.pct_change ?? 0,
  }));

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--color-desktop)' }}>
      {/* 1. Dashboard Boot Sequence */}
      <BootSequence />

      {/* 2. Error Dialog Popup */}
      {showError && error && (
        <div
          className="win-window"
          style={{
            position: 'fixed',
            top: 20,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 9999,
            width: '90%',
            maxWidth: '440px',
            background: 'var(--color-paper-raised)',
            border: '2px solid var(--color-rule)',
            boxShadow: '4px 4px 0 var(--color-rule)',
            borderRadius: 'var(--radius-card)',
            overflow: 'hidden',
          }}
        >
          <div
            className="win-titlebar win-titlebar--coral"
            style={{
              padding: '4px 10px',
              borderBottom: '2px solid var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              color: 'var(--color-on-win-coral)',
              fontSize: 'var(--text-xs)',
              fontWeight: 'bold',
            }}
          >
            <span>Error — System Alert</span>
            <button
              type="button"
              className="win-control-btn"
              onClick={() => setShowError(false)}
            >
              ×
            </button>
          </div>
          <div
            style={{
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              fontSize: 'var(--text-body-sm)',
              color: 'var(--color-ink)',
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: 'var(--color-win-coral)',
                color: 'var(--color-on-win-coral)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 900,
                border: '1px solid var(--color-rule)',
                flexShrink: 0,
              }}
            >
              ✕
            </div>
            <span style={{ flex: 1 }}>{error}</span>
          </div>
        </div>
      )}

      {/* 3. Header Taskbar */}
      <Header
        onToggleMobileNav={() => setMobileNavOpen(true)}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
      />

      {/* 4. Real-time Ticker Tape Ribbon */}
      {tickerItems.length > 0 && <TickerTape items={tickerItems} />}

      {/* 5. Breadcrumb Context Bar */}
      <BreadcrumbBar />

      {/* 6. Main Content Area with Flex Layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <main style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 42px', position: 'relative' }}>
          <div style={{ maxWidth: '1600px', margin: '0 auto', width: '100%' }}>
            <WeekendGapBanner />

            {/* Persistent background panels so WebSocket & PTY sessions stay alive on tab change */}
            <div style={{ display: activeTab === 'chat' ? 'block' : 'none' }}>
              <ErrorBoundary>
                <AgentChatPanel />
              </ErrorBoundary>
            </div>
            <div style={{ display: activeTab === 'terminal' ? 'block' : 'none' }}>
              <ErrorBoundary>
                <Suspense fallback={<SkeletonFallback />}>
                  <TerminalPanel />
                </Suspense>
              </ErrorBoundary>
            </div>

            {/* All other dynamic tabs */}
            {activeTab !== 'chat' && activeTab !== 'terminal' && (
              <Suspense fallback={<SkeletonFallback />}>
                <div key={activeTab}>
                  <ErrorBoundary>
                    <TabComponent />
                  </ErrorBoundary>
                </div>
              </Suspense>
            )}
          </div>
        </main>
      </div>

      {/* 7. Global Trading Status Bar */}
      <GlobalStatusBar />

      {/* 8. Mobile Navigation Drawer */}
      <MobileNavDrawer
        isOpen={mobileNavOpen}
        activeTab={activeTab}
        tabs={NAV_ITEMS}
        onSelectTab={(id) => setActiveTab(id)}
        onClose={() => setMobileNavOpen(false)}
      />

      {/* 9. Global Command Palette (Cmd+K / Ctrl+K) */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
      />
    </div>
  );
};

export default App;

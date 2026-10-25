import React, { useState, useEffect, Suspense } from 'react';
import { Header } from './components/layout/Header';
import { BreadcrumbBar } from './components/layout/BreadcrumbBar';
import { GlobalStatusBar } from './components/layout/GlobalStatusBar';
import { MobileNavDrawer } from './components/layout/MobileNavDrawer';
import { NAV_ITEMS, WORKSPACES } from './components/layout/navigation';
import { BootSequence } from './components/ui/BootSequence';
import { CommandPalette } from './components/ui/CommandPalette';
import { KeyboardShortcutsPanel } from './components/ui/KeyboardShortcutsPanel';
import { WeekendGapBanner } from './components/ui/WeekendGapBanner';
import { ManualOrderDrawer } from './components/ui/ManualOrderDrawer';
import { AuthModal } from './components/ui/AuthModal';
import { Skeleton } from './components/ui/Skeleton';
import { Card } from './components/ui/Card';
import { Badge } from './components/ui/Badge';
import { CockpitBar } from './components/panels/CockpitBar';
import { PositionsTable } from './components/panels/PositionsTable';
import { AnalysisGrid } from './components/panels/AnalysisGrid';
import { DecisionDossierModal } from './components/panels/DecisionDossierModal';
import { PerformancePanel } from './components/panels/PerformancePanel';
import { EdgeMetricsPanel } from './components/panels/EdgeMetricsPanel';
import { MarketDataPanel } from './components/panels/MarketDataPanel';
import { ActivityFeed } from './components/panels/ActivityFeed';
import { SystemPanel } from './components/panels/SystemPanel';
import { RiskPanel } from './components/panels/RiskPanel';
import { AgentChatPanel } from './components/panels/AgentChatPanel';
import { CandlestickChart } from './components/charts/CandlestickChart';
import { getStoredToken } from './lib/api';

// Code-split heavy institutional panels
const GraphVisualizerPanel = React.lazy(() =>
  import('./components/panels/GraphVisualizerPanel').then((m) => ({ default: m.GraphVisualizerPanel }))
);
const DebateOutcomesPanel = React.lazy(() =>
  import('./components/panels/DebateOutcomesPanel').then((m) => ({ default: m.DebateOutcomesPanel }))
);
const MemoryBrowserPanel = React.lazy(() =>
  import('./components/panels/MemoryBrowserPanel').then((m) => ({ default: m.MemoryBrowserPanel }))
);
const SkillManagerPanel = React.lazy(() =>
  import('./components/panels/SkillManagerPanel').then((m) => ({ default: m.SkillManagerPanel }))
);
const BenchmarkPanel = React.lazy(() =>
  import('./components/panels/BenchmarkPanel').then((m) => ({ default: m.BenchmarkPanel }))
);
const TokenAuditPanel = React.lazy(() =>
  import('./components/panels/TokenAuditPanel').then((m) => ({ default: m.TokenAuditPanel }))
);
const BacktestPanel = React.lazy(() =>
  import('./components/panels/BacktestPanel').then((m) => ({ default: m.BacktestPanel }))
);
const SignalsTriggersPanel = React.lazy(() =>
  import('./components/panels/SignalsTriggersPanel').then((m) => ({ default: m.SignalsTriggersPanel }))
);
const ObservabilityPanel = React.lazy(() =>
  import('./components/panels/ObservabilityPanel').then((m) => ({ default: m.ObservabilityPanel }))
);
const ConfigEditorPanel = React.lazy(() =>
  import('./components/panels/ConfigEditorPanel').then((m) => ({ default: m.ConfigEditorPanel }))
);
const PluginManagerPanel = React.lazy(() =>
  import('./components/panels/PluginManagerPanel').then((m) => ({ default: m.PluginManagerPanel }))
);
const TerminalPanel = React.lazy(() =>
  import('./components/panels/TerminalPanel').then((m) => ({ default: m.TerminalPanel }))
);
const SessionBrowserPanel = React.lazy(() =>
  import('./components/panels/SessionBrowserPanel').then((m) => ({ default: m.SessionBrowserPanel }))
);

import { useDashboardStore } from './store/dashboardStore';
import { useWebSocket } from './hooks/useWebSocket';
import { usePolling } from './hooks/usePolling';
import { fmt, assessmentColor } from './lib/formatters';
import './App.css';

const App: React.FC = () => {
  const { activeTab, setActiveTab, setTheme, brief, analyses, selectedSymbol, fetchAll, setAgentSheetOpen } =
    useDashboardStore();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [manualOrderOpen, setManualOrderOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [dossierAnalysis, setDossierAnalysis] = useState<any | null>(null);
  const [showSmcChart, setShowSmcChart] = useState(false);

  // Global keyboard shortcuts (1-5 chapters, Cmd/Ctrl+K palette, T theme, ? shortcuts)
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdPaletteOpen((prev) => !prev);
        return;
      }

      const target = e.target as HTMLElement | null;
      if (
        target &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
      ) {
        return;
      }

      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setShortcutsOpen((prev) => !prev);
        return;
      }

      if (!e.metaKey && !e.ctrlKey && !e.altKey && e.key.toLowerCase() === 't') {
        e.preventDefault();
        const currTheme = useDashboardStore.getState().theme;
        setTheme(currTheme === 'dark' ? 'light' : 'dark');
        return;
      }

      if ((!e.metaKey && !e.ctrlKey) && ['1', '2', '3', '4', '5'].includes(e.key)) {
        const wsIndex = parseInt(e.key, 10) - 1;
        const targetWs = WORKSPACES[wsIndex];
        if (targetWs) {
          e.preventDefault();
          setActiveTab(targetWs.defaultTab);
        }
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [setActiveTab, setTheme]);

  // Listen for 401/403 authentication errors from api.ts
  useEffect(() => {
    const handleAuthError = () => {
      if (!getStoredToken()) {
        setAuthModalOpen(true);
      }
    };
    window.addEventListener('monika:auth-error', handleAuthError);
    return () => window.removeEventListener('monika:auth-error', handleAuthError);
  }, []);

  useWebSocket();
  usePolling();

  const latestDispatch = analyses && analyses.length > 0 ? analyses[0] : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: 'var(--color-canvas)' }}>
      {/* Tactile Matte Architectural Paper Grain & Optical Liquid Glass Refraction Filter */}
      <svg className="paper-grain-overlay" width="100%" height="100%" aria-hidden="true">
        <defs>
          <filter id="monika-editorial-grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <filter id="monika-liquid-refraction" x="-10%" y="-10%" width="120%" height="120%">
            <feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="2" result="refractNoise" />
            <feDisplacementMap in="SourceGraphic" in2="refractNoise" scale="4" xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
        <rect width="100%" height="100%" filter="url(#monika-editorial-grain)" />
      </svg>

      <BootSequence />

      <CommandPalette isOpen={cmdPaletteOpen} onClose={() => setCmdPaletteOpen(false)} />
      <KeyboardShortcutsPanel isOpen={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <ManualOrderDrawer isOpen={manualOrderOpen} onClose={() => setManualOrderOpen(false)} />
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={() => {
          setAuthModalOpen(false);
          fetchAll();
        }}
      />

      <DecisionDossierModal
        isOpen={Boolean(dossierAnalysis)}
        onClose={() => setDossierAnalysis(null)}
        analysisId={dossierAnalysis?.id}
        symbol={dossierAnalysis?.symbol}
      />

      {/* L0 Whisper Horizon Safety Bar */}
      <Header
        onOpenMobileNav={() => setMobileNavOpen(true)}
        onOpenAuthModal={() => setAuthModalOpen(true)}
        onOpenManualOrder={() => setManualOrderOpen(true)}
      />

      <MobileNavDrawer
        isOpen={mobileNavOpen}
        activeTab={activeTab}
        tabs={NAV_ITEMS}
        onSelectTab={setActiveTab}
        onClose={() => setMobileNavOpen(false)}
      />

      {/* Swiss Editorial Chapter Header & Sub-Navigation */}
      <BreadcrumbBar />

      {/* Open Architectural Canvas */}
      <main role="main" className="main-content" style={{ flex: 1 }}>
        <WeekendGapBanner />

        <Suspense
          fallback={
            <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <Skeleton height="120px" />
              <Skeleton height="360px" />
            </div>
          }
        >
          {/* CHAPTER I. CAPITAL — OVERVIEW DESK */}
          {activeTab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '36px' }}>
              {/* Sculptural Hero Equity Monument, Interactive Scrubbing Curve & Telemetry Ribbon */}
              <CockpitBar
                showSmcChart={showSmcChart}
                onToggleSmcChart={() => setShowSmcChart((prev) => !prev)}
              />

              {/* Optional Live Multi-Asset SMC Candlestick Chart Drawer */}
              {showSmcChart && (
                <section
                  className="editorial-section swiss-crosshair"
                  style={{ borderTop: '1px solid var(--color-rule)', paddingTop: '20px' }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '14px',
                    }}
                  >
                    <span className="section-kicker">
                      MULTI-ASSET SMC STRUCTURE &amp; TIMESFM FORECAST CONE · {selectedSymbol || 'EURUSD'}
                    </span>
                  </div>
                  <CandlestickChart
                    key={selectedSymbol || 'EURUSD'}
                    initialSymbol={selectedSymbol || 'EURUSD'}
                    initialTimeframe="H4"
                    height={440}
                  />
                </section>
              )}

              {/* Asymmetric 7:5 Split: Left Position Ledger (7 cols) + Right Editorial Investment Dispatch (5 cols) */}
              <div className="overview-grid">
                <div>
                  <PositionsTable />
                </div>

                <aside
                  style={{
                    borderLeft: '1px solid var(--color-rule)',
                    paddingLeft: '28px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '28px',
                  }}
                >
                  {/* Editorial Investment Dispatch Pull-Quote */}
                  <section className="editorial-section swiss-crosshair" style={{ paddingTop: '16px' }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '12px',
                      }}
                    >
                      <span className="section-kicker">LATEST INVESTMENT DISPATCH</span>
                      {latestDispatch && (
                        <Badge variant={(latestDispatch.decision || 'wait') as any}>
                          {(latestDispatch.decision || 'WAIT').toUpperCase()}
                        </Badge>
                      )}
                    </div>

                    {latestDispatch ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        <h2
                          style={{
                            margin: 0,
                            fontFamily: 'var(--font-editorial)',
                            fontSize: '26px',
                            fontWeight: 400,
                            color: 'var(--color-ink)',
                            lineHeight: 1.22,
                          }}
                        >
                          {latestDispatch.symbol} —{' '}
                          {latestDispatch.decision?.toUpperCase() === 'BUY'
                            ? 'Institutional Accumulation & Bullish Confluence'
                            : latestDispatch.decision?.toUpperCase() === 'SELL'
                            ? 'Distribution Supply Zone & Downside Asymmetry'
                            : 'Equilibrium Consolidation & Patience Protocol'}
                        </h2>

                        <blockquote
                          style={{
                            margin: 0,
                            paddingLeft: '16px',
                            borderLeft: '2px solid var(--color-ink)',
                            fontFamily: 'var(--font-editorial)',
                            fontStyle: 'italic',
                            fontSize: '18px',
                            color: 'var(--color-ink-secondary)',
                            lineHeight: 1.45,
                          }}
                        >
                          “{latestDispatch.rationale || 'Awaiting next multi-agent dialectic synthesis.'}”
                        </blockquote>

                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            paddingTop: '10px',
                            borderTop: '1px solid var(--color-rule)',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 'var(--text-xs)',
                            color: 'var(--color-ink-muted)',
                          }}
                        >
                          <span>
                            CONFIDENCE:{' '}
                            <strong style={{ color: 'var(--color-ink)' }}>
                              {latestDispatch.confidence != null
                                ? `${(latestDispatch.confidence <= 1
                                    ? latestDispatch.confidence * 100
                                    : latestDispatch.confidence
                                  ).toFixed(0)}%`
                                : '—'}
                            </strong>
                          </span>
                          <button
                            type="button"
                            onClick={() => setDossierAnalysis(latestDispatch)}
                            className="editorial-btn"
                            style={{ padding: '4px 10px' }}
                          >
                            OPEN DOSSIER →
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        style={{
                          padding: '24px 0',
                          color: 'var(--color-ink-muted)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 'var(--text-xs)',
                        }}
                      >
                        — No intelligence dispatch archived yet —
                      </div>
                    )}
                  </section>

                  {/* Macro Regime Summary */}
                  <section className="editorial-section swiss-crosshair" style={{ paddingTop: '16px' }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '10px',
                      }}
                    >
                      <span className="section-kicker">MACRO REGIME &amp; DAILY BRIEF</span>
                      <button
                        type="button"
                        onClick={() => setActiveTab('brief')}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          fontFamily: 'var(--font-mono)',
                          fontSize: 'var(--text-xs)',
                          color: 'var(--color-ink-secondary)',
                          cursor: 'pointer',
                          textDecoration: 'underline',
                        }}
                      >
                        FULL BRIEF →
                      </button>
                    </div>
                    <p
                      style={{
                        margin: 0,
                        fontSize: 'var(--text-body-sm)',
                        color: 'var(--color-ink-secondary)',
                        lineHeight: 1.6,
                      }}
                    >
                      {brief?.structured?.macro_narrative ||
                        brief?.content_markdown?.slice(0, 260) ||
                        'Macroeconomic regime monitor active. Click Full Brief to inspect cross-asset yields, FedWatch probabilities, and central bank calendar.'}
                    </p>
                  </section>
                </aside>
              </div>
            </div>
          )}

          {/* CHAPTER I SUB-VIEWS */}
          {activeTab === 'positions' && <PositionsTable />}
          {activeTab === 'signals' && <SignalsTriggersPanel />}
          {activeTab === 'market' && <MarketDataPanel />}

          {/* CHAPTER II. JOURNAL — DIALECTICS, DISPATCHES, BRIEF, DAG, MEMORY, SKILLS */}
          {activeTab === 'debates' && <DebateOutcomesPanel />}
          {activeTab === 'analysis' && <AnalysisGrid />}
          {activeTab === 'graph' && <GraphVisualizerPanel />}
          {activeTab === 'memory' && <MemoryBrowserPanel />}
          {activeTab === 'skills' && <SkillManagerPanel />}

          {activeTab === 'brief' && (
            <Card title="MACROECONOMIC INTELLIGENCE BRIEF">
              {brief ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h2 className="editorial-headline" style={{ margin: 0 }}>
                      Daily Quantitative Macro Synthesis
                    </h2>
                    <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-muted)' }}>
                      {fmt.utc(brief.generated_at)}
                    </span>
                  </div>

                  {(brief.structured?.macro_narrative || brief.content_markdown) && (
                    <blockquote
                      style={{
                        margin: 0,
                        padding: '16px 20px',
                        background: 'var(--color-well)',
                        borderLeft: '2px solid var(--color-ink)',
                        fontFamily: 'var(--font-editorial)',
                        fontSize: '20px',
                        lineHeight: 1.45,
                        color: 'var(--color-ink)',
                      }}
                    >
                      {brief.structured?.macro_narrative || brief.content_markdown}
                    </blockquote>
                  )}

                  {brief.structured?.currency_bias && (
                    <div>
                      <div className="section-kicker" style={{ marginBottom: '12px' }}>
                        CURRENCY BIAS MATRIX
                      </div>
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                          gap: '12px',
                        }}
                      >
                        {Object.entries(brief.structured.currency_bias).map(([pair, bias]) => {
                          const assessment = String(bias);
                          return (
                            <div
                              key={pair}
                              style={{
                                border: '1px solid var(--color-rule)',
                                padding: '14px',
                                background: 'var(--color-canvas)',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 'var(--text-body-md)' }}>
                                  {pair}
                                </span>
                                <span
                                  style={{
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: 'var(--text-xs)',
                                    fontWeight: 600,
                                    color: assessmentColor(assessment),
                                    textTransform: 'uppercase',
                                  }}
                                >
                                  {assessment}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--color-ink-muted)', padding: '48px', fontFamily: 'var(--font-mono)' }}>
                  No daily brief generated yet.
                </div>
              )}
            </Card>
          )}

          {/* CHAPTER III. RISK — MECHANICAL FORTRESS, GRADUATION, EDGE */}
          {activeTab === 'risk' && <RiskPanel />}
          {activeTab === 'performance' && <PerformancePanel />}
          {activeTab === 'edge' && <EdgeMetricsPanel />}

          {/* CHAPTER IV. LAB — BACKTEST, BENCHMARK, TOKENS */}
          {activeTab === 'backtest' && <BacktestPanel />}
          {activeTab === 'benchmark' && <BenchmarkPanel />}
          {activeTab === 'tokens' && <TokenAuditPanel />}

          {/* CHAPTER V. ATELIER — CONFIG, OBSERVABILITY, PLUGINS, SYSTEM, TERMINAL, SESSIONS, CHAT */}
          {activeTab === 'config' && <ConfigEditorPanel />}
          {activeTab === 'observability' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
              <ObservabilityPanel />
              <ActivityFeed />
            </div>
          )}
          {activeTab === 'plugins' && <PluginManagerPanel />}
          {activeTab === 'system' && <SystemPanel />}
          {activeTab === 'terminal' && <TerminalPanel />}
          {activeTab === 'sessions' && <SessionBrowserPanel />}
          {activeTab === 'chat' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="section-kicker">FULLSCREEN AGENT DIALOGUE &amp; TELEGRAPH CONSOLE</span>
                <button
                  type="button"
                  onClick={() => setAgentSheetOpen(true)}
                  className="editorial-btn"
                >
                  OPEN IN FLOATING DOCK SHEET
                </button>
              </div>
              <AgentChatPanel />
            </div>
          )}
        </Suspense>
      </main>

      {/* Unified Bottom Floating Command Dock + Persistent Expandable Agent Sheet */}
      <GlobalStatusBar onOpenCommandPalette={() => setCmdPaletteOpen(true)} />
    </div>
  );
};

export default App;

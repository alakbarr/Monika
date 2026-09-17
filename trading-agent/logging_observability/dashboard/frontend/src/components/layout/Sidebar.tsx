// ==============================================================================
// File: src/components/layout/Sidebar.tsx
// Description: Retro OS Workspace Navigator with 5 Desktop Folders & Custom Vector Icons
// ==============================================================================

import React, { useState } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { sounds } from '../../lib/soundEffects';
import {
  CrtMonitorIcon,
  FolderDeskIcon,
  NotebookDeskIcon,
  TelegraphDeskIcon,
  FloppyDiskIcon,
} from '../ui/RetroIcons';

export interface WorkspaceItem {
  id: string;
  code: string;
  keyNum: string;
  label: string;
  icon: React.ElementType;
  defaultTab: string;
  subTabs: { id: string; label: string }[];
}

export const WORKSPACES: WorkspaceItem[] = [
  {
    id: 'desk',
    code: 'TRD',
    keyNum: '1',
    label: 'Trading Desk',
    icon: CrtMonitorIcon,
    defaultTab: 'overview',
    subTabs: [
      { id: 'overview', label: 'Overview' },
      { id: 'positions', label: 'Position Ledger' },
      { id: 'signals', label: 'Signals & Triggers' },
      { id: 'market', label: 'Market Data' },
    ],
  },
  {
    id: 'intel',
    code: 'INT',
    keyNum: '2',
    label: 'Market Intelligence',
    icon: FolderDeskIcon,
    defaultTab: 'graph',
    subTabs: [
      { id: 'graph', label: 'Pipeline DAG Flow' },
      { id: 'debates', label: 'Debate Arbitration' },
      { id: 'analysis', label: 'Market Analysis' },
      { id: 'brief', label: 'Macroeconomic Intelligence Brief' },
    ],
  },
  {
    id: 'ledger',
    code: 'LED',
    keyNum: '3',
    label: 'Ledger & Risk',
    icon: NotebookDeskIcon,
    defaultTab: 'performance',
    subTabs: [
      { id: 'performance', label: 'P&L Performance' },
      { id: 'edge', label: 'Edge & Expectancy' },
      { id: 'risk', label: 'Risk & Limits' },
      { id: 'tokens', label: 'LLM Token Audit' },
    ],
  },
  {
    id: 'console',
    code: 'TEL',
    keyNum: '4',
    label: 'Telegraph & Desk Console',
    icon: TelegraphDeskIcon,
    defaultTab: 'chat',
    subTabs: [
      { id: 'chat', label: 'Chat' },
      { id: 'sessions', label: 'Session History' },
      { id: 'observability', label: 'Dispatch Audit Log' },
    ],
  },
  {
    id: 'system',
    code: 'SYS',
    keyNum: '5',
    label: 'System Configuration',
    icon: FloppyDiskIcon,
    defaultTab: 'config',
    subTabs: [
      { id: 'config', label: 'Configuration Settings' },
      { id: 'system', label: 'Host Diagnostics' },
    ],
  },
];

// Flat export for backwards compatibility
export interface NavItem {
  id: string;
  label: string;
  icon?: React.ElementType;
}

export const NAV_ITEMS: NavItem[] = WORKSPACES.flatMap((w) =>
  w.subTabs.map((s) => ({ id: s.id, label: s.label, icon: w.icon }))
);

export const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab, positions, overview } = useDashboardStore();
  const openPosCount = positions.filter((p) => p.status === 'open').length;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    return localStorage.getItem('monika_sidebar_collapsed') === 'true';
  });

  const toggleCollapsed = () => {
    sounds.playClick('typewriter');
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('monika_sidebar_collapsed', String(next));
      return next;
    });
  };

  // Determine active workspace based on current activeTab
  const activeWorkspace =
    WORKSPACES.find((w) => w.subTabs.some((s) => s.id === activeTab)) || WORKSPACES[0];

  const handleSelectWorkspace = (w: WorkspaceItem) => {
    sounds.playClick('typewriter');
    // If clicking a different workspace, activate its default tab
    if (!w.subTabs.some((s) => s.id === activeTab)) {
      setActiveTab(w.defaultTab);
    }
  };

  const handleSelectSubTab = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('typewriter');
    setActiveTab(tabId);
  };

  return (
    <nav
      role="navigation"
      className={`desktop-sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}
      style={{
        width: collapsed ? 'var(--sidebar-collapsed)' : 'var(--sidebar-width)',
        height: '100%',
        background: 'var(--color-paper)',
        borderRight: '2px solid var(--color-rule)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        padding: '10px 0',
        flexShrink: 0,
        fontFamily: 'var(--font-precision)',
        boxShadow: 'inset -2px 0 0 rgba(0,0,0,0.05)',
        transition: 'width 150ms cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      {/* Workspace Drawer Header with Collapse Toggle */}
      <div
        style={{
          padding: '4px 10px 8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          fontSize: 'var(--text-xs)',
          fontWeight: 'var(--weight-bold)',
          color: 'var(--color-ink)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          borderBottom: '2px solid var(--color-rule)',
          marginBottom: '8px',
        }}
      >
        {!collapsed && <span>WORKSPACES</span>}
        <button
          type="button"
          onClick={toggleCollapsed}
          className="win-control-btn"
          style={{
            width: 22,
            height: 22,
            fontSize: '11px',
            cursor: 'pointer',
          }}
          title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          aria-label={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
        >
          {collapsed ? '▶' : '◀'}
        </button>
      </div>

      {/* 5 Themed Workspace Folders */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', padding: collapsed ? '0 6px' : '0 8px' }}>
        {WORKSPACES.map((w) => {
          const isWsActive = activeWorkspace.id === w.id;
          const Icon = w.icon;
          const badge = w.id === 'desk' ? openPosCount : undefined;

          return (
            <div
              key={w.id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                borderRadius: '6px',
                border: isWsActive ? '2px solid var(--color-rule)' : '2px solid transparent',
                background: isWsActive ? 'var(--color-paper-raised)' : 'transparent',
                boxShadow: isWsActive ? '3px 3px 0 var(--color-rule)' : 'none',
                overflow: 'hidden',
                transition: 'all 120ms ease-out',
              }}
            >
              {/* Workspace Main Folder Button */}
              <button
                type="button"
                onClick={() => handleSelectWorkspace(w)}
                title={collapsed ? `[${w.keyNum}] ${w.label}` : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  gap: '8px',
                  padding: collapsed ? '10px 0' : '8px 10px',
                  background: isWsActive ? 'var(--color-win-yellow)' : 'transparent',
                  color: isWsActive ? '#1C1917' : 'var(--color-ink)',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  width: '100%',
                  fontWeight: isWsActive ? 800 : 600,
                  fontFamily: 'var(--font-precision)',
                  borderBottom: isWsActive && !collapsed ? '1.5px solid var(--color-rule)' : 'none',
                }}
              >
                <span style={{ display: 'inline-flex', flexShrink: 0, color: isWsActive ? '#1C1917' : 'var(--color-brass)' }}>
                  <Icon size={18} />
                </span>
                {!collapsed && (
                  <>
                    <span
                      style={{
                        fontSize: 'var(--text-xs)',
                        fontWeight: isWsActive ? 800 : 700,
                        letterSpacing: '0.04em',
                        flex: 1,
                        textTransform: 'uppercase',
                        color: isWsActive ? '#1C1917' : 'var(--color-ink)',
                      }}
                    >
                      [{w.keyNum}] {w.label}
                    </span>

                    {badge !== undefined && badge > 0 && (
                      <span
                        className="tabular-nums"
                        style={{
                          padding: '1px 5px',
                          fontSize: '10px',
                          fontWeight: 800,
                          background: 'var(--color-win-salmon)',
                          color: '#FAF7F2',
                          border: '1px solid var(--color-rule)',
                          borderRadius: '4px',
                        }}
                      >
                        {badge}
                      </span>
                    )}
                  </>
                )}
              </button>

              {/* Sub-tabs Drawer (visible when workspace is active and not collapsed) */}
              {isWsActive && !collapsed && (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '3px',
                    padding: '6px 8px 8px 12px',
                    background: 'var(--color-paper-raised)',
                  }}
                >
                  {w.subTabs.map((sub) => {
                    const isSubActive = activeTab === sub.id;
                    return (
                      <button
                        key={sub.id}
                        type="button"
                        onClick={(e) => handleSelectSubTab(sub.id, e)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '5px 8px',
                          border: isSubActive ? '1.5px solid var(--color-rule)' : '1.5px solid transparent',
                          borderLeft: isSubActive ? '4px solid var(--color-win-yellow)' : '4px solid transparent',
                          borderRadius: '3px',
                          background: isSubActive ? 'var(--color-paper)' : 'transparent',
                          color: 'var(--color-ink)',
                          fontWeight: isSubActive ? 800 : 500,
                          fontSize: 'var(--text-xs)',
                          cursor: 'pointer',
                          textAlign: 'left',
                          boxShadow: isSubActive ? '1.5px 1.5px 0 var(--color-rule)' : 'none',
                          transform: isSubActive ? 'translate(-1px, -1px)' : 'none',
                        }}
                      >
                        <span style={{
                          color: isSubActive ? 'var(--color-win-yellow)' : 'var(--color-ink-soft)',
                          fontSize: '11px',
                          fontWeight: 900,
                        }}>
                          {isSubActive ? '▶' : '›'}
                        </span>
                        <span>{sub.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Emergency Halt / Paused Banner */}
      {overview?.trading_paused && (
        <div
          className="win-window"
          title={overview.pause_reason || 'Order execution suspended by Risk Guardian.'}
          style={{
            margin: collapsed ? 'auto 4px 8px' : 'auto 8px 8px',
            padding: collapsed ? '6px 2px' : '10px',
            background: 'var(--color-paper-raised)',
            border: '2px solid var(--color-win-coral)',
            borderRadius: 'var(--radius-card)',
            boxShadow: '2px 2px 0 var(--color-rule)',
            textAlign: collapsed ? 'center' : 'left',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', gap: '6px', marginBottom: collapsed ? 0 : '4px' }}>
            <span
              className="win-badge"
              style={{
                color: '#FAF7F2',
                background: 'var(--color-win-coral)',
                border: '1.5px solid var(--color-rule)',
                fontSize: '10px',
                padding: '2px 4px',
              }}
            >
              {collapsed ? '!' : '[ SUSPENDED ]'}
            </span>
          </div>
          {!collapsed && (
            <div style={{ fontSize: '11px', color: 'var(--color-ink)', lineHeight: 1.3 }}>
              {overview.pause_reason || 'Order execution suspended by Risk Guardian.'}
            </div>
          )}
        </div>
      )}
    </nav>
  );
};

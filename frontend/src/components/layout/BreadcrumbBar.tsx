// ==============================================================================
// File: src/components/layout/BreadcrumbBar.tsx
// Description: Swiss Editorial Chapter Header & Sub-Navigation Strip
// ==============================================================================

import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { WORKSPACES } from './navigation';
import { sounds } from '../../lib/soundEffects';

export const BreadcrumbBar: React.FC = () => {
  const { activeTab, setActiveTab } = useDashboardStore();

  const activeWorkspace =
    WORKSPACES.find((w) => w.subTabs.some((s) => s.id === activeTab)) || WORKSPACES[0];

  const handleSelectSubTab = (tabId: string) => {
    sounds.playClick('typewriter');
    setActiveTab(tabId);
  };

  return (
    <div
      role="navigation"
      aria-label="Chapter Navigation"
      style={{
        background: 'var(--color-glass-surface)',
        backdropFilter: 'var(--glass-blur-panel)',
        WebkitBackdropFilter: 'var(--glass-blur-panel)',
        borderBottom: '1px solid var(--color-glass-border)',
        boxShadow: 'inset 0 1px 0 0 var(--color-glass-specular-top)',
        padding: '16px 32px 0 32px',
      }}
    >
      <div
        style={{
          maxWidth: '1456px',
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        {/* Editorial Chapter Title & Subtitle */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                color: 'var(--color-ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
              }}
            >
              CHAPTER {activeWorkspace.roman}
            </span>
            <h1
              style={{
                margin: 0,
                fontFamily: 'var(--font-editorial)',
                fontSize: '28px',
                fontWeight: 400,
                color: 'var(--color-ink)',
                letterSpacing: '-0.02em',
                lineHeight: 1.1,
              }}
            >
              {activeWorkspace.label}
            </h1>
            <span
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 'var(--text-body-sm)',
                color: 'var(--color-ink-muted)',
              }}
            >
              — {activeWorkspace.subtitle}
            </span>
          </div>

          {/* Quick Chapter Switcher Ribbon (I - V) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
            {WORKSPACES.map((w) => {
              const isCurrentChapter = activeWorkspace.id === w.id;
              return (
                <button
                  key={w.id}
                  type="button"
                  onClick={() => handleSelectSubTab(w.defaultTab)}
                  style={{
                    height: '26px',
                    padding: '0 10px',
                    background: isCurrentChapter ? 'var(--color-ink)' : 'var(--color-well)',
                    color: isCurrentChapter ? 'var(--color-on-inverted)' : 'var(--color-ink-secondary)',
                    border: '1px solid var(--color-glass-border)',
                    borderRadius: 'var(--radius-pill)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    fontWeight: isCurrentChapter ? 600 : 500,
                    letterSpacing: '0.05em',
                    cursor: 'pointer',
                    transition: 'all 120ms ease',
                  }}
                >
                  {w.roman}. {w.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Unboxed Editorial Sub-Tab Strip */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '24px',
            overflowX: 'auto',
          }}
        >
          {activeWorkspace.subTabs.map((sub) => {
            const isActive = activeTab === sub.id;
            return (
              <button
                key={sub.id}
                type="button"
                onClick={() => handleSelectSubTab(sub.id)}
                style={{
                  padding: '8px 0 11px 0',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: isActive
                    ? '2px solid var(--color-ink)'
                    : '2px solid transparent',
                  color: isActive ? 'var(--color-ink)' : 'var(--color-ink-muted)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: isActive ? 600 : 500,
                  textTransform: 'uppercase',
                  letterSpacing: '0.07em',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'color 120ms ease, border-color 120ms ease',
                }}
              >
                {sub.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

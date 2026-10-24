// ==============================================================================
// File: src/components/layout/GlobalStatusBar.tsx
// Description: Unified Bottom Floating Command Dock + Expandable Agent Sheet
// Monika Swiss Editorial & Unboxed Sculptural Navigation Dock
// ==============================================================================

import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { WORKSPACES } from './navigation';
import { AgentChatPanel } from '../panels/AgentChatPanel';
import { sounds } from '../../lib/soundEffects';
import { Sparkles, ChevronUp, ChevronDown, Command } from 'lucide-react';

interface GlobalStatusBarProps {
  onOpenCommandPalette?: () => void;
}

export const GlobalStatusBar: React.FC<GlobalStatusBarProps> = ({ onOpenCommandPalette }) => {
  const {
    activeTab,
    setActiveTab,
    positions,
    agentSheetOpen,
    toggleAgentSheet,
    setAgentSheetOpen,
  } = useDashboardStore();

  const openPositionsCount = positions.filter((p) => p.status === 'open').length;

  const activeWorkspace =
    WORKSPACES.find((w) => w.subTabs.some((s) => s.id === activeTab)) || WORKSPACES[0];

  const handleSelectChapter = (defaultTab: string) => {
    sounds.playClick('typewriter');
    setActiveTab(defaultTab);
  };

  return (
    <div className="floating-dock-wrapper no-print" role="navigation" aria-label="Primary Chapter Dock">
      {/* Expandable Agent Dialogue Sheet (kept mounted so WebSocket stream stays live) */}
      <div
        className="floating-dock-sheet"
        style={{
          display: agentSheetOpen ? 'block' : 'none',
          maxHeight: '68vh',
        }}
      >
        <div
          style={{
            padding: '10px 16px',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-well)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--color-ink)', letterSpacing: '0.06em' }}>
            MONIKA AUTONOMOUS DIALOGUE &amp; DIRECTIVE SHEET
          </span>
          <button
            type="button"
            onClick={() => setAgentSheetOpen(false)}
            style={{
              background: 'transparent',
              border: '1px solid var(--color-rule)',
              color: 'var(--color-ink-secondary)',
              padding: '2px 8px',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              cursor: 'pointer',
            }}
          >
            MINIMIZE [ESC]
          </button>
        </div>
        <div style={{ maxHeight: 'calc(68vh - 42px)', overflow: 'hidden' }}>
          <AgentChatPanel />
        </div>
      </div>

      {/* Floating Architectural Command Dock */}
      <div className="floating-dock-bar">
        {/* Left: 5 Editorial Chapters (I - V) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', overflowX: 'auto' }}>
          {WORKSPACES.map((w) => {
            const isActive = activeWorkspace.id === w.id;
            return (
              <button
                key={w.id}
                type="button"
                onClick={() => handleSelectChapter(w.defaultTab)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '7px',
                  height: '34px',
                  padding: '0 12px',
                  background: isActive ? 'var(--color-dock-fg)' : 'transparent',
                  color: isActive ? 'var(--color-dock-bg)' : 'var(--color-dock-fg)',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: isActive ? 600 : 500,
                  letterSpacing: '0.04em',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'background-color 120ms ease, color 120ms ease',
                }}
              >
                <span style={{ opacity: isActive ? 0.75 : 0.55 }}>{w.roman}.</span>
                <span>{w.label}</span>
                {w.id === 'capital' && openPositionsCount > 0 && (
                  <span
                    className="tabular-nums"
                    style={{
                      padding: '1px 5px',
                      fontSize: 'var(--text-xs)',
                      fontWeight: 700,
                      background: isActive ? 'var(--color-dock-bg)' : 'var(--color-gain)',
                      color: isActive ? 'var(--color-dock-fg)' : 'var(--color-dock-bg)',
                      borderRadius: 'var(--radius-xs)',
                    }}
                  >
                    {openPositionsCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Right: Expandable Agent Dialogue Trigger + Command Palette Trigger */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => {
              sounds.playClick('toggle');
              toggleAgentSheet();
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              height: '34px',
              padding: '0 14px',
              background: agentSheetOpen ? 'var(--color-gain)' : 'rgba(255, 255, 255, 0.08)',
              color: 'var(--color-dock-fg)',
              border: '1px solid var(--color-dock-rule)',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'var(--font-sans)',
              fontSize: 'var(--text-body-sm)',
              fontWeight: 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            <Sparkles size={13} />
            <span>Ask or Steer Monika…</span>
            {agentSheetOpen ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
          </button>

          {onOpenCommandPalette && (
            <button
              type="button"
              onClick={onOpenCommandPalette}
              title="Open Command Palette (⌘K / Ctrl+K)"
              aria-label="Open Command Palette"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                height: '34px',
                padding: '0 10px',
                background: 'transparent',
                color: 'var(--color-dock-muted)',
                border: '1px solid var(--color-dock-rule)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Command size={12} />
              <span>⌘K</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

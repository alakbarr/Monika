// ==============================================================================
// File: src/components/layout/Header.tsx
// Description: Retro OS Taskbar Header with Audio Feedback, Status LEDs, and Menu Bar
// ==============================================================================

import React, { useState, useEffect } from 'react';
import { StatusIndicator } from '../ui/StatusIndicator';
import { ThemeToggle } from '../ui/ThemeToggle';
import { KeyboardShortcutsPanel } from '../ui/KeyboardShortcutsPanel';
import { AudioToggleIcon } from '../ui/RetroIcons';
import { sounds } from '../../lib/soundEffects';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt, vixSentiment } from '../../lib/formatters';
import { MonikaInfiniteIcon } from '../ui/MonikaInfiniteIcon';

interface HeaderProps {
  onToggleMobileNav?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onToggleMobileNav }) => {
  const { health, overview, wsConnected } = useDashboardStore();
  const [clock, setClock] = useState(new Date());
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [isMuted, setIsMuted] = useState(sounds.getMuted());

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) return;
      if (e.key === '?') {
        e.preventDefault();
        sounds.playClick('typewriter');
        setShortcutsOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleAudioToggle = () => {
    const nextMuted = sounds.toggleMute();
    setIsMuted(nextMuted);
    if (!nextMuted) {
      sounds.playClick('bell');
    }
  };

  const vixS = overview?.vix ? vixSentiment(overview.vix) : null;

  return (
    <header
      style={{
        height: 'var(--header-height)',
        background: 'var(--color-paper-raised)',
        borderBottom: '2px solid var(--color-rule)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 14px',
        position: 'sticky',
        top: 0,
        zIndex: 100,
        fontFamily: 'var(--font-precision)',
        boxShadow: '0 2px 0 var(--color-rule)',
      }}
    >
      {/* Brand & Retro OS Menu */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {onToggleMobileNav && (
          <button
            type="button"
            onClick={onToggleMobileNav}
            className="win-btn"
            style={{
              display: 'none',
              padding: '2px 8px',
              fontSize: 'var(--text-xs)',
            }}
            id="mobile-nav-toggle"
            aria-label="Open Navigation Menu"
          >
            ☰
          </button>
        )}

        {/* Brand Lockup: 3D Möbius Emblem + Precision Wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Vintage OS Logo Stamp */}
          <div className="monika-brand-stamp">
            <MonikaInfiniteIcon size={30} glow />
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              lineHeight: 1,
              userSelect: 'none',
            }}
          >
            <span className="monika-brand-title">
              MONIKA
            </span>
            <span className="monika-brand-os">
              OS
            </span>
          </div>
        </div>
      </div>

      {/* Center: Live Ledger Status Pill */}
      {overview && (
        <div
          className="header-metrics-center"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: '30px',
            boxSizing: 'border-box',
            gap: '14px',
            fontSize: 'var(--text-xs)',
            background: 'var(--color-paper)',
            padding: '0 12px',
            borderRadius: '6px',
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>P&L:</span>
            <span
              className="tabular-nums"
              style={{
                fontWeight: 800,
                color: overview.daily_pnl >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
              }}
            >
              {overview.daily_pnl >= 0 ? '▲ +' : '▼ '}
              {fmt.usd(Math.abs(overview.daily_pnl))}
            </span>
          </div>

          <span style={{ opacity: 0.3 }}>│</span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>POSITIONS:</span>
            <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-ink)' }}>
              {overview.open_positions_count}
            </span>
          </div>

          {overview.vix && vixS && (
            <>
              <span style={{ opacity: 0.3 }}>│</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>VIX:</span>
                <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-brass)' }}>
                  {overview.vix.toFixed(1)}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* Right: Controls, Audio Synthesizer, Theme Toggle, Clock */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* Physical LED Status indicators */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: '30px',
            boxSizing: 'border-box',
            gap: '8px',
            padding: '0 8px',
            background: 'var(--color-paper)',
            border: '2px solid var(--color-rule)',
            borderRadius: '4px',
            boxShadow: '2px 2px 0 var(--color-rule)',
          }}
        >
          <StatusIndicator status={wsConnected ? 'connected' : 'disconnected'} label="WS" />
          <StatusIndicator status={health?.mt5_connected ? 'connected' : 'disconnected'} label="MT5" />
        </div>

        {/* Tactile Audio Feedback Switch */}
        <button
          type="button"
          onClick={handleAudioToggle}
          className="win-btn"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '30px',
            height: '30px',
            boxSizing: 'border-box',
            padding: 0,
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
          }}
          title={isMuted ? 'Unmute Audio Feedback' : 'Mute Audio Feedback'}
          aria-label="Toggle Typewriter Sound"
        >
          <AudioToggleIcon size={16} muted={isMuted} />
        </button>

        {/* Retro Toggle Switch (Light / Dark) */}
        <ThemeToggle />

        {/* Shortcuts Helper Key */}
        <button
          type="button"
          onClick={() => {
            sounds.playClick('typewriter');
            setShortcutsOpen(true);
          }}
          className="win-btn"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '30px',
            boxSizing: 'border-box',
            padding: '0 10px',
            fontSize: 'var(--text-xs)',
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
          }}
          title="Keyboard Shortcuts Reference (?)"
        >
          [ ? ]
        </button>

        {/* Clock UTC */}
        <div
          className="tabular-nums"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: '30px',
            boxSizing: 'border-box',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink)',
            fontWeight: 700,
            background: 'var(--color-paper)',
            padding: '0 10px',
            border: '2px solid var(--color-rule)',
            borderRadius: 'var(--radius-md)',
            boxShadow: '2px 2px 0 var(--color-rule)',
          }}
        >
          {clock.toUTCString().slice(17, 25)} UTC
        </div>
      </div>

      <KeyboardShortcutsPanel
        isOpen={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </header>
  );
};

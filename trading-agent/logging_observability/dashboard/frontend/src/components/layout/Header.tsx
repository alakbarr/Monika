// ==============================================================================
// File: src/components/layout/Header.tsx
// Description: Dashboard Taskbar Header with Audio Feedback, Status LEDs, and Menu Bar
// ==============================================================================

import React, { useState, useEffect } from 'react';
import { StatusIndicator } from '../ui/StatusIndicator';
import { ThemeToggle } from '../ui/ThemeToggle';
import { KeyboardShortcutsPanel } from '../ui/KeyboardShortcutsPanel';
import { AudioToggleIcon } from '../ui/Icons';
import { sounds } from '../../lib/soundEffects';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt, vixSentiment } from '../../lib/formatters';
import { MonikaInfiniteIcon } from '../ui/MonikaInfiniteIcon';

interface HeaderProps {
  onToggleMobileNav?: () => void;
  onOpenCommandPalette?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onToggleMobileNav, onOpenCommandPalette }) => {
  const { health, overview, wsConnected, timeZoneDisplay, setTimeZoneDisplay } = useDashboardStore();
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
      {/* Brand & Workspace Menu */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {onToggleMobileNav && (
          <button
            type="button"
            onClick={onToggleMobileNav}
            className="win-btn"
            style={{
              display: 'none',
              padding: '6px 12px',
              minHeight: '36px',
              minWidth: '36px',
              fontSize: 'var(--text-body-md)',
              cursor: 'pointer',
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

        {/* L0 Safety Mode Pill */}
        <div
          className={`monika-mode-pill ${overview?.is_live ? 'monika-mode-pill--live' : 'monika-mode-pill--paper'}`}
          title={overview?.is_live ? 'LIVE REAL-CAPITAL TRADING ACTIVE' : 'Simulated Paper Trading Mode'}
        >
          <span style={{ fontSize: '9px' }}>■</span>
          <span>{overview?.is_live ? 'LIVE TRADING' : 'PAPER TRADING'}</span>
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
            minWidth: '36px',
            minHeight: '36px',
            boxSizing: 'border-box',
            padding: '4px',
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
            cursor: 'pointer',
          }}
          title={isMuted ? 'Unmute Audio Feedback' : 'Mute Audio Feedback'}
          aria-label="Toggle Typewriter Sound"
        >
          <AudioToggleIcon size={18} muted={isMuted} />
        </button>

        {/* Retro Toggle Switch (Light / Dark) */}
        <ThemeToggle />

        {/* Command Palette Launcher */}
        <button
          type="button"
          onClick={() => {
            sounds.playClick('typewriter');
            onOpenCommandPalette?.();
          }}
          className="win-btn"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '36px',
            boxSizing: 'border-box',
            padding: '0 10px',
            fontSize: 'var(--text-body-sm)',
            fontWeight: 700,
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
            cursor: 'pointer',
          }}
          title="Command Palette (Cmd+K / Ctrl+K)"
          aria-label="Open Command Palette"
        >
          ⌘K
        </button>

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
            minHeight: '36px',
            boxSizing: 'border-box',
            padding: '0 12px',
            fontSize: 'var(--text-body-sm)',
            fontWeight: 700,
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
            cursor: 'pointer',
          }}
          title="Keyboard Shortcuts Reference (?)"
          aria-label="Open Keyboard Shortcuts Reference"
        >
          [ ? ]
        </button>

        {/* Interactive Clock UTC / LOCAL Switcher */}
        <button
          type="button"
          onClick={() => {
            sounds.playClick('toggle');
            const nextTz = timeZoneDisplay === 'UTC' ? 'LOCAL' : 'UTC';
            setTimeZoneDisplay(nextTz);
          }}
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
            cursor: 'pointer',
            fontFamily: 'var(--font-precision)',
          }}
          title={`Click to toggle UTC / Local time (Active: ${timeZoneDisplay})`}
          aria-label={`Current time zone: ${timeZoneDisplay}. Click to toggle.`}
        >
          {timeZoneDisplay === 'UTC'
            ? `${clock.toUTCString().slice(17, 25)} UTC`
            : `${clock.toTimeString().slice(0, 8)} LOC`}
        </button>
      </div>

      <KeyboardShortcutsPanel
        isOpen={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </header>
  );
};

import React, { useState, useEffect } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { ThemeToggle } from '../ui/ThemeToggle';
import { ConfirmModal } from '../ui/ConfirmModal';
import { AudioToggleIcon } from '../ui/Icons';
import { MonikaInfiniteIcon } from '../ui/MonikaInfiniteIcon';
import { sounds } from '../../lib/soundEffects';
import { api } from '../../lib/api';
import { Menu, KeyRound, Plus, OctagonAlert, Play } from 'lucide-react';

interface HeaderProps {
  onOpenMobileNav?: () => void;
  onOpenAuthModal?: () => void;
  onOpenManualOrder?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onOpenMobileNav,
  onOpenAuthModal,
  onOpenManualOrder,
}) => {
  const { overview, health, wsConnected, riskState, paperStats, userRole, fetchAll } =
    useDashboardStore();
  const [utcNow, setUtcNow] = useState<Date>(() => new Date());
  const [soundMuted, setSoundMuted] = useState<boolean>(() => sounds.getMuted());
  const [killModalOpen, setKillModalOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setUtcNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleToggleSound = () => {
    const nextMuted = sounds.toggleMute();
    setSoundMuted(nextMuted);
    if (!nextMuted) sounds.playClick('toggle');
  };

  const isPaused = overview?.trading_paused ?? riskState?.trading_paused ?? false;
  const isPaper = overview?.is_live ? false : overview?.is_paper !== false;
  const totalPaperTrades = paperStats?.total_trades ?? 0;

  const handleEmergencyHaltOrResume = async () => {
    if (isPaused) {
      setActionBusy(true);
      try {
        await api.resumeTrading();
        sounds.playClick('bell');
        await fetchAll();
      } catch {
        // Handled by global error state
      } finally {
        setActionBusy(false);
      }
    } else {
      setKillModalOpen(true);
    }
  };

  const confirmEmergencyKill = async () => {
    setKillModalOpen(false);
    setActionBusy(true);
    try {
      await api.emergencyKill();
      sounds.playAlert();
      await fetchAll();
    } catch {
      // Handled by global error state
    } finally {
      setActionBusy(false);
    }
  };

  const utcTimeStr = utcNow.toISOString().slice(11, 19) + ' UTC';

  return (
    <>
      <header
        className="liquid-glass-chrome"
        style={{
          height: 'var(--header-height)',
          background: 'var(--color-glass-chrome)',
          backdropFilter: 'var(--glass-blur-chrome)',
          WebkitBackdropFilter: 'var(--glass-blur-chrome)',
          borderBottom: '1px solid var(--color-glass-border)',
          boxShadow: 'var(--shadow-glass-chrome)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          position: 'sticky',
          top: 0,
          zIndex: 200,
          gap: '16px',
        }}
      >
        {/* Left: Brand Identity & L0 Mode Pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: 0 }}>
          {onOpenMobileNav && (
            <button
              id="mobile-nav-toggle"
              type="button"
              onClick={onOpenMobileNav}
              aria-label="Open navigation menu"
              style={{
                display: 'none',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                background: 'transparent',
                border: '1px solid var(--color-rule)',
                color: 'var(--color-ink)',
                cursor: 'pointer',
              }}
            >
              <Menu size={16} />
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <MonikaInfiniteIcon size={20} />
            <span
              style={{
                fontFamily: 'var(--font-editorial)',
                fontSize: '21px',
                color: 'var(--color-ink)',
                letterSpacing: '-0.02em',
                lineHeight: 1,
              }}
            >
              Monika
            </span>
          </div>

          <span style={{ color: 'var(--color-rule)', userSelect: 'none' }}>/</span>

          {/* Unmistakable Paper vs Live Mode Badge + Graduation Gate Progress */}
          <div
            className={`monika-mode-pill ${isPaper ? 'monika-mode-pill--paper' : 'monika-mode-pill--live'}`}
            title={
              isPaper
                ? `Paper Trading Active — Graduation Gate: ${totalPaperTrades}/50 Trades`
                : 'LIVE MARKET EXECUTION ACTIVE'
            }
          >
            <span
              style={{
                width: 6,
                height: 6,
                background: isPaper ? 'var(--color-warn)' : 'var(--color-on-inverted)',
                display: 'inline-block',
              }}
            />
            <span>{isPaper ? 'PAPER' : 'LIVE'}</span>
            {isPaper && (
              <span
                className="tabular-nums"
                style={{
                  opacity: 0.85,
                  paddingLeft: '4px',
                  borderLeft: '1px solid var(--color-warn-border)',
                }}
              >
                {totalPaperTrades}/50
              </span>
            )}
          </div>

          {isPaused && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '3px 8px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                fontWeight: 600,
                color: 'var(--color-loss)',
                background: 'var(--color-loss-bg)',
                border: '1px solid var(--color-loss-border)',
                letterSpacing: '0.06em',
              }}
            >
              HALTED
            </span>
          )}
        </div>

        {/* Center: Whisper Telemetry Strip */}
        <div
          className="header-metrics-center"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '18px',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink-muted)',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                width: 6,
                height: 6,
                background: health?.mt5_connected ? 'var(--color-gain)' : 'var(--color-loss)',
                display: 'inline-block',
              }}
            />
            <span>MT5 {health?.mt5_connected ? 'SYNC' : 'OFFLINE'}</span>
          </span>

          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                width: 6,
                height: 6,
                background: health?.db_connected ? 'var(--color-gain)' : 'var(--color-loss)',
                display: 'inline-block',
              }}
            />
            <span>PGSQL</span>
          </span>

          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                width: 6,
                height: 6,
                background: wsConnected ? 'var(--color-gain)' : 'var(--color-warn)',
                display: 'inline-block',
              }}
            />
            <span>{wsConnected ? 'STREAM' : 'POLL'}</span>
          </span>

          <span className="tabular-nums" style={{ color: 'var(--color-ink-secondary)' }}>
            {utcTimeStr}
          </span>
        </div>

        {/* Right: Utility Controls, Manual Order & Guarded Emergency Halt */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <button
            type="button"
            onClick={handleToggleSound}
            title={soundMuted ? 'Unmute acoustic feedback' : 'Mute acoustic feedback'}
            aria-label={soundMuted ? 'Unmute sound' : 'Mute sound'}
            style={{
              height: '28px',
              width: '28px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
            }}
          >
            <AudioToggleIcon size={14} muted={soundMuted} />
          </button>

          {onOpenAuthModal && (
            <button
              type="button"
              onClick={onOpenAuthModal}
              title={`Authenticated Role: ${(userRole || 'viewer').toUpperCase()} — Click to configure API key`}
              style={{
                height: '28px',
                padding: '0 9px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                background: 'transparent',
                border: '1px solid var(--color-rule)',
                borderRadius: 'var(--radius-xs)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                color: 'var(--color-ink-secondary)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                cursor: 'pointer',
              }}
            >
              <KeyRound size={12} />
              <span>{userRole || 'viewer'}</span>
            </button>
          )}

          <ThemeToggle />

          {onOpenManualOrder && (
            <button
              type="button"
              onClick={onOpenManualOrder}
              className="editorial-btn"
              style={{
                height: '28px',
                padding: '0 11px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
              }}
            >
              <Plus size={13} />
              <span>NEW ORDER</span>
            </button>
          )}

          {/* Non-Negotiable L0 Safety Control: Emergency Halt / Resume */}
          <button
            id="emergency-halt-btn"
            type="button"
            disabled={actionBusy}
            onClick={handleEmergencyHaltOrResume}
            className={isPaused ? 'editorial-btn editorial-btn-primary' : 'editorial-btn editorial-btn-danger'}
            style={{
              height: '28px',
              padding: '0 12px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              letterSpacing: '0.06em',
            }}
          >
            {isPaused ? <Play size={12} /> : <OctagonAlert size={13} />}
            <span>{isPaused ? 'RESUME TRADING' : 'EMERGENCY HALT'}</span>
          </button>
        </div>
      </header>

      <ConfirmModal
        isOpen={killModalOpen}
        title="Emergency Circuit Breaker"
        actionSummary="Execute immediate portfolio liquidation & halt autonomous trading?"
        details="This dispatches an emergency kill command to the Mechanical Fortress (POST /api/v1/actions/emergency-kill), liquidating open positions and locking the RiskGate until manually resumed."
        confirmLabel="Liquidate & Halt Now"
        cancelLabel="Cancel"
        danger
        onConfirm={confirmEmergencyKill}
        onCancel={() => setKillModalOpen(false)}
      />
    </>
  );
};

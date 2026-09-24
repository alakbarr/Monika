// ==============================================================================
// File: src/components/ui/WeekendGapBanner.tsx
// Description: Weekend Gap Radar Caution Banner for MT5 Friday Close & Exposure De-risking
// ==============================================================================

import React, { useEffect, useState, useMemo } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { api } from '../../lib/api';
import { TypewriterButton } from './TypewriterButton';
import { ConfirmModal } from './ConfirmModal';
import { ShieldAlert, AlertTriangle, Clock, Zap, X } from 'lucide-react';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';

const CRYPTO_REGEX = /(BTC|ETH|SOL|XRP|DOGE|USDT|BNB|ADA|LTC)/i;

export const WeekendGapBanner: React.FC = () => {
  const { positions, fetchQuick } = useDashboardStore();
  const [now, setNow] = useState<Date>(new Date());
  const [dismissedUntil, setDismissedUntil] = useState<number | null>(null);
  const [confirmOpen, setConfirmOpen] = useState<boolean>(false);
  const [flattening, setFlattening] = useState<boolean>(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  // Update clock every second
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Filter open non-crypto positions
  const nonCryptoPositions = useMemo(() => {
    return positions.filter(
      (p) => p.status === 'open' && !CRYPTO_REGEX.test(p.symbol)
    );
  }, [positions]);

  // Compute UTC day & hour
  const utcDay = now.getUTCDay(); // 0 = Sun, 5 = Fri, 6 = Sat
  const utcHour = now.getUTCHours();
  const utcMin = now.getUTCMinutes();
  const utcSec = now.getUTCSeconds();

  // Weekend timing calculation:
  // Friday Market Close: Friday 21:00 UTC
  // Sunday Market Reopen: Sunday 21:00 UTC
  const isFriday = utcDay === 5;
  const isSaturday = utcDay === 6;
  const isSunday = utcDay === 0;

  const isFridayPreClose = isFriday && utcHour < 21;
  const isMarketClosed =
    (isFriday && utcHour >= 21) ||
    isSaturday ||
    (isSunday && utcHour < 21);

  // Show banner if:
  // 1. It is Friday (any time) or weekend closed period
  // 2. AND there are non-crypto open positions
  // 3. AND user hasn't snoozed it
  const isSnoozed = dismissedUntil !== null && Date.now() < dismissedUntil;

  if (nonCryptoPositions.length === 0 || isSnoozed) {
    return null;
  }

  // If Monday - Thursday, no weekend banner needed
  if (!isFriday && !isMarketClosed) {
    return null;
  }

  // Calculate time remaining to Friday 21:00 UTC
  let countdownStr = '';
  let isUrgent = false;

  if (isFridayPreClose) {
    const totalSecsLeft =
      (20 - utcHour) * 3600 + (59 - utcMin) * 60 + (59 - utcSec);
    const hrs = Math.floor(totalSecsLeft / 3600);
    const mins = Math.floor((totalSecsLeft % 3600) / 60);
    const secs = totalSecsLeft % 60;
    countdownStr = `${String(hrs).padStart(2, '0')}h ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`;
    isUrgent = hrs < 2; // Under 2 hours to close is critical
  } else if (isMarketClosed) {
    countdownStr = 'MARKET CLOSED (REOPENS SUN 21:00 UTC)';
    isUrgent = true;
  }

  const totalVolume = nonCryptoPositions.reduce((acc, p) => acc + (p.volume || 0), 0);
  const totalFloatingPnl = nonCryptoPositions.reduce((acc, p) => acc + (p.floating_pnl || 0), 0);

  const handleFlatten = async () => {
    setFlattening(true);
    try {
      const results = await Promise.allSettled(
        nonCryptoPositions.map((pos) =>
          api.closePosition({
            ticket: pos.mt5_ticket || pos.id,
            position_id: pos.id,
            reason: 'Weekend Gap Protocol Flatten',
          })
        )
      );
      const closedCount = results.filter((r) => r.status === 'fulfilled').length;
      const failedCount = results.filter((r) => r.status === 'rejected').length;

      if (failedCount > 0) {
        setFeedbackMsg(`Flattened ${closedCount} position(s). ${failedCount} failed to close.`);
      } else {
        setFeedbackMsg(`Successfully flattened all ${closedCount} non-crypto position(s).`);
      }
      sounds.playClick('bell');
      await fetchQuick();
    } catch (err: any) {
      setFeedbackMsg(`Partial or failed close: ${err?.message || 'Network error'}`);
    } finally {
      setFlattening(false);
      setConfirmOpen(false);
    }
  };

  const handleSnooze = () => {
    sounds.playClick('toggle');
    // Snooze for 1 hour
    setDismissedUntil(Date.now() + 3600 * 1000);
  };

  const borderVariant = isUrgent ? 'var(--color-ledger-red)' : 'var(--color-brass)';
  const bgVariant = isUrgent
    ? 'rgba(122, 46, 39, 0.12)'
    : 'rgba(232, 185, 74, 0.1)';

  return (
    <>
      <div
        className="win-window"
        style={{
          margin: '0 0 14px 0',
          padding: '10px 16px',
          background: bgVariant,
          border: `2px solid ${borderVariant}`,
          borderRadius: 'var(--radius-card)',
          boxShadow: isUrgent
            ? '0 0 12px rgba(122, 46, 39, 0.3), var(--shadow-card)'
            : 'var(--shadow-card)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          fontFamily: 'var(--font-precision)',
          animation: isUrgent ? 'pulse 2s infinite' : undefined,
        }}
      >
        {/* Left: Indicator & Headline */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: '4px',
              background: isUrgent ? 'var(--color-ledger-red)' : 'var(--color-win-yellow)',
              border: '1.5px solid var(--color-rule)',
              color: isUrgent ? '#FAF7F2' : '#1C1917',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
              flexShrink: 0,
            }}
          >
            {isUrgent ? <ShieldAlert size={20} /> : <AlertTriangle size={20} />}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  fontSize: 'var(--text-title-xs)',
                  fontWeight: 800,
                  color: isUrgent ? 'var(--color-ledger-red)' : 'var(--color-ink)',
                  letterSpacing: '0.04em',
                }}
              >
                [ WEEKEND GAP RADAR // {isMarketClosed ? 'MARKETS CLOSED' : 'FRIDAY CLOSE PROTOCOL'} ]
              </span>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  padding: '2px 6px',
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  fontWeight: 700,
                  color: isUrgent ? 'var(--color-ledger-red)' : 'var(--color-brass)',
                }}
              >
                <Clock size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                {countdownStr}
              </span>
            </div>

            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink)', marginTop: '2px' }}>
              <strong>{nonCryptoPositions.length} non-crypto position(s)</strong> active ({nonCryptoPositions.map((p) => p.symbol).join(', ')} · Total {totalVolume.toFixed(2)} lots · Floating PnL: {fmt.usd(totalFloatingPnl, true)}).
              {' '}Holding over the weekend subjects account to unhedgeable geopolitical & gap risk.
            </div>
          </div>
        </div>

        {/* Right: Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <TypewriterButton
            size="sm"
            variant="danger"
            onClick={() => setConfirmOpen(true)}
            disabled={flattening}
            title="Close all non-crypto positions immediately to avoid weekend gaps"
          >
            <Zap size={13} /> [ FLATTEN NON-CRYPTO ({nonCryptoPositions.length}) ]
          </TypewriterButton>

          <TypewriterButton
            size="sm"
            onClick={handleSnooze}
            title="Snooze warning for 1 hour"
          >
            <X size={12} /> [ SNOOZE 1H ]
          </TypewriterButton>
        </div>
      </div>

      {feedbackMsg && (
        <div
          style={{
            marginBottom: '10px',
            padding: '8px 12px',
            background: 'var(--color-paper-raised)',
            border: '1px solid var(--color-rule)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ledger-green)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{feedbackMsg}</span>
          <button
            onClick={() => setFeedbackMsg(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Confirmation Modal */}
      <ConfirmModal
        isOpen={confirmOpen}
        title="CONFIRM WEEKEND GAP FLATTEN"
        actionSummary={`You are about to close ${nonCryptoPositions.length} non-crypto position(s) to neutralize weekend gap risk.`}
        danger={true}
        confirmLabel={flattening ? 'CLOSING...' : 'CONFIRM FLATTEN'}
        cancelLabel="CANCEL"
        onConfirm={handleFlatten}
        onCancel={() => setConfirmOpen(false)}
        details={
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink)' }}>
            <p style={{ margin: '0 0 6px 0' }}>
              <strong>Positions to liquidate at market:</strong>
            </p>
            <ul style={{ paddingLeft: '20px', margin: 0 }}>
              {nonCryptoPositions.map((p) => (
                <li key={p.id}>
                  {p.symbol} · {p.direction.toUpperCase()} · {p.volume} lot(s) (PnL: {fmt.usd(p.floating_pnl || 0, true)})
                </li>
              ))}
            </ul>
          </div>
        }
      />
    </>
  );
};

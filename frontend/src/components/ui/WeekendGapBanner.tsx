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

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const nonCryptoPositions = useMemo(() => {
    return positions.filter(
      (p) => p.status === 'open' && !CRYPTO_REGEX.test(p.symbol)
    );
  }, [positions]);

  const utcDay = now.getUTCDay();
  const utcHour = now.getUTCHours();
  const utcMin = now.getUTCMinutes();
  const utcSec = now.getUTCSeconds();

  const isFriday = utcDay === 5;
  const isSaturday = utcDay === 6;
  const isSunday = utcDay === 0;

  const isFridayPreClose = isFriday && utcHour < 21;
  const isMarketClosed =
    (isFriday && utcHour >= 21) ||
    isSaturday ||
    (isSunday && utcHour < 21);

  const isSnoozed = dismissedUntil !== null && Date.now() < dismissedUntil;

  if (nonCryptoPositions.length === 0 || isSnoozed) {
    return null;
  }

  if (!isFriday && !isMarketClosed) {
    return null;
  }

  let countdownStr = '';
  let isUrgent = false;

  if (isFridayPreClose) {
    const totalSecsLeft =
      (20 - utcHour) * 3600 + (59 - utcMin) * 60 + (59 - utcSec);
    const hrs = Math.floor(totalSecsLeft / 3600);
    const mins = Math.floor((totalSecsLeft % 3600) / 60);
    const secs = totalSecsLeft % 60;
    countdownStr = `${String(hrs).padStart(2, '0')}h ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`;
    isUrgent = hrs < 2;
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
    setDismissedUntil(Date.now() + 3600 * 1000);
  };

  const borderVariant = isUrgent ? 'var(--color-loss)' : 'var(--color-warning)';
  const bgVariant = isUrgent ? 'var(--color-loss-soft)' : 'var(--color-warning-soft)';

  return (
    <>
      <div
        style={{
          margin: '0 0 14px 0',
          padding: '10px 16px',
          background: bgVariant,
          border: `1px solid ${borderVariant}`,
          borderRadius: '2px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          fontFamily: 'var(--font-sans)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '2px',
              background: isUrgent ? 'var(--color-loss)' : 'var(--color-warning)',
              color: 'var(--color-surface)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {isUrgent ? <ShieldAlert size={18} /> : <AlertTriangle size={18} />}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  fontWeight: 600,
                  color: isUrgent ? 'var(--color-loss)' : 'var(--color-ink)',
                  letterSpacing: '0.06em',
                }}
              >
                WEEKEND GAP RADAR · {isMarketClosed ? 'MARKETS CLOSED' : 'FRIDAY CLOSE PROTOCOL'}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  padding: '1px 6px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '2px',
                  fontWeight: 600,
                  color: isUrgent ? 'var(--color-loss)' : 'var(--color-warning)',
                }}
              >
                <Clock size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                {countdownStr}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: 'var(--color-ink)', marginTop: '2px' }}>
              <strong>{nonCryptoPositions.length} non-crypto position(s)</strong> active ({nonCryptoPositions.map((p) => p.symbol).join(', ')} · Total {totalVolume.toFixed(2)} lots · Floating PnL: {fmt.usd(totalFloatingPnl, true)}).
              {' '}Holding over the weekend subjects account to unhedgeable gap risk.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <TypewriterButton
            size="sm"
            variant="danger"
            onClick={() => setConfirmOpen(true)}
            disabled={flattening}
            title="Close all non-crypto positions immediately to avoid weekend gaps"
          >
            <Zap size={12} /> FLATTEN NON-CRYPTO ({nonCryptoPositions.length})
          </TypewriterButton>

          <TypewriterButton
            size="sm"
            onClick={handleSnooze}
            title="Snooze warning for 1 hour"
          >
            <X size={12} /> SNOOZE 1H
          </TypewriterButton>
        </div>
      </div>

      {feedbackMsg && (
        <div
          style={{
            marginBottom: '10px',
            padding: '8px 12px',
            background: 'var(--color-surface-well)',
            border: '1px solid var(--color-border)',
            borderRadius: '2px',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-profit)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{feedbackMsg}</span>
          <button
            onClick={() => setFeedbackMsg(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-ink-muted)' }}
          >
            ✕
          </button>
        </div>
      )}

      <ConfirmModal
        isOpen={confirmOpen}
        title="CONFIRM WEEKEND GAP FLATTEN"
        actionSummary={`You are about to close ${nonCryptoPositions.length} non-crypto position(s) to neutralize weekend gap risk.`}
        danger={true}
        confirmLabel={flattening ? 'CLOSING…' : 'CONFIRM FLATTEN'}
        cancelLabel="CANCEL"
        onConfirm={handleFlatten}
        onCancel={() => setConfirmOpen(false)}
        details={
          <div style={{ fontSize: '12px', color: 'var(--color-ink)' }}>
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

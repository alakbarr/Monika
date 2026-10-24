import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Badge } from './Badge';
import { TypewriterButton } from './TypewriterButton';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';
import { ShieldAlert, Clock, ArrowRight, X } from 'lucide-react';

export interface TradeApprovalRequest {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  volume: number;
  entry_price?: number;
  sl?: number;
  tp?: number;
  risk_usd?: number;
  risk_pct?: number;
  confluence_score?: number;
  debate_verdict?: string;
  reason?: string;
  ttl_seconds?: number;
}

interface ApprovalModalProps {
  isOpen: boolean;
  request: TradeApprovalRequest | null;
  onAllowOnce: (id: string) => void;
  onAllowSession: (id: string) => void;
  onDeny: (id: string) => void;
  onClose: () => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  isOpen,
  request,
  onAllowOnce,
  onAllowSession,
  onDeny,
  onClose,
}) => {
  const initialTTL = request?.ttl_seconds ?? 120;
  const [timeLeft, setTimeLeft] = useState<number>(initialTTL);
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const onDenyRef = React.useRef(onDeny);
  onDenyRef.current = onDeny;

  useEffect(() => {
    if (isOpen && request) {
      setTimeLeft(request.ttl_seconds ?? 120);
    }
  }, [isOpen, request]);

  useEffect(() => {
    if (!isOpen || !request) return;
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          setTimeout(() => onDenyRef.current(request.id), 0);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isOpen, request]);

  useEffect(() => {
    if (!isOpen || !request) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
      ) {
        return;
      }
      if (e.key === '1') {
        e.preventDefault();
        sounds.playClick('bell');
        onAllowOnce(request.id);
      } else if (e.key === '2') {
        e.preventDefault();
        sounds.playClick('bell');
        onAllowSession(request.id);
      } else if (e.key === '3' || e.key === 'Escape') {
        e.preventDefault();
        sounds.playClick('toggle');
        onDeny(request.id);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, request, onAllowOnce, onAllowSession, onDeny]);

  if (!isOpen || !request) return null;

  const isBuy = request.direction.toLowerCase() === 'buy';
  const slDist = request.entry_price && request.sl ? Math.abs(request.entry_price - request.sl) : null;
  const tpDist = request.entry_price && request.tp ? Math.abs(request.entry_price - request.tp) : null;
  const rrRatio = slDist && tpDist && slDist > 0 ? (tpDist / slDist).toFixed(2) : null;
  const ttlProgress = Math.max(0, Math.min(100, (timeLeft / initialTTL) * 100));

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="approval-modal-title"
      className="retro-modal-scrim"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-strong)',
          boxShadow: 'var(--shadow-modal)',
          borderRadius: '2px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          id="approval-modal-title"
          style={{
            background: 'var(--color-surface-well)',
            color: 'var(--color-ink)',
            padding: '10px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--color-border)',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: '11px',
            letterSpacing: '0.08em',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldAlert size={14} />
            <span>OPERATOR HUMAN-IN-THE-LOOP APPROVAL REQUIRED</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-ink-muted)',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={15} />
          </button>
        </div>

        {/* TTL Dynamic Progress Bar */}
        <div style={{ width: '100%', height: '3px', background: 'var(--color-border)', position: 'relative' }}>
          <div
            style={{
              width: `${ttlProgress}%`,
              height: '100%',
              background: timeLeft < 30 ? 'var(--color-loss)' : 'var(--color-profit)',
              transition: 'width 1s linear',
            }}
          />
        </div>

        {/* Modal Body */}
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '20px', fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-ink)' }}>
                  {request.symbol}
                </span>
                <Badge variant={isBuy ? 'buy' : 'sell'}>
                  {request.direction.toUpperCase()}
                </Badge>
                <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-muted)', fontWeight: 600 }}>
                  {fmt.lots(request.volume)} Lots
                </span>
              </div>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)', marginTop: '4px' }}>
                Action Ticket #{request.id}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)', color: timeLeft < 30 ? 'var(--color-loss)' : 'var(--color-ink-muted)' }}>
              <Clock size={13} />
              <span className="tabular-nums" style={{ fontWeight: 600 }}>
                Expires in {timeLeft}s
              </span>
            </div>
          </div>

          {/* Visual Order Risk/Reward Ladder */}
          <div
            style={{
              background: 'var(--color-surface-well)',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--color-ink-muted)', letterSpacing: '0.06em' }}>
              <span>Stop Loss (SL)</span>
              <span>Proposed Entry</span>
              <span>Take Profit (TP)</span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '4px',
                alignItems: 'center',
                background: 'var(--color-surface)',
                padding: '8px 12px',
                border: '1px solid var(--color-border)',
                borderRadius: '2px',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--color-loss)', fontWeight: 600, fontSize: '13px' }}>
                  {fmt.price(request.sl, request.symbol)}
                </span>
                <ArrowRight size={12} color="var(--color-ink-muted)" />
                <span style={{ color: 'var(--color-ink)', fontWeight: 600, fontSize: '13px' }}>
                  {fmt.price(request.entry_price, request.symbol)}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
                <ArrowRight size={12} color="var(--color-ink-muted)" />
                <span style={{ color: 'var(--color-profit)', fontWeight: 600, fontSize: '13px' }}>
                  {fmt.price(request.tp, request.symbol)}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
              <div>
                <span style={{ color: 'var(--color-ink-muted)' }}>Risk: </span>
                <span style={{ fontWeight: 600, color: 'var(--color-loss)' }}>
                  {request.risk_usd ? fmt.usd(request.risk_usd) : '—'}
                  {request.risk_pct ? ` (${request.risk_pct.toFixed(2)}%)` : ''}
                </span>
              </div>
              {rrRatio && (
                <div style={{ fontWeight: 600, color: 'var(--color-ink)' }}>
                  R:R Ratio <span style={{ color: 'var(--color-profit)' }}>1 : {rrRatio}</span>
                </div>
              )}
              {request.confluence_score !== undefined && (
                <div>
                  <span style={{ color: 'var(--color-ink-muted)' }}>Confluence: </span>
                  <span style={{ fontWeight: 600, color: 'var(--color-ink)' }}>
                    {request.confluence_score}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {(request.debate_verdict || request.reason) && (
            <div
              style={{
                fontSize: '12px',
                color: 'var(--color-ink)',
                background: 'var(--color-surface-well)',
                border: '1px solid var(--color-border)',
                borderRadius: '2px',
                padding: '10px 12px',
                lineHeight: 1.5,
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, marginBottom: '4px', color: 'var(--color-ink-muted)' }}>
                SPECIALIST DEBATE VERDICT
              </div>
              <div>{request.debate_verdict || request.reason}</div>
            </div>
          )}

          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)', textAlign: 'center' }}>
            Price drift guard active: Execution auto-aborts if market drifts &gt;0.15% before submission.
          </div>
        </div>

        <div
          style={{
            background: 'var(--color-surface-well)',
            padding: '12px 20px',
            borderTop: '1px solid var(--color-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', gap: '8px' }}>
            <TypewriterButton
              variant="primary"
              onClick={() => {
                sounds.playClick('bell');
                onAllowOnce(request.id);
              }}
            >
              [1] ALLOW ONCE
            </TypewriterButton>

            <TypewriterButton
              variant="secondary"
              onClick={() => {
                sounds.playClick('bell');
                onAllowSession(request.id);
              }}
            >
              [2] ALLOW SESSION (4H)
            </TypewriterButton>
          </div>

          <TypewriterButton
            variant="danger"
            onClick={() => {
              sounds.playClick('toggle');
              onDeny(request.id);
            }}
          >
            [3 / ESC] DENY
          </TypewriterButton>
        </div>
      </div>
    </div>,
    document.body
  );
};

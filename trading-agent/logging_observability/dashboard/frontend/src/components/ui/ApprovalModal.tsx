// ==============================================================================
// File: src/components/ui/ApprovalModal.tsx
// Description: Interactive HITL Trade Approval Modal with Visual R:R Ladder & TTL Timer
// ==============================================================================

import React, { useEffect, useState } from 'react';
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

  // Reset timer on new request
  useEffect(() => {
    if (isOpen && request) {
      setTimeLeft(request.ttl_seconds ?? 120);
    }
  }, [isOpen, request]);

  // Countdown TTL loop
  useEffect(() => {
    if (!isOpen || !request || timeLeft <= 0) return;
    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          onDeny(request.id);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isOpen, request, timeLeft, onDeny]);

  // Keyboard shortcut listener (1: Allow Once, 2: Allow Session, 3/Esc: Deny)
  useEffect(() => {
    if (!isOpen || !request) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '1') {
        sounds.playClick('bell');
        onAllowOnce(request.id);
      } else if (e.key === '2') {
        sounds.playClick('bell');
        onAllowSession(request.id);
      } else if (e.key === '3' || e.key === 'Escape') {
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

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(20, 18, 14, 0.82)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <div
        className="win-window"
        style={{
          width: '100%',
          maxWidth: '560px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          boxShadow: '6px 6px 0 rgba(0, 0, 0, 0.45)',
          borderRadius: 'var(--radius-card)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Retro Dialog Title Bar */}
        <div
          className="win-titlebar"
          style={{
            background: 'var(--color-win-yellow)',
            color: '#1C1917',
            padding: '6px 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '2px solid var(--color-rule)',
            fontWeight: 700,
            fontSize: 'var(--text-xs)',
            letterSpacing: '0.05em',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldAlert size={16} />
            <span>OPERATOR HUMAN-IN-THE-LOOP APPROVAL REQUIRED</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: '#1C1917',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* TTL Dynamic Progress Bar */}
        <div style={{ width: '100%', height: '4px', background: 'var(--color-rule)', position: 'relative' }}>
          <div
            style={{
              width: `${ttlProgress}%`,
              height: '100%',
              background: timeLeft < 30 ? 'var(--color-ledger-red)' : 'var(--color-ledger-green)',
              transition: 'width 1s linear',
            }}
          />
        </div>

        {/* Modal Body */}
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Header proposal overview */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-ink)' }}>
                  {request.symbol}
                </span>
                <Badge variant={isBuy ? 'buy' : 'sell'}>
                  {request.direction.toUpperCase()}
                </Badge>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-ink-muted)', fontWeight: 600 }}>
                  {fmt.lots(request.volume)} Lots
                </span>
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', marginTop: '4px' }}>
                Action Ticket #{request.id}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-xs)', color: timeLeft < 30 ? 'var(--color-ledger-red)' : 'var(--color-ink-muted)' }}>
              <Clock size={14} />
              <span className="tabular-nums" style={{ fontWeight: 700 }}>
                Expires in {timeLeft}s
              </span>
            </div>
          </div>

          {/* Visual Order Risk/Reward Ladder */}
          <div
            style={{
              background: 'var(--color-surface-card)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: '3px',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', textTransform: 'uppercase', color: 'var(--color-ink-muted)', letterSpacing: '0.04em' }}>
              <span>Stop Loss (SL)</span>
              <span>Proposed Entry</span>
              <span>Take Profit (TP)</span>
            </div>

            {/* Ladder Bar */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '4px',
                alignItems: 'center',
                background: 'var(--color-paper)',
                padding: '8px 12px',
                border: '1px solid var(--color-rule)',
                borderRadius: '3px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--color-ledger-red)', fontWeight: 700, fontSize: '13px' }}>
                  {fmt.price(request.sl, request.symbol)}
                </span>
                <ArrowRight size={12} color="var(--color-ink-muted)" />
                <span style={{ color: 'var(--color-ink)', fontWeight: 700, fontSize: '13px' }}>
                  {fmt.price(request.entry_price, request.symbol)}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'flex-end' }}>
                <ArrowRight size={12} color="var(--color-ink-muted)" />
                <span style={{ color: 'var(--color-ledger-green)', fontWeight: 700, fontSize: '13px' }}>
                  {fmt.price(request.tp, request.symbol)}
                </span>
              </div>
            </div>

            {/* Key Ratios */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)' }}>
              <div>
                <span style={{ color: 'var(--color-ink-muted)' }}>Risk: </span>
                <span style={{ fontWeight: 700, color: 'var(--color-ledger-red)' }}>
                  {request.risk_usd ? fmt.usd(request.risk_usd) : '—'}
                  {request.risk_pct ? ` (${request.risk_pct.toFixed(2)}%)` : ''}
                </span>
              </div>
              {rrRatio && (
                <div style={{ fontWeight: 700, color: 'var(--color-ink)' }}>
                  R:R Ratio <span style={{ color: 'var(--color-ledger-green)' }}>1 : {rrRatio}</span>
                </div>
              )}
              {request.confluence_score !== undefined && (
                <div>
                  <span style={{ color: 'var(--color-ink-muted)' }}>Confluence: </span>
                  <span style={{ fontWeight: 700, color: 'var(--color-brass)' }}>
                    {request.confluence_score}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* AI Reasoning / Debate Verdict */}
          {(request.debate_verdict || request.reason) && (
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--color-ink)',
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
                borderRadius: '3px',
                padding: '10px 12px',
                lineHeight: 1.5,
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: '4px', color: 'var(--color-brass)' }}>
                [ AI SPECIALIST DEBATE VERDICT ]
              </div>
              <div>{request.debate_verdict || request.reason}</div>
            </div>
          )}

          {/* Drift Guard Notice */}
          <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', textAlign: 'center' }}>
            ⚠ Price drift guard active: Execution will auto-abort if market drifts &gt;0.15% before submission.
          </div>
        </div>

        {/* Action Buttons Bar */}
        <div
          style={{
            background: 'var(--color-paper)',
            padding: '14px 20px',
            borderTop: '2px solid var(--color-rule)',
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
    </div>
  );
};

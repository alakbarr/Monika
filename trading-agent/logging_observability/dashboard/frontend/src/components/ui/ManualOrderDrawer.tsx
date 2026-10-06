import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../lib/api';
import { sounds } from '../../lib/soundEffects';
import { X, ArrowUpRight, ArrowDownRight, ShieldCheck, AlertTriangle } from 'lucide-react';

interface ManualOrderDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  initialSymbol?: string;
  onOrderSuccess?: () => void;
}

const POPULAR_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'BTCUSD', 'XTIUSD'];

export const ManualOrderDrawer: React.FC<ManualOrderDrawerProps> = ({
  isOpen,
  onClose,
  initialSymbol = 'EURUSD',
  onOrderSuccess,
}) => {
  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [orderType, setOrderType] = useState<string>('buy');
  const [volume, setVolume] = useState<number>(0.1);
  const [price, setPrice] = useState<string>('');
  const [sl, setSl] = useState<string>('');
  const [tp, setTp] = useState<string>('');
  const [comment, setComment] = useState<string>('Manual:Dashboard');

  const [preview, setPreview] = useState<{
    risk_amount?: number;
    reward_amount?: number;
    risk_reward_ratio?: number;
    sl_distance_pips?: number;
    tp_distance_pips?: number;
    passed_risk_gate?: boolean;
    violations?: string[];
  } | null>(null);

  const [loadingPreview, setLoadingPreview] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (initialSymbol) {
      setSymbol(initialSymbol);
    }
  }, [initialSymbol]);

  useEffect(() => {
    setOrderType(direction === 'BUY' ? 'buy' : 'sell');
  }, [direction]);

  // Fetch live market preview
  const fetchPreview = useCallback(async () => {
    if (!isOpen || !symbol || volume <= 0) return;
    setLoadingPreview(true);
    try {
      const res = await api.previewManualOrder({
        symbol,
        direction: direction.toLowerCase() as 'buy' | 'sell',
        volume,
        price: price ? parseFloat(price) : undefined,
        sl: sl ? parseFloat(sl) : undefined,
        tp: tp ? parseFloat(tp) : undefined,
      });

      setPreview({
        risk_amount: (res as any).estimated_risk_usd ?? (res as any).risk_amount,
        reward_amount: (res as any).estimated_reward_usd ?? (res as any).reward_amount,
        risk_reward_ratio: (res as any).rr_ratio ?? (res as any).risk_reward_ratio,
        sl_distance_pips: (res as any).sl_distance_pips,
        tp_distance_pips: (res as any).tp_distance_pips,
        passed_risk_gate: (res as any).risk_gate_allowed ?? (res as any).passed_risk_gate ?? true,
        violations: (res as any).risk_gate_reason ? [(res as any).risk_gate_reason] : (res as any).violations ?? [],
      });
    } catch {
      // preview error handled silently
    } finally {
      setLoadingPreview(false);
    }
  }, [isOpen, symbol, direction, volume, price, sl, tp]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchPreview();
    }, 350);
    return () => clearTimeout(timer);
  }, [fetchPreview]);

  // Quick pip helpers
  const handleAddPips = (target: 'sl' | 'tp', pips: number) => {
    sounds.playClick('typewriter');
    const isJpy = symbol.toUpperCase().includes('JPY');
    const pipFactor = isJpy ? 0.01 : 0.0001;
    const currentPrice = price ? parseFloat(price) : 1.0850;

    if (target === 'sl') {
      const offset = direction === 'BUY' ? -pips * pipFactor : pips * pipFactor;
      setSl((currentPrice + offset).toFixed(isJpy ? 2 : 5));
    } else {
      const offset = direction === 'BUY' ? pips * pipFactor : -pips * pipFactor;
      setTp((currentPrice + offset).toFixed(isJpy ? 2 : 5));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);
    setSubmitting(true);
    sounds.playClick('toggle');

    try {
      const res = await api.submitManualOrder({
        symbol: symbol.toUpperCase(),
        direction: direction.toLowerCase() as 'buy' | 'sell',
        order_type: orderType,
        volume,
        price: price ? parseFloat(price) : undefined,
        sl: sl ? parseFloat(sl) : undefined,
        tp: tp ? parseFloat(tp) : undefined,
        comment,
      });

      if (res.status === 'success' || (res as any).result?.success) {
        setSuccessMsg(`Order executed successfully! Ticket: ${(res as any).result?.ticket ?? res.ticket ?? 'Placed'}`);
        if (onOrderSuccess) onOrderSuccess();
        setTimeout(() => {
          onClose();
        }, 1500);
      } else {
        setErrorMsg((res as any).message || (res as any).result?.error || 'Order execution rejected.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to submit manual order.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(28, 25, 23, 0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        fontFamily: 'var(--font-precision)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="win-window"
        style={{
          width: '100%',
          maxWidth: '520px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          boxShadow: '4px 4px 0 var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Title Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            background: 'var(--color-navy)',
            color: '#FFFFFF',
            fontWeight: 800,
            fontSize: '13px',
            letterSpacing: '0.05em',
          }}
        >
          <span>MANUAL ORDER EXECUTION // TICKET ENTRY</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup form order"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#FFFFFF',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minWidth: '44px',
              minHeight: '44px',
              padding: '10px',
              margin: '-10px -4px -10px 0',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Symbol & Direction Selection */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
                SYMBOL
              </label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: '2px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 800,
                  fontSize: '13px',
                  color: 'var(--color-ink)',
                }}
              />
              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                {POPULAR_SYMBOLS.slice(0, 4).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSymbol(s)}
                    style={{
                      fontSize: '10px',
                      padding: '2px 5px',
                      background: symbol === s ? 'var(--color-navy)' : 'var(--color-paper)',
                      color: symbol === s ? '#FFFFFF' : 'var(--color-ink-soft)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: '2px',
                      cursor: 'pointer',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Direction Selector */}
            <div>
              <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
                DIRECTION
              </label>
              <div style={{ display: 'flex', height: '34px', border: '1.5px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
                <button
                  type="button"
                  onClick={() => { sounds.playClick('toggle'); setDirection('BUY'); }}
                  style={{
                    flex: 1,
                    background: direction === 'BUY' ? 'var(--color-ledger-green)' : 'var(--color-paper)',
                    color: direction === 'BUY' ? '#FFFFFF' : 'var(--color-ink)',
                    fontWeight: 800,
                    fontSize: '12px',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '4px',
                  }}
                >
                  <ArrowUpRight size={14} /> BUY
                </button>
                <button
                  type="button"
                  onClick={() => { sounds.playClick('toggle'); setDirection('SELL'); }}
                  style={{
                    flex: 1,
                    background: direction === 'SELL' ? 'var(--color-ledger-red)' : 'var(--color-paper)',
                    color: direction === 'SELL' ? '#FFFFFF' : 'var(--color-ink)',
                    fontWeight: 800,
                    fontSize: '12px',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '4px',
                  }}
                >
                  <ArrowDownRight size={14} /> SELL
                </button>
              </div>
            </div>
          </div>

          {/* Volume Lots & Preset Steppers */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink-soft)' }}>
                VOLUME (LOTS)
              </label>
              <div style={{ display: 'flex', gap: '4px' }}>
                {[0.01, 0.05, 0.1, 0.5, 1.0].map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setVolume(v)}
                    style={{
                      fontSize: '10px',
                      padding: '2px 6px',
                      background: volume === v ? 'var(--color-win-yellow)' : 'var(--color-paper)',
                      color: volume === v ? '#1C1917' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: '2px',
                      cursor: 'pointer',
                      fontWeight: 700,
                    }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={volume}
              onChange={(e) => setVolume(parseFloat(e.target.value) || 0.01)}
              style={{
                width: '100%',
                padding: '6px 10px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 800,
                fontSize: '13px',
                color: 'var(--color-ink)',
              }}
            />
          </div>

          {/* Execution Price (Optional) */}
          <div>
            <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              PRICE (LEAVE EMPTY FOR MARKET ORDER)
            </label>
            <input
              type="number"
              step="any"
              placeholder="Market Execution"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              style={{
                width: '100%',
                padding: '6px 10px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                fontFamily: 'var(--font-precision)',
                fontSize: '12px',
                color: 'var(--color-ink)',
              }}
            />
          </div>

          {/* SL & TP with Quick Pip Buttons */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            {/* Stop Loss */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ledger-red)' }}>STOP LOSS</label>
                <div style={{ display: 'flex', gap: '3px' }}>
                  {[15, 25, 40].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => handleAddPips('sl', p)}
                      style={{ fontSize: '9px', padding: '1px 4px', border: '1px solid var(--color-rule)', background: 'var(--color-paper)', cursor: 'pointer' }}
                    >
                      {p}p
                    </button>
                  ))}
                </div>
              </div>
              <input
                type="number"
                step="any"
                placeholder="Optional SL"
                value={sl}
                onChange={(e) => setSl(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: '2px',
                  fontFamily: 'var(--font-precision)',
                  fontSize: '12px',
                  color: 'var(--color-ink)',
                }}
              />
            </div>

            {/* Take Profit */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ledger-green)' }}>TAKE PROFIT</label>
                <div style={{ display: 'flex', gap: '3px' }}>
                  {[20, 40, 60].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => handleAddPips('tp', p)}
                      style={{ fontSize: '9px', padding: '1px 4px', border: '1px solid var(--color-rule)', background: 'var(--color-paper)', cursor: 'pointer' }}
                    >
                      {p}p
                    </button>
                  ))}
                </div>
              </div>
              <input
                type="number"
                step="any"
                placeholder="Optional TP"
                value={tp}
                onChange={(e) => setTp(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: '2px',
                  fontFamily: 'var(--font-precision)',
                  fontSize: '12px',
                  color: 'var(--color-ink)',
                }}
              />
            </div>
          </div>

          {/* Order Comment */}
          <div>
            <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              COMMENT / STRATEGY TAG
            </label>
            <input
              type="text"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Manual:Dashboard"
              style={{
                width: '100%',
                padding: '6px 10px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                fontFamily: 'var(--font-precision)',
                fontSize: '12px',
                color: 'var(--color-ink)',
              }}
            />
          </div>

          {/* Mathematical Risk Preview Box */}
          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              borderRadius: '2px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: 'var(--color-ink-soft)', letterSpacing: '0.05em' }}>
                REAL-TIME RISK & REWARD METRICS
              </span>
              {loadingPreview && <span style={{ fontSize: '10px', color: 'var(--color-ink-muted)' }}>Calculating...</span>}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', textAlign: 'center' }}>
              <div>
                <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', display: 'block' }}>EST. RISK</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 800, color: 'var(--color-ledger-red)' }}>
                  {preview?.risk_amount != null ? `$${preview.risk_amount.toFixed(2)}` : '—'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', display: 'block' }}>EST. REWARD</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 800, color: 'var(--color-ledger-green)' }}>
                  {preview?.reward_amount != null ? `$${preview.reward_amount.toFixed(2)}` : '—'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', display: 'block' }}>R:R RATIO</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 800, color: 'var(--color-ink)' }}>
                  {preview?.risk_reward_ratio != null ? `1:${preview.risk_reward_ratio.toFixed(2)}` : '—'}
                </span>
              </div>
            </div>

            {/* Risk Gate Status */}
            <div style={{ marginTop: '4px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
              {preview?.passed_risk_gate ? (
                <>
                  <ShieldCheck size={14} color="var(--color-ledger-green)" />
                  <span style={{ color: 'var(--color-ledger-green)', fontWeight: 700 }}>
                    Deterministic RiskGate validation passed
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle size={14} color="var(--color-ledger-red)" />
                  <span style={{ color: 'var(--color-ledger-red)', fontWeight: 700 }}>
                    {preview?.violations?.[0] || 'Risk Gate warning'}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Messages */}
          {errorMsg && (
            <div style={{ padding: '8px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--color-ledger-red)', color: 'var(--color-ledger-red)', fontSize: '12px' }}>
              {errorMsg}
            </div>
          )}
          {successMsg && (
            <div style={{ padding: '8px', background: 'rgba(34, 197, 94, 0.1)', border: '1px solid var(--color-ledger-green)', color: 'var(--color-ledger-green)', fontSize: '12px' }}>
              {successMsg}
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '10px', marginTop: '6px' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1,
                padding: '9px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                fontWeight: 700,
                fontSize: '12px',
                cursor: 'pointer',
                color: 'var(--color-ink)',
              }}
            >
              CANCEL
            </button>
            <button
              type="submit"
              disabled={submitting}
              style={{
                flex: 2,
                padding: '9px',
                background: direction === 'BUY' ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                color: '#FFFFFF',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                fontWeight: 800,
                fontSize: '12px',
                cursor: submitting ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                boxShadow: '2px 2px 0 var(--color-rule)',
              }}
            >
              {submitting ? 'EXECUTING ORDER...' : `SUBMIT ${direction} ${volume} LOTS`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

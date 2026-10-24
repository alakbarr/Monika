import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../lib/api';
import { sounds } from '../../lib/soundEffects';
import { useDashboardStore } from '../../store/dashboardStore';
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
        passed_risk_gate: (res as any).risk_gate_allowed ?? (res as any).passed_risk_gate ?? false,
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
    const symUpper = symbol.toUpperCase();
    const isJpy = symUpper.includes('JPY');
    const isGold = symUpper.includes('XAU') || symUpper.includes('GOLD');
    const isCrypto = symUpper.includes('BTC') || symUpper.includes('ETH');

    let pipFactor = 0.0001;
    let decimals = 5;
    if (isJpy) {
      pipFactor = 0.01;
      decimals = 2;
    } else if (isGold) {
      pipFactor = 0.1;
      decimals = 2;
    } else if (isCrypto) {
      pipFactor = 1.0;
      decimals = 2;
    }

    const livePrice = useDashboardStore.getState().marketQuotes[symUpper]?.price;
    const currentPrice = price ? parseFloat(price) : (livePrice ?? null);

    if (!currentPrice || isNaN(currentPrice) || currentPrice <= 0) {
      setErrorMsg(`Harga pasar terkini untuk ${symbol} belum tersedia. Masukkan harga entri terlebih dahulu.`);
      return;
    }

    if (target === 'sl') {
      const offset = direction === 'BUY' ? -pips * pipFactor : pips * pipFactor;
      setSl((currentPrice + offset).toFixed(decimals));
    } else {
      const offset = direction === 'BUY' ? pips * pipFactor : -pips * pipFactor;
      setTp((currentPrice + offset).toFixed(decimals));
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

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, submitting, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="retro-modal-scrim"
      style={{
        zIndex: 10000,
        padding: '16px',
        fontFamily: 'var(--font-sans)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="editorial-section swiss-crosshair"
        style={{
          width: '100%',
          maxWidth: '520px',
          background: 'var(--color-paper-raised)',
          border: '1px solid var(--color-rule-strong)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Editorial Title Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 18px',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-paper)',
          }}
        >
          <div>
            <div className="editorial-kicker">I. DISCRETIONARY EXECUTION</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '20px', color: 'var(--color-ink)', marginTop: '2px' }}>
              Manual Order Ticket
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup form order"
            className="editorial-btn editorial-btn--ghost"
            style={{ padding: '6px 10px' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Symbol & Direction Selection */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label className="editorial-kicker" style={{ display: 'block', marginBottom: '6px' }}>
                SYMBOL
              </label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                style={{
                  width: '100%',
                  padding: '7px 10px',
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-rule)',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 600,
                  fontSize: '13px',
                  color: 'var(--color-ink)',
                }}
              />
              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '6px' }}>
                {POPULAR_SYMBOLS.slice(0, 4).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="touch-target-expand"
                    onClick={() => setSymbol(s)}
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-precision)',
                      padding: '2px 6px',
                      background: symbol === s ? 'var(--color-ink)' : 'var(--color-paper)',
                      color: symbol === s ? 'var(--color-paper)' : 'var(--color-ink-soft)',
                      border: '1px solid var(--color-rule)',
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
              <label className="editorial-kicker" style={{ display: 'block', marginBottom: '6px' }}>
                DIRECTION
              </label>
              <div style={{ display: 'flex', height: '35px', border: '1px solid var(--color-rule)', overflow: 'hidden' }}>
                <button
                  type="button"
                  onClick={() => { sounds.playClick('toggle'); setDirection('BUY'); }}
                  style={{
                    flex: 1,
                    background: direction === 'BUY' ? 'var(--color-ledger-green)' : 'var(--color-paper)',
                    color: direction === 'BUY' ? 'var(--color-on-win-green)' : 'var(--color-ink)',
                    fontFamily: 'var(--font-precision)',
                    fontWeight: 600,
                    fontSize: '11px',
                    letterSpacing: '0.08em',
                    border: 'none',
                    borderRight: '1px solid var(--color-rule)',
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
                    color: direction === 'SELL' ? 'var(--color-on-win-coral)' : 'var(--color-ink)',
                    fontFamily: 'var(--font-precision)',
                    fontWeight: 600,
                    fontSize: '11px',
                    letterSpacing: '0.08em',
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label className="editorial-kicker">
                VOLUME (LOTS)
              </label>
              <div style={{ display: 'flex', gap: '4px' }}>
                {[0.01, 0.05, 0.1, 0.5, 1.0].map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setVolume(v)}
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-precision)',
                      padding: '2px 6px',
                      background: volume === v ? 'var(--color-ink)' : 'var(--color-paper)',
                      color: volume === v ? 'var(--color-paper)' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      cursor: 'pointer',
                      fontWeight: 600,
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
                padding: '7px 10px',
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
                fontFamily: 'var(--font-precision)',
                fontWeight: 600,
                fontSize: '13px',
                color: 'var(--color-ink)',
              }}
            />
          </div>

          {/* Execution Price (Optional) */}
          <div>
            <label className="editorial-kicker" style={{ display: 'block', marginBottom: '6px' }}>
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
                padding: '7px 10px',
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
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
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label className="editorial-kicker" style={{ color: 'var(--color-ledger-red)' }}>STOP LOSS</label>
                <div style={{ display: 'flex', gap: '3px' }}>
                  {[15, 25, 40].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => handleAddPips('sl', p)}
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-precision)',
                        padding: '1px 5px',
                        border: '1px solid var(--color-rule)',
                        background: 'var(--color-paper)',
                        color: 'var(--color-ink-soft)',
                        cursor: 'pointer',
                      }}
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
                  padding: '7px 10px',
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-rule)',
                  fontFamily: 'var(--font-precision)',
                  fontSize: '12px',
                  color: 'var(--color-ink)',
                }}
              />
            </div>

            {/* Take Profit */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label className="editorial-kicker" style={{ color: 'var(--color-ledger-green)' }}>TAKE PROFIT</label>
                <div style={{ display: 'flex', gap: '3px' }}>
                  {[20, 40, 60].map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => handleAddPips('tp', p)}
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-precision)',
                        padding: '1px 5px',
                        border: '1px solid var(--color-rule)',
                        background: 'var(--color-paper)',
                        color: 'var(--color-ink-soft)',
                        cursor: 'pointer',
                      }}
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
                  padding: '7px 10px',
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-rule)',
                  fontFamily: 'var(--font-precision)',
                  fontSize: '12px',
                  color: 'var(--color-ink)',
                }}
              />
            </div>
          </div>

          {/* Order Comment */}
          <div>
            <label className="editorial-kicker" style={{ display: 'block', marginBottom: '6px' }}>
              COMMENT / STRATEGY TAG
            </label>
            <input
              type="text"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Manual:Dashboard"
              style={{
                width: '100%',
                padding: '7px 10px',
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
                fontFamily: 'var(--font-precision)',
                fontSize: '12px',
                color: 'var(--color-ink)',
              }}
            />
          </div>

          {/* Mathematical Risk Preview Box */}
          <div
            style={{
              padding: '12px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="editorial-kicker">
                II. REAL-TIME RISK & REWARD METRICS
              </span>
              {loadingPreview && <span style={{ fontSize: '11px', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-muted)' }}>Calculating...</span>}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', textAlign: 'center', borderTop: '1px solid var(--color-rule)', borderBottom: '1px solid var(--color-rule)', padding: '8px 0' }}>
              <div>
                <span className="editorial-kicker" style={{ display: 'block', marginBottom: '2px' }}>EST. RISK</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontFamily: 'var(--font-precision)', fontWeight: 600, color: 'var(--color-ledger-red)' }}>
                  {preview?.risk_amount != null ? `$${preview.risk_amount.toFixed(2)}` : '—'}
                </span>
              </div>
              <div style={{ borderLeft: '1px solid var(--color-rule)', borderRight: '1px solid var(--color-rule)' }}>
                <span className="editorial-kicker" style={{ display: 'block', marginBottom: '2px' }}>EST. REWARD</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontFamily: 'var(--font-precision)', fontWeight: 600, color: 'var(--color-ledger-green)' }}>
                  {preview?.reward_amount != null ? `$${preview.reward_amount.toFixed(2)}` : '—'}
                </span>
              </div>
              <div>
                <span className="editorial-kicker" style={{ display: 'block', marginBottom: '2px' }}>R:R RATIO</span>
                <span className="tabular-nums" style={{ fontSize: '13px', fontFamily: 'var(--font-precision)', fontWeight: 600, color: 'var(--color-ink)' }}>
                  {preview?.risk_reward_ratio != null ? `1:${preview.risk_reward_ratio.toFixed(2)}` : '—'}
                </span>
              </div>
            </div>

            {/* Risk Gate Status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
              {preview?.passed_risk_gate ? (
                <>
                  <ShieldCheck size={14} color="var(--color-ledger-green)" />
                  <span style={{ color: 'var(--color-ledger-green)', fontWeight: 600 }}>
                    Deterministic RiskGate validation passed
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle size={14} color="var(--color-ledger-red)" />
                  <span style={{ color: 'var(--color-ledger-red)', fontWeight: 600 }}>
                    {preview?.violations?.[0] || 'Risk Gate warning'}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Messages */}
          {errorMsg && (
            <div style={{ padding: '8px 10px', background: 'var(--color-ledger-red-bg)', border: '1px solid var(--color-ledger-red)', color: 'var(--color-ledger-red)', fontSize: '12px' }}>
              {errorMsg}
            </div>
          )}
          {successMsg && (
            <div style={{ padding: '8px 10px', background: 'var(--color-ledger-green-bg)', border: '1px solid var(--color-ledger-green)', color: 'var(--color-ledger-green)', fontSize: '12px' }}>
              {successMsg}
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
            <button
              type="button"
              onClick={onClose}
              className="editorial-btn editorial-btn--ghost"
              style={{ flex: 1 }}
            >
              CANCEL
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="editorial-btn"
              style={{
                flex: 2,
                background: direction === 'BUY' ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                color: direction === 'BUY' ? 'var(--color-on-win-green)' : 'var(--color-on-win-coral)',
                borderColor: direction === 'BUY' ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                cursor: submitting ? 'not-allowed' : 'pointer',
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

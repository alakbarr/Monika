// ==============================================================================
// File: src/components/panels/DecisionDossierModal.tsx
// Description: Multi-Agent Decision Dossier & Explainability Modal (Retro-Vintage)
// ==============================================================================

import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { DecisionDossierData } from '../../types/api';
import { fmt } from '../../lib/formatters';
import { WindowFrame } from '../ui/WindowFrame';
import { FileText, Download, Check, AlertTriangle, ShieldCheck, Scale, Terminal } from 'lucide-react';

interface DecisionDossierModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysisId?: number | string | null;
  symbol?: string | null;
  ticket?: number | null;
}

export const DecisionDossierModal: React.FC<DecisionDossierModalProps> = ({
  isOpen,
  onClose,
  analysisId,
  symbol,
  ticket,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dossier, setDossier] = useState<DecisionDossierData | null>(null);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'stage1' | 'stage2' | 'stage3' | 'stage4' | 'stage5'>('all');

  useEffect(() => {
    if (!isOpen) {
      setDossier(null);
      setError(null);
      return;
    }

    const targetId = analysisId || symbol || (ticket ? String(ticket) : null);
    if (!targetId) {
      setError('No analysis ID, symbol, or ticket provided for Decision Dossier.');
      return;
    }

    setLoading(true);
    setError(null);

    api.decisionDossier(targetId, ticket || undefined)
      .then((data) => {
        setDossier(data);
      })
      .catch((err) => {
        console.error('Failed to load decision dossier:', err);
        setError(err.message || 'Failed to fetch Decision Dossier data.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, analysisId, symbol, ticket]);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleCopyReceipt = () => {
    if (!dossier) return;
    const receipt = `=== MONIKA DECISION DOSSIER RECEIPT ===
Symbol: ${dossier.symbol}
Decision: ${dossier.decision.toUpperCase()} (Confidence: ${dossier.confidence}%)
Generated: ${dossier.generated_at || 'N/A'}
Market Regime: ${dossier.market_regime}

--- STAGE 1: MACRO CONTEXT ---
Risk Sentiment: ${dossier.stage1_macro.risk_sentiment}
DXY Bias: ${dossier.stage1_macro.dxy_bias}
Volatility Regime: ${dossier.stage1_macro.volatility_regime}
Brief Age: ${dossier.stage1_macro.brief_age_hours ? `${dossier.stage1_macro.brief_age_hours}h` : 'N/A'}

--- STAGE 2: TACTICAL CONFLUENCE ---
Confluence Score: ${dossier.stage2_tactical.confluence_score ?? 'N/A'}
Priced-in Score: ${dossier.stage2_tactical.priced_in_score ?? 'N/A'}
Stop Loss: ${dossier.stop_loss ?? 'N/A'} | Take Profit: ${dossier.take_profit ?? 'N/A'}
Active Factors: ${dossier.stage2_tactical.factors.join(', ') || 'None'}

--- STAGE 3: ADVERSARIAL DEBATE ---
Judge Verdict: ${dossier.stage3_debate.judge_verdict} (Modified: ${dossier.stage3_debate.was_modified ? 'YES' : 'NO'})
Reason: ${dossier.stage3_debate.judge_reason || 'N/A'}

--- STAGE 4: RISKGATE MECHANICAL FORTRESS ---
Execution Status: ${dossier.stage4_riskgate.execution_status.toUpperCase()}
Risk Multiplier: ${dossier.stage4_riskgate.risk_multiplier}x
Notes: ${dossier.stage4_riskgate.execution_notes || 'None'}

--- STAGE 5: EXECUTION TELEMETRY & INTEGRITY ---
Ticket: ${dossier.stage5_execution.position?.ticket ?? 'N/A'}
SHA-256 Chain Valid: ${dossier.stage5_execution.integrity_valid ? 'YES' : 'FAILED'}
Latest Hash: ${dossier.stage5_execution.sha256_chain_hash || 'N/A'}
=======================================`;

    navigator.clipboard.writeText(receipt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  const handleExportJson = () => {
    if (!dossier) return;
    const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `decision-dossier-${dossier.symbol}-${dossier.analysis_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const cardStyle: React.CSSProperties = {
    background: 'var(--color-paper)',
    border: '1px solid var(--color-rule)',
    borderRadius: 'var(--radius-sm)',
    padding: '12px 14px',
    boxShadow: 'var(--shadow-card)',
  };

  const badgeStyle = (bg: string, fg: string): React.CSSProperties => ({
    background: bg,
    color: fg,
    padding: '2px 8px',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    fontFamily: 'var(--font-precision)',
    border: '1px solid var(--color-rule)',
    borderRadius: 'var(--radius-xs)',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Decision Dossier Modal"
      className="retro-modal-scrim"
      style={{
        zIndex: 1000,
        padding: '16px',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div style={{ width: '100%', maxWidth: '960px', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
        <WindowFrame
          title={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700 }}>DECISION AUDIT DOSSIER</span>
              {dossier && (
                <>
                  <span style={badgeStyle('var(--color-paper-raised)', 'var(--color-ink)')}>
                    {dossier.symbol}
                  </span>
                  <span
                    style={badgeStyle(
                      dossier.decision === 'buy'
                        ? 'var(--color-profit-bg)'
                        : dossier.decision === 'sell'
                        ? 'var(--color-loss-bg)'
                        : 'var(--color-warn-dim)',
                      dossier.decision === 'buy'
                        ? 'var(--color-text-profit)'
                        : dossier.decision === 'sell'
                        ? 'var(--color-text-loss)'
                        : 'var(--color-text-warn)'
                    )}
                  >
                    {dossier.decision.toUpperCase()} ({dossier.confidence}%)
                  </span>
                </>
              )}
            </div>
          }
          icon={<Terminal size={14} />}
          variant="blue"
          onClose={onClose}
          padding="0"
          actions={
            dossier ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  type="button"
                  onClick={handleCopyReceipt}
                  className="win-btn"
                  style={{
                    padding: '2px 8px',
                    fontSize: 'var(--text-caption)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                  title="Salin ringkasan ke clipboard"
                >
                  {copied ? <Check size={12} /> : <FileText size={12} />}
                  <span>{copied ? 'COPIED' : 'RECEIPT'}</span>
                </button>
                <button
                  type="button"
                  onClick={handleExportJson}
                  className="win-btn"
                  style={{
                    padding: '2px 8px',
                    fontSize: 'var(--text-caption)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                  title="Ekspor berkas JSON mentah"
                >
                  <Download size={12} />
                  <span>JSON</span>
                </button>
              </div>
            ) : undefined
          }
        >
          {/* Stage Filter Navigation Tabs */}
          {dossier && (
            <div
              style={{
                display: 'flex',
                gap: '4px',
                padding: '8px 16px',
                background: 'var(--color-paper)',
                borderBottom: '1px solid var(--color-rule)',
                overflowX: 'auto',
              }}
            >
              {[
                { id: 'all', label: 'ALL STAGES' },
                { id: 'stage1', label: '1. MACRO REALITY' },
                { id: 'stage2', label: '2. CONFLUENCE & SMC' },
                { id: 'stage3', label: '3. DEBATE & JUDGE' },
                { id: 'stage4', label: '4. RISKGATE FORTRESS' },
                { id: 'stage5', label: '5. TELEMETRY & HASH' },
              ].map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id as typeof activeTab)}
                    className="win-btn"
                    style={{
                      padding: '4px 10px',
                      fontSize: 'var(--text-caption)',
                      fontFamily: 'var(--font-precision)',
                      fontWeight: isActive ? 700 : 400,
                      background: isActive ? 'var(--color-win-blue)' : 'var(--color-paper-raised)',
                      color: isActive ? 'var(--color-on-win-blue)' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      boxShadow: isActive ? 'none' : 'var(--shadow-btn)',
                      transform: isActive ? 'translate(1px, 1px)' : 'none',
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          )}

          {/* Dossier Body Content */}
          <div
            style={{
              padding: '16px',
              overflowY: 'auto',
              maxHeight: 'calc(90vh - 120px)',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              background: 'var(--color-paper-raised)',
            }}
          >
            {loading && (
              <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                <p style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)' }}>
                  Menyintesis silsilah keputusan dan merekonstruksi rantai audit...
                </p>
              </div>
            )}

            {error && !loading && (
              <div
                style={{
                  ...cardStyle,
                  background: 'var(--color-loss-bg)',
                  borderColor: 'var(--color-ledger-red)',
                  color: 'var(--color-text-loss)',
                }}
              >
                <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  <AlertTriangle size={16} />
                  <span>Kesalahan Mengambil Dossier</span>
                </div>
                <div style={{ fontSize: 'var(--text-body-sm)' }}>{error}</div>
              </div>
            )}

            {dossier && !loading && (
              <>
                {/* Executive Summary Card */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: '12px',
                    padding: '12px 16px',
                    background: 'var(--color-paper)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: 'var(--radius-sm)',
                    boxShadow: 'var(--shadow-card)',
                    fontSize: 'var(--text-body-sm)',
                    fontFamily: 'var(--font-precision)',
                  }}
                >
                  <div>
                    <span style={{ color: 'var(--color-ink-soft)', display: 'block', fontSize: 'var(--text-caption)' }}>
                      ANALYSIS ID
                    </span>
                    <strong style={{ color: 'var(--color-ink)' }}>#{dossier.analysis_id}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--color-ink-soft)', display: 'block', fontSize: 'var(--text-caption)' }}>
                      MARKET REGIME
                    </span>
                    <strong style={{ color: 'var(--color-text-info)', textTransform: 'uppercase' }}>
                      {dossier.market_regime}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--color-ink-soft)', display: 'block', fontSize: 'var(--text-caption)' }}>
                      PRICE AT ANALYSIS
                    </span>
                    <strong style={{ color: 'var(--color-ink)' }}>
                      {dossier.price_at_analysis ? fmt.price(dossier.price_at_analysis, dossier.symbol) : 'N/A'}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--color-ink-soft)', display: 'block', fontSize: 'var(--text-caption)' }}>
                      EXECUTION STATUS
                    </span>
                    <strong
                      style={{
                        color:
                          dossier.stage4_riskgate.execution_status === 'approved' ||
                          dossier.stage4_riskgate.execution_status === 'executed'
                            ? 'var(--color-text-profit)'
                            : dossier.stage4_riskgate.execution_status === 'rejected' ||
                              dossier.stage4_riskgate.execution_status === 'blocked'
                            ? 'var(--color-text-loss)'
                            : 'var(--color-text-warn)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {dossier.stage4_riskgate.execution_status}
                    </strong>
                  </div>
                </div>

                {/* STAGE 1: MACRO REALITY */}
                {(activeTab === 'all' || activeTab === 'stage1') && (
                  <div style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderBottom: '1px solid var(--color-border)',
                        paddingBottom: '8px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-win-blue)' }} />
                        <strong style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', color: 'var(--color-text-info)' }}>
                          STAGE 1: MACRO REALITY
                        </strong>
                      </div>
                      {dossier.stage1_macro.brief_age_hours !== null && (
                        <span style={{ fontSize: 'var(--text-caption)', color: 'var(--color-ink-soft)' }}>
                          Usia Brief: {dossier.stage1_macro.brief_age_hours}h
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px', marginBottom: '10px' }}>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Risk Sentiment</span>
                        <strong style={{ textTransform: 'uppercase', color: 'var(--color-ink)' }}>{dossier.stage1_macro.risk_sentiment}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>DXY Bias</span>
                        <strong style={{ textTransform: 'uppercase', color: 'var(--color-text-info)' }}>{dossier.stage1_macro.dxy_bias}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Volatility Regime</span>
                        <strong style={{ textTransform: 'uppercase', color: 'var(--color-text-warn)' }}>{dossier.stage1_macro.volatility_regime}</strong>
                      </div>
                    </div>
                    {dossier.stage1_macro.summary && (
                      <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-body-sm)', lineHeight: 1.5 }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginBottom: '4px', fontWeight: 700 }}>RINGKASAN MACRO BRIEF</span>
                        {dossier.stage1_macro.summary}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 2: TACTICAL CONFLUENCE & SMC */}
                {(activeTab === 'all' || activeTab === 'stage2') && (
                  <div style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderBottom: '1px solid var(--color-border)',
                        paddingBottom: '8px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-ledger-green)' }} />
                        <strong style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', color: 'var(--color-text-profit)' }}>
                          STAGE 2: TACTICAL CONFLUENCE & SMC
                        </strong>
                      </div>
                      <div style={{ display: 'flex', gap: '12px', fontSize: 'var(--text-caption)', fontFamily: 'var(--font-precision)' }}>
                        <span>Confluence: <strong style={{ color: 'var(--color-text-profit)' }}>{dossier.stage2_tactical.confluence_score ?? 'N/A'}/100</strong></span>
                        <span>Priced-in: <strong style={{ color: 'var(--color-text-warn)' }}>{dossier.stage2_tactical.priced_in_score ?? 'N/A'}/100</strong></span>
                      </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px', marginBottom: '10px' }}>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Stop Loss</span>
                        <strong style={{ color: 'var(--color-text-loss)' }}>{dossier.stop_loss ? fmt.price(dossier.stop_loss, dossier.symbol) : 'N/A'}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Take Profit</span>
                        <strong style={{ color: 'var(--color-text-profit)' }}>{dossier.take_profit ? fmt.price(dossier.take_profit, dossier.symbol) : 'N/A'}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Invalidation Level</span>
                        <strong style={{ color: 'var(--color-text-warn)' }}>{dossier.invalidation_price ? fmt.price(dossier.invalidation_price, dossier.symbol) : (dossier.invalidation || 'N/A')}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>SSVP CDS Score</span>
                        <strong style={{ color: 'var(--color-text-info)' }}>{dossier.stage2_tactical.ssvp_cds_score ?? 'N/A'}</strong>
                      </div>
                    </div>
                    {dossier.rationale && (
                      <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-body-sm)', lineHeight: 1.5, marginBottom: '10px' }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginBottom: '4px', fontWeight: 700 }}>RASIONAL TEKNIKAL</span>
                        {dossier.rationale}
                      </div>
                    )}
                    {dossier.stage2_tactical.factors.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 700 }}>FAKTOR ALPHA:</span>
                        {dossier.stage2_tactical.factors.map((factor, idx) => (
                          <span key={idx} style={badgeStyle('var(--color-paper-raised)', 'var(--color-ink)')}>
                            {factor}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 3: ADVERSARIAL DEBATE & JUDICIAL VERDICT */}
                {(activeTab === 'all' || activeTab === 'stage3') && (
                  <div style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderBottom: '1px solid var(--color-border)',
                        paddingBottom: '8px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Scale size={16} color="var(--color-win-salmon)" />
                        <strong style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)' }}>
                          STAGE 3: ADVERSARIAL DEBATE
                        </strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-caption)' }}>
                        <span>Putusan Hakim: <strong style={{ textTransform: 'uppercase', color: 'var(--color-text-accent)' }}>{dossier.stage3_debate.judge_verdict}</strong></span>
                        {dossier.stage3_debate.was_modified && (
                          <span style={badgeStyle('var(--color-warn-dim)', 'var(--color-text-warn)')}>
                            MODIFIKASI DEBAT
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '10px', marginBottom: '10px' }}>
                      <div style={{ padding: '10px', background: 'var(--color-profit-bg)', border: '1px solid var(--color-ledger-green)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-profit)', marginBottom: '4px' }}>
                          I. TESIS BULL ADVOCATE
                        </span>
                        <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: 1.45 }}>
                          {dossier.stage3_debate.bull_thesis || 'Tidak ada catatan tesis bull.'}
                        </p>
                      </div>
                      <div style={{ padding: '10px', background: 'var(--color-loss-bg)', border: '1px solid var(--color-ledger-red)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-loss)', marginBottom: '4px' }}>
                          II. SANGGAHAN BEAR DISSENT
                        </span>
                        <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: 1.45 }}>
                          {dossier.stage3_debate.bear_dissent || 'Tidak ada catatan sanggahan bear.'}
                        </p>
                      </div>
                    </div>
                    {dossier.stage3_debate.judge_reason && (
                      <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-body-sm)', lineHeight: 1.5 }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginBottom: '4px', fontWeight: 700 }}>III. PERTIMBANGAN HAKIM</span>
                        {dossier.stage3_debate.judge_reason}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 4: MECHANICAL FORTRESS RISKGATE */}
                {(activeTab === 'all' || activeTab === 'stage4') && (
                  <div style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderBottom: '1px solid var(--color-border)',
                        paddingBottom: '8px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ShieldCheck size={16} color="var(--color-win-blue)" />
                        <strong style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', color: 'var(--color-text-info)' }}>
                          STAGE 4: RISKGATE MECHANICAL FORTRESS
                        </strong>
                      </div>
                      <span style={{ fontSize: 'var(--text-caption)', fontFamily: 'var(--font-precision)' }}>
                        Risk Multiplier: <strong style={{ color: 'var(--color-text-info)' }}>{dossier.stage4_riskgate.risk_multiplier}x</strong>
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px', marginBottom: '10px' }}>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Status Gerbang Risiko</span>
                        <strong
                          style={{
                            textTransform: 'uppercase',
                            color:
                              dossier.stage4_riskgate.execution_status === 'approved' ||
                              dossier.stage4_riskgate.execution_status === 'executed'
                                ? 'var(--color-text-profit)'
                                : 'var(--color-text-loss)',
                          }}
                        >
                          {dossier.stage4_riskgate.execution_status}
                        </strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Sumber Keputusan</span>
                        <strong style={{ color: 'var(--color-ink)' }}>{dossier.stage4_riskgate.decision_source}</strong>
                      </div>
                      <div style={{ padding: '8px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)' }}>
                        <span style={{ color: 'var(--color-ink-soft)', fontSize: 'var(--text-caption)', display: 'block' }}>Supresi SSVP</span>
                        <strong style={{ color: dossier.stage4_riskgate.was_ssvp_suppressed ? 'var(--color-text-warn)' : 'var(--color-ink)' }}>
                          {dossier.stage4_riskgate.was_ssvp_suppressed ? 'TERSUPRESI' : 'BERSIH'}
                        </strong>
                      </div>
                    </div>
                    {dossier.stage4_riskgate.execution_notes && (
                      <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-caption)', fontFamily: 'var(--font-precision)', whiteSpace: 'pre-wrap' }}>
                        <span style={{ display: 'block', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginBottom: '4px', fontWeight: 700 }}>CATATAN AUDIT RISKGATE:</span>
                        {dossier.stage4_riskgate.execution_notes}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 5: EXECUTION TELEMETRY & LINEAGE */}
                {(activeTab === 'all' || activeTab === 'stage5') && (
                  <div style={cardStyle}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderBottom: '1px solid var(--color-border)',
                        paddingBottom: '8px',
                        marginBottom: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Terminal size={16} color="var(--color-brass)" />
                        <strong style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)' }}>
                          STAGE 5: EXECUTION TELEMETRY & INTEGRITY
                        </strong>
                      </div>
                      <span
                        style={badgeStyle(
                          dossier.stage5_execution.integrity_valid ? 'var(--color-profit-bg)' : 'var(--color-loss-bg)',
                          dossier.stage5_execution.integrity_valid ? 'var(--color-text-profit)' : 'var(--color-text-loss)'
                        )}
                      >
                        {dossier.stage5_execution.integrity_valid ? '✓ SHA-256 VALID' : '✕ INTEGRITY COMPROMISED'}
                      </span>
                    </div>

                    {dossier.stage5_execution.position ? (
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                          gap: '8px',
                          padding: '8px',
                          background: 'var(--color-paper-raised)',
                          border: '1px solid var(--color-border)',
                          borderRadius: 'var(--radius-xs)',
                          marginBottom: '10px',
                          fontSize: 'var(--text-caption)',
                          fontFamily: 'var(--font-precision)',
                        }}
                      >
                        <div>
                          <span style={{ color: 'var(--color-ink-soft)', display: 'block' }}>MT5 Ticket</span>
                          <strong>#{dossier.stage5_execution.position.ticket}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--color-ink-soft)', display: 'block' }}>Fill Price</span>
                          <strong>{fmt.price(dossier.stage5_execution.position.entry_price, dossier.symbol)}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--color-ink-soft)', display: 'block' }}>Slippage</span>
                          <strong>{(dossier.stage5_execution.position.slippage_pips ?? 0).toFixed(1)} pips</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--color-ink-soft)', display: 'block' }}>PnL</span>
                          <strong style={{ color: (dossier.stage5_execution.position.pnl ?? 0) >= 0 ? 'var(--color-text-profit)' : 'var(--color-text-loss)' }}>
                            {fmt.usd(dossier.stage5_execution.position.pnl ?? 0, true)}
                          </strong>
                        </div>
                      </div>
                    ) : (
                      <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-caption)', color: 'var(--color-ink-soft)', marginBottom: '10px' }}>
                        ℹ️ Tidak ada posisi broker live yang dieksekusi untuk keputusan {dossier.decision.toUpperCase()}.
                      </div>
                    )}

                    <div style={{ padding: '8px 10px', background: 'var(--color-paper-sunken)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-caption)', fontFamily: 'var(--font-precision)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span>Cycle ID: <strong>{dossier.stage5_execution.cycle_id}</strong></span>
                        <span>Total Events: <strong style={{ color: 'var(--color-text-info)' }}>{dossier.stage5_execution.event_count}</strong></span>
                      </div>
                      {dossier.stage5_execution.sha256_chain_hash && (
                        <div style={{ wordBreak: 'break-all', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                          Chain Hash: <code style={{ color: 'var(--color-text-info)' }}>{dossier.stage5_execution.sha256_chain_hash}</code>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Modal Footer */}
          <div
            style={{
              padding: '10px 16px',
              borderTop: '1px solid var(--color-rule)',
              background: 'var(--color-paper)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 'var(--text-caption)',
              fontFamily: 'var(--font-precision)',
              color: 'var(--color-ink-soft)',
            }}
          >
            <span>STANDAR AUDIT DETERMINISTIK §7.2 | MONIKA FORTRESS</span>
            <button
              type="button"
              onClick={onClose}
              className="win-btn"
              style={{
                padding: '4px 14px',
                fontSize: 'var(--text-body-sm)',
              }}
            >
              Tutup
            </button>
          </div>
        </WindowFrame>
      </div>
    </div>
  );
};
export default DecisionDossierModal;

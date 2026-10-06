import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { DecisionDossierData } from '../../types/api';
import { fmt } from '../../lib/formatters';

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl max-h-[90vh] flex flex-col rounded-2xl bg-zinc-950 border border-zinc-800 shadow-2xl shadow-cyan-950/20 overflow-hidden text-zinc-100 font-sans">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/60">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-cyan-950/60 border border-cyan-800/40 text-cyan-400 font-mono text-sm font-semibold">
              🔍 DOSSIER
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold tracking-tight text-white">
                  Decision Audit & Explainability
                </h2>
                {dossier && (
                  <>
                    <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                      {dossier.symbol}
                    </span>
                    <span
                      className={`text-xs font-mono font-bold px-2 py-0.5 rounded uppercase ${
                        dossier.decision === 'buy'
                          ? 'bg-emerald-950 border border-emerald-700/60 text-emerald-400'
                          : dossier.decision === 'sell'
                          ? 'bg-rose-950 border border-rose-700/60 text-rose-400'
                          : 'bg-amber-950 border border-amber-700/60 text-amber-400'
                      }`}
                    >
                      {dossier.decision} ({dossier.confidence}%)
                    </span>
                  </>
                )}
              </div>
              <p className="text-xs text-zinc-400">
                End-to-end multi-agent lineage, adversarial thesis, and mechanical fortress validation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {dossier && (
              <>
                <button
                  onClick={handleCopyReceipt}
                  className="px-3 py-1.5 rounded-lg text-xs font-mono font-medium border border-zinc-700 bg-zinc-800/80 hover:bg-zinc-700 text-zinc-200 transition-colors flex items-center gap-1.5"
                  title="Copy markdown receipt"
                >
                  {copied ? '✓ COPIED' : '📋 RECEIPT'}
                </button>
                <button
                  onClick={handleExportJson}
                  className="px-3 py-1.5 rounded-lg text-xs font-mono font-medium border border-cyan-800/60 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 transition-colors flex items-center gap-1.5"
                  title="Export raw JSON"
                >
                  💾 JSON
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors ml-2"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tab Filters */}
        {dossier && (
          <div className="flex items-center gap-1 px-6 py-2 border-b border-zinc-800/60 bg-zinc-900/30 overflow-x-auto text-xs font-mono">
            {[
              { id: 'all', label: 'ALL STAGES' },
              { id: 'stage1', label: '1. MACRO REALITY' },
              { id: 'stage2', label: '2. CONFLUENCE & SMC' },
              { id: 'stage3', label: '3. DEBATE & JUDGE' },
              { id: 'stage4', label: '4. RISKGATE FORTRESS' },
              { id: 'stage5', label: '5. TELEMETRY & HASH' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-3 py-1 rounded-md transition-colors ${
                  activeTab === tab.id
                    ? 'bg-zinc-800 text-cyan-400 font-semibold border border-zinc-700'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-850'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && (
            <div className="py-20 text-center space-y-3">
              <div className="inline-block w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-mono text-zinc-400">Synthesizing Decision Lineage & Reconstructing Audit Trail...</p>
            </div>
          )}

          {error && !loading && (
            <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950/30 text-rose-300 text-sm font-mono">
              <div className="font-bold mb-1">⚠️ Error Retrieving Dossier</div>
              <div>{error}</div>
            </div>
          )}

          {dossier && !loading && (
            <div className="space-y-6">
              
              {/* Executive Summary Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-xl bg-zinc-900/80 border border-zinc-800 text-xs font-mono">
                <div>
                  <span className="text-zinc-500 block">Analysis ID:</span>
                  <span className="font-bold text-zinc-200">#{dossier.analysis_id}</span>
                </div>
                <div>
                  <span className="text-zinc-500 block">Market Regime:</span>
                  <span className="font-bold uppercase text-cyan-400">{dossier.market_regime}</span>
                </div>
                <div>
                  <span className="text-zinc-500 block">Price at Analysis:</span>
                  <span className="font-bold text-zinc-200">{dossier.price_at_analysis ? fmt.price(dossier.price_at_analysis, dossier.symbol) : 'N/A'}</span>
                </div>
                <div>
                  <span className="text-zinc-500 block">Execution Status:</span>
                  <span className={`font-bold uppercase ${
                    dossier.stage4_riskgate.execution_status === 'approved' || dossier.stage4_riskgate.execution_status === 'executed'
                      ? 'text-emerald-400'
                      : dossier.stage4_riskgate.execution_status === 'rejected' || dossier.stage4_riskgate.execution_status === 'blocked'
                      ? 'text-rose-400'
                      : 'text-amber-400'
                  }`}>
                    {dossier.stage4_riskgate.execution_status}
                  </span>
                </div>
              </div>

              {/* STAGE 1: MACRO REALITY */}
              {(activeTab === 'all' || activeTab === 'stage1') && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-500" />
                      <h3 className="text-sm font-bold text-blue-400 font-mono">STAGE 1: MACRO REALITY</h3>
                    </div>
                    {dossier.stage1_macro.brief_age_hours !== null && (
                      <span className="text-xs font-mono text-zinc-400">
                        Brief Age: {dossier.stage1_macro.brief_age_hours}h
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800/80">
                      <span className="text-zinc-500 block mb-1">Risk Sentiment</span>
                      <span className="font-bold text-zinc-200 uppercase">{dossier.stage1_macro.risk_sentiment}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800/80">
                      <span className="text-zinc-500 block mb-1">DXY Trend / USD Bias</span>
                      <span className="font-bold text-cyan-400 uppercase">{dossier.stage1_macro.dxy_bias}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800/80">
                      <span className="text-zinc-500 block mb-1">Volatility Regime</span>
                      <span className="font-bold text-amber-400 uppercase">{dossier.stage1_macro.volatility_regime}</span>
                    </div>
                  </div>
                  {dossier.stage1_macro.summary && (
                    <div className="p-3 rounded-lg bg-zinc-950/80 border border-zinc-800/80 text-xs text-zinc-300 leading-relaxed font-sans">
                      <span className="font-mono text-zinc-500 text-[10px] block mb-1">MACRO BRIEF EXCERPT</span>
                      {dossier.stage1_macro.summary}
                    </div>
                  )}
                </div>
              )}

              {/* STAGE 2: TACTICAL CONFLUENCE & SMC */}
              {(activeTab === 'all' || activeTab === 'stage2') && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" />
                      <h3 className="text-sm font-bold text-emerald-400 font-mono">STAGE 2: TACTICAL CONFLUENCE & SMC</h3>
                    </div>
                    <div className="flex items-center gap-3 text-xs font-mono">
                      <span>Confluence: <strong className="text-emerald-400">{dossier.stage2_tactical.confluence_score ?? 'N/A'}/100</strong></span>
                      <span>Priced-in: <strong className="text-amber-400">{dossier.stage2_tactical.priced_in_score ?? 'N/A'}/100</strong></span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs font-mono">
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block">Stop Loss</span>
                      <span className="font-bold text-rose-400">{dossier.stop_loss ? fmt.price(dossier.stop_loss, dossier.symbol) : 'N/A'}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block">Take Profit</span>
                      <span className="font-bold text-emerald-400">{dossier.take_profit ? fmt.price(dossier.take_profit, dossier.symbol) : 'N/A'}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block">Invalidation Level</span>
                      <span className="font-bold text-amber-400">{dossier.invalidation_price ? fmt.price(dossier.invalidation_price, dossier.symbol) : (dossier.invalidation || 'N/A')}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block">SSVP CDS Score</span>
                      <span className="font-bold text-cyan-400">{dossier.stage2_tactical.ssvp_cds_score ?? 'N/A'}</span>
                    </div>
                  </div>

                  {dossier.rationale && (
                    <div className="p-3 rounded-lg bg-zinc-950/80 border border-zinc-800/80 text-xs text-zinc-300 leading-relaxed font-sans">
                      <span className="font-mono text-zinc-500 text-[10px] block mb-1">TECHNICAL RATIONALE</span>
                      {dossier.rationale}
                    </div>
                  )}

                  {dossier.stage2_tactical.factors.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] font-mono text-zinc-500 uppercase">Active Alpha Factors:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {dossier.stage2_tactical.factors.map((factor, idx) => (
                          <span key={idx} className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700/60 text-[11px] font-mono text-zinc-300">
                            ⚡ {factor}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* STAGE 3: ADVERSARIAL DEBATE & JUDICIAL VERDICT */}
              {(activeTab === 'all' || activeTab === 'stage3') && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-purple-500" />
                      <h3 className="text-sm font-bold text-purple-400 font-mono">STAGE 3: ADVERSARIAL DEBATE</h3>
                    </div>
                    <span className="text-xs font-mono text-zinc-400">
                      Verdict: <strong className="text-purple-300 uppercase">{dossier.stage3_debate.judge_verdict}</strong>
                      {dossier.stage3_debate.was_modified && (
                        <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-950 border border-amber-800/60 text-amber-300 text-[10px]">
                          MODIFIED BY DEBATE
                        </span>
                      )}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-900/50 space-y-1 font-sans">
                      <div className="flex items-center gap-1.5 font-mono text-emerald-400 text-xs font-bold">
                        <span>🐂 Bull Advocate Thesis</span>
                      </div>
                      <p className="text-zinc-300 leading-relaxed text-xs">
                        {dossier.stage3_debate.bull_thesis || 'No formal bull thesis recorded.'}
                      </p>
                    </div>

                    <div className="p-3 rounded-lg bg-rose-950/20 border border-rose-900/50 space-y-1 font-sans">
                      <div className="flex items-center gap-1.5 font-mono text-rose-400 text-xs font-bold">
                        <span>🐻 Bear Dissent Argument</span>
                      </div>
                      <p className="text-zinc-300 leading-relaxed text-xs">
                        {dossier.stage3_debate.bear_dissent || 'No formal bear dissent recorded.'}
                      </p>
                    </div>
                  </div>

                  {dossier.stage3_debate.judge_reason && (
                    <div className="p-3 rounded-lg bg-purple-950/20 border border-purple-900/40 text-xs font-sans text-zinc-300">
                      <span className="font-mono text-purple-400 text-[10px] block mb-1">⚖️ JUDICIAL RULING & REASON</span>
                      {dossier.stage3_debate.judge_reason}
                    </div>
                  )}
                </div>
              )}

              {/* STAGE 4: MECHANICAL FORTRESS RISKGATE */}
              {(activeTab === 'all' || activeTab === 'stage4') && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-500" />
                      <h3 className="text-sm font-bold text-cyan-400 font-mono">STAGE 4: RISKGATE MECHANICAL FORTRESS</h3>
                    </div>
                    <span className="text-xs font-mono text-zinc-400">
                      Risk Multiplier: <strong className="text-cyan-300">{dossier.stage4_riskgate.risk_multiplier}x</strong>
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block mb-1">Risk Gate Status</span>
                      <span className={`font-bold uppercase ${
                        dossier.stage4_riskgate.execution_status === 'approved' || dossier.stage4_riskgate.execution_status === 'executed'
                          ? 'text-emerald-400'
                          : 'text-rose-400'
                      }`}>
                        {dossier.stage4_riskgate.execution_status}
                      </span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block mb-1">Decision Source</span>
                      <span className="font-bold text-zinc-300">{dossier.stage4_riskgate.decision_source}</span>
                    </div>
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                      <span className="text-zinc-500 block mb-1">SSVP Suppression</span>
                      <span className={`font-bold ${dossier.stage4_riskgate.was_ssvp_suppressed ? 'text-amber-400' : 'text-zinc-400'}`}>
                        {dossier.stage4_riskgate.was_ssvp_suppressed ? 'YES (Suppressed)' : 'NO (Clear)'}
                      </span>
                    </div>
                  </div>

                  {dossier.stage4_riskgate.execution_notes && (
                    <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs font-mono text-zinc-300">
                      <span className="text-zinc-500 text-[10px] block mb-1">RISKGATE AUDIT LOG / REJECTION REASONS:</span>
                      <p className="leading-relaxed whitespace-pre-wrap">{dossier.stage4_riskgate.execution_notes}</p>
                    </div>
                  )}
                </div>
              )}

              {/* STAGE 5: EXECUTION TELEMETRY & CRYPTOGRAPHIC LINEAGE */}
              {(activeTab === 'all' || activeTab === 'stage5') && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-amber-500" />
                      <h3 className="text-sm font-bold text-amber-400 font-mono">STAGE 5: EXECUTION TELEMETRY & LINEAGE</h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                          dossier.stage5_execution.integrity_valid
                            ? 'bg-emerald-950 border border-emerald-700/60 text-emerald-400'
                            : 'bg-rose-950 border border-rose-700/60 text-rose-400'
                        }`}
                      >
                        {dossier.stage5_execution.integrity_valid ? '✓ SHA-256 VALID CHAIN' : '✕ CHAIN COMPROMISED'}
                      </span>
                    </div>
                  </div>

                  {/* Position Details if Executed */}
                  {dossier.stage5_execution.position ? (
                    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono space-y-2">
                      <div className="flex items-center justify-between text-zinc-400">
                        <span>MT5 Order Ticket: <strong className="text-white">#{dossier.stage5_execution.position.ticket}</strong></span>
                        <span>Fill Price: <strong className="text-white">{fmt.price(dossier.stage5_execution.position.entry_price, dossier.symbol)}</strong></span>
                        <span>Slippage: <strong className="text-zinc-300">{(dossier.stage5_execution.position.slippage_pips ?? 0).toFixed(1)} pips</strong></span>
                        <span>PnL: <strong className={(dossier.stage5_execution.position.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{fmt.usd(dossier.stage5_execution.position.pnl ?? 0, true)}</strong></span>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 rounded-lg bg-zinc-950/60 border border-zinc-850 text-xs font-mono text-zinc-500">
                      ℹ️ No live broker position filled for this trade (Decision: {dossier.decision.toUpperCase()}).
                    </div>
                  )}

                  {/* SHA-256 Hash Chain Fingerprint */}
                  <div className="p-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs font-mono space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-500">Cycle ID: <strong className="text-zinc-300">{dossier.stage5_execution.cycle_id}</strong></span>
                      <span className="text-zinc-500">Total Sequential Events: <strong className="text-cyan-400">{dossier.stage5_execution.event_count}</strong></span>
                    </div>
                    {dossier.stage5_execution.sha256_chain_hash && (
                      <div className="text-[11px] text-zinc-400 break-all pt-1">
                        Chain Hash: <code className="text-cyan-300">{dossier.stage5_execution.sha256_chain_hash}</code>
                      </div>
                    )}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-zinc-800/80 bg-zinc-900/60 text-xs font-mono text-zinc-500">
          <span>Deterministic Audit Standard §7.2 | Sovereign Fortress</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};

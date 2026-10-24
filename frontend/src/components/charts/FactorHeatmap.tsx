import React, { useState } from 'react';
import { sounds } from '../../lib/soundEffects';
import { LayoutGrid, ListFilter, Sparkles } from 'lucide-react';

interface FactorHeatmapProps {
  data: Record<string, {
    win_rate: number;
    total: number;
    wins: number;
    assessment: string;
    p_value?: number;
    significant?: boolean;
  }>;
}

const FACTOR_LABELS: Record<string, string> = {
  fundamental_bias: 'Fundamental Macro Bias',
  dxy_confirms: 'DXY Confluence Alignment',
  d1_trend: 'Daily (D1) Trend Direction',
  rsi_neutral: 'RSI Momentum Neutrality',
  near_fvg: 'Fair Value Gap (FVG) Zone',
  near_order_block: 'Institutional Order Block',
  in_ote_zone: 'OTE Fibonacci Retracement',
  near_sr_zone: 'Key Support / Resistance',
  cot_aligned: 'COT Institutional Positioning',
  vix_ok: 'CBOE VIX Volatility Regime',
  post_event_entry: 'Post-Macro Event Timing',
  session_prime: 'London / NY Prime Session',
};

export const FactorHeatmap: React.FC<FactorHeatmapProps> = ({ data }) => {
  const [viewMode, setViewMode] = useState<'matrix' | 'list'>('matrix');
  const [filterSignificantOnly, setFilterSignificantOnly] = useState<boolean>(false);

  const rawEntries = Object.entries(data || {});

  const filtered = rawEntries.filter(([, stats]) => {
    if (filterSignificantOnly) {
      return stats.assessment === 'STRONG_PREDICTOR' || stats.assessment === 'NEGATIVE_PREDICTOR' || stats.significant;
    }
    return true;
  });

  const sorted = [...filtered].sort(([, a], [, b]) => {
    const wrA = (a.win_rate <= 1 && a.total > 0) ? a.win_rate * 100 : a.win_rate;
    const wrB = (b.win_rate <= 1 && b.total > 0) ? b.win_rate * 100 : b.win_rate;
    return wrB - wrA;
  });

  // Calculate approximate Information Coefficient (IC) from win rate
  const computeIC = (winRatePct: number): number => {
    // Normal binary classification IC approximation: 2 * (WR - 0.5)
    const p = winRatePct / 100;
    return Math.max(-1, Math.min(1, 2 * (p - 0.5)));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontFamily: 'var(--font-precision)' }}>
      {/* View Switcher & Filter Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', fontWeight: 800, color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>
            FACTOR VIEW:
          </span>
          <div style={{ display: 'inline-flex', border: '1px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
            <button
              type="button"
              onClick={() => { sounds.playClick('toggle'); setViewMode('matrix'); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 8px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: viewMode === 'matrix' ? 800 : 500,
                background: viewMode === 'matrix' ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: viewMode === 'matrix' ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
                border: 'none',
                borderRight: '1px solid var(--color-rule)',
                cursor: 'pointer',
              }}
            >
              <LayoutGrid size={12} /> 2D MATRIX
            </button>
            <button
              type="button"
              onClick={() => { sounds.playClick('toggle'); setViewMode('list'); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 8px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: viewMode === 'list' ? 800 : 500,
                background: viewMode === 'list' ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: viewMode === 'list' ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <ListFilter size={12} /> RANKED LIST
            </button>
          </div>
        </div>

        {/* Significance filter toggle */}
        <button
          type="button"
          onClick={() => {
            sounds.playClick('toggle');
            setFilterSignificantOnly(!filterSignificantOnly);
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            padding: '3px 9px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: filterSignificantOnly ? 800 : 600,
            background: filterSignificantOnly ? 'rgba(232, 185, 74, 0.2)' : 'var(--color-paper)',
            color: filterSignificantOnly ? 'var(--color-ink)' : 'var(--color-ink-soft)',
            border: `1px solid ${filterSignificantOnly ? 'var(--color-brass)' : 'var(--color-rule)'}`,
            borderRadius: '2px',
            cursor: 'pointer',
          }}
        >
          <Sparkles size={12} color={filterSignificantOnly ? 'var(--color-brass)' : 'var(--color-ink-soft)'} />
          {filterSignificantOnly ? 'SHOWING SIGNIFICANT ONLY (FDR)' : 'ALL FACTORS'}
        </button>
      </div>

      {sorted.length === 0 ? (
        <div style={{ padding: '16px', textAlign: 'center', color: 'var(--color-ink-muted)', fontSize: '12px' }}>
          No factors matching filter criteria.
        </div>
      ) : viewMode === 'matrix' ? (
        /* 2D Matrix Heatmap View */
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
            gap: '10px',
          }}
        >
          {sorted.map(([factor, stats]) => {
            const winRatePct = (stats.win_rate <= 1 && stats.total > 0) ? stats.win_rate * 100 : stats.win_rate;
            const ic = computeIC(winRatePct);
            const isHigh = winRatePct >= 55;
            const isLow = winRatePct < 45;

            // Background heat styling
            const bgHeat = isHigh
              ? 'rgba(34, 197, 94, 0.12)'
              : isLow
              ? 'rgba(239, 68, 68, 0.12)'
              : 'rgba(232, 185, 74, 0.08)';

            const borderColor = isHigh
              ? 'var(--color-ledger-green)'
              : isLow
              ? 'var(--color-ledger-red)'
              : 'var(--color-rule)';

            const textBadgeColor = isHigh
              ? 'var(--color-ledger-green)'
              : isLow
              ? 'var(--color-ledger-red)'
              : 'var(--color-brass)';

            return (
              <div
                key={factor}
                style={{
                  background: bgHeat,
                  border: `1px solid ${borderColor}`,
                  borderRadius: '2px',
                  padding: '10px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '8px',
                  boxShadow: '1px 1px 0 var(--color-rule)',
                  position: 'relative',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 800, color: 'var(--color-ink)', lineHeight: '1.2' }}>
                      {FACTOR_LABELS[factor] || factor}
                    </span>
                    {stats.significant && (
                      <span title="Statistically significant via Benjamini-Hochberg FDR test" style={{ cursor: 'help' }}>
                        <Sparkles size={12} color="var(--color-brass)" />
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>
                    ALPHA CODE: <code>{factor}</code>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderTop: '1px dashed var(--color-rule)', paddingTop: '6px' }}>
                  <div>
                    <span className="tabular-nums" style={{ fontSize: '18px', fontWeight: 900, color: textBadgeColor }}>
                      {winRatePct.toFixed(1)}%
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)', display: 'block' }}>
                      {stats.wins}/{stats.total} trades
                    </span>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '11px', fontWeight: 800, color: ic >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                      IC: {ic >= 0 ? `+${ic.toFixed(2)}` : ic.toFixed(2)}
                    </div>
                    {stats.p_value != null && (
                      <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        p={stats.p_value.toFixed(3)}
                      </div>
                    )}
                  </div>
                </div>

                {stats.assessment && (
                  <div style={{ marginTop: '2px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '1px 5px',
                        borderRadius: '2px',
                        fontWeight: 700,
                        background: stats.assessment === 'STRONG_PREDICTOR'
                          ? 'rgba(34, 197, 94, 0.2)'
                          : stats.assessment === 'NEGATIVE_PREDICTOR'
                          ? 'rgba(239, 68, 68, 0.2)'
                          : 'rgba(217, 119, 6, 0.15)',
                        color: stats.assessment === 'STRONG_PREDICTOR'
                          ? 'var(--color-ledger-green)'
                          : stats.assessment === 'NEGATIVE_PREDICTOR'
                          ? 'var(--color-ledger-red)'
                          : 'var(--color-brass)',
                        border: `1px solid ${
                          stats.assessment === 'STRONG_PREDICTOR'
                            ? 'var(--color-ledger-green)'
                            : stats.assessment === 'NEGATIVE_PREDICTOR'
                            ? 'var(--color-ledger-red)'
                            : 'var(--color-brass)'
                        }`,
                        display: 'inline-block',
                      }}
                    >
                      {stats.assessment.replace('_', ' ')}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* 1D Ranked List View */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {sorted.map(([factor, stats]) => {
            const winRatePct = (stats.win_rate <= 1 && stats.total > 0) ? stats.win_rate * 100 : stats.win_rate;
            const ic = computeIC(winRatePct);
            const isHigh = winRatePct >= 55;
            const isMed = winRatePct >= 45;
            const color = isHigh
              ? 'var(--color-ledger-green)'
              : isMed
              ? 'var(--color-brass)'
              : 'var(--color-ledger-red)';
            const barWidth = `${Math.min(100, Math.max(0, winRatePct))}%`;

            return (
              <div key={factor}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '3px',
                  }}
                >
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-ink)',
                      fontWeight: 'var(--weight-bold)',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {FACTOR_LABELS[factor] || factor}
                    {stats.assessment && (
                      <span
                        style={{
                          marginLeft: '8px',
                          fontSize: '11px',
                          padding: '1px 5px',
                          borderRadius: '2px',
                          fontWeight: 700,
                          background: stats.assessment === 'STRONG_PREDICTOR'
                            ? 'rgba(34, 197, 94, 0.15)'
                            : stats.assessment === 'NEGATIVE_PREDICTOR'
                            ? 'rgba(239, 68, 68, 0.15)'
                            : 'rgba(217, 119, 6, 0.15)',
                          color: stats.assessment === 'STRONG_PREDICTOR'
                            ? 'var(--color-profit)'
                            : stats.assessment === 'NEGATIVE_PREDICTOR'
                            ? 'var(--color-loss)'
                            : 'var(--color-warning)',
                          border: `1px solid ${
                            stats.assessment === 'STRONG_PREDICTOR'
                              ? 'var(--color-profit)'
                              : stats.assessment === 'NEGATIVE_PREDICTOR'
                              ? 'var(--color-loss)'
                              : 'var(--color-warning)'
                          }`,
                        }}
                      >
                        {stats.assessment.replace('_', ' ')}
                      </span>
                    )}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
                      IC: {ic >= 0 ? `+${ic.toFixed(2)}` : ic.toFixed(2)}
                    </span>
                    <span
                      className="tabular-nums"
                      style={{
                        fontSize: 'var(--text-xs)',
                        color,
                        fontWeight: 'var(--weight-bold)',
                      }}
                    >
                      {winRatePct.toFixed(1)}% ({stats.wins}/{stats.total})
                    </span>
                  </div>
                </div>
                {/* Bar track */}
                <div
                  style={{
                    height: '6px',
                    background: 'var(--color-paper)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: 'var(--radius-card)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: barWidth,
                      background: color,
                      transition: 'width 200ms ease-out',
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

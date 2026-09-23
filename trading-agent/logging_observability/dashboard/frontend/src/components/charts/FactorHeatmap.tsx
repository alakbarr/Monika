import React from 'react';

interface FactorHeatmapProps {
  data: Record<string, {
    win_rate: number;
    total: number;
    wins: number;
    assessment: string;
  }>;
}

const FACTOR_LABELS: Record<string, string> = {
  fundamental_bias: 'Fundamental Macro Bias',
  dxy_confirms: 'DXY Confluence',
  d1_trend: 'Daily (D1) Trend Alignment',
  rsi_neutral: 'RSI Neutrality',
  near_fvg: 'FVG Proximity',
  near_order_block: 'Order Block Level',
  in_ote_zone: 'OTE Retracement Zone',
  near_sr_zone: 'Support / Resistance Zone',
  cot_aligned: 'COT Positioning Alignment',
  vix_ok: 'VIX Volatility Regime OK',
  post_event_entry: 'Post-Macro Event Entry',
  session_prime: 'Prime Trading Session',
};

export const FactorHeatmap: React.FC<FactorHeatmapProps> = ({ data }) => {
  const sorted = Object.entries(data)
    .sort(([, a], [, b]) => b.win_rate - a.win_rate);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontFamily: 'var(--font-precision)' }}>
      {sorted.map(([factor, stats]) => {
        const winRatePct = (stats.win_rate <= 1 && stats.total > 0) ? stats.win_rate * 100 : stats.win_rate;
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
                      fontSize: '9px',
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
              <span
                className="tabular-nums"
                style={{
                  fontSize: 'var(--text-xs)',
                  color,
                  fontWeight: 'var(--weight-bold)',
                }}
              >
                {winRatePct.toFixed(0)}% ({stats.total})
              </span>
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
  );
};

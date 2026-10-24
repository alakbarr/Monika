import React from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { AlertTriangle } from 'lucide-react';

export const EdgeMetricsPanel: React.FC = () => {
  const { edgeMetrics, loading } = useDashboardStore();

  if (loading) return (<Card><Skeleton height="200px" /></Card>);
  if (!edgeMetrics) return (
    <Card>
      <div style={{ textAlign: 'center', color: 'var(--color-ink-muted)', padding: '48px', fontSize: 'var(--text-body-sm)', fontFamily: 'var(--font-precision)' }}>
        No edge metrics available.
      </div>
    </Card>
  );

  const periods = ['7d', '14d', '30d'] as const;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {edgeMetrics.alert && (
        <div
          style={{
            background: 'var(--color-paper-raised)',
            border: '1px solid var(--color-loss)',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
          }}
        >
          <AlertTriangle color="var(--color-loss)" size={18} />
          <div>
            <div className="editorial-kicker" style={{ color: 'var(--color-loss)' }}>
              WARNING — NEGATIVE EXPECTANCY DEFICIT
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-ink-soft)', marginTop: '3px', lineHeight: 1.4 }}>
              Expectancy is negative across recent evaluation periods. Review analysis and arbitration quality.
            </div>
          </div>
        </div>
      )}

      <div
        className="edge-periods-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
        }}
      >
        {periods.map((period, idx) => {
          const data = edgeMetrics.edge_metrics?.[period];
          const roman = idx === 0 ? 'I' : idx === 1 ? 'II' : 'III';
          if (!data) {
            return (
              <div
                key={period}
                className="editorial-section swiss-crosshair"
                style={{
                  padding: '18px',
                  border: '1px solid var(--color-rule)',
                  background: 'var(--color-paper-raised)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div className="editorial-kicker">
                  {roman}. EVALUATION WINDOW — {period.toUpperCase()}
                </div>
                <div style={{ color: 'var(--color-ink-soft)', padding: '24px 8px', textAlign: 'center', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
                  — No closed trades archived for window {period} —
                </div>
              </div>
            );
          }
          const isInsuff = data.insufficient_data;
          const isProfitable = data.is_profitable;

          return (
            <div
              key={period}
              className="editorial-section swiss-crosshair"
              style={{
                border: '1px solid var(--color-rule)',
                borderTop: isProfitable && !isInsuff ? '2px solid var(--color-ledger-green)' : '1px solid var(--color-rule)',
                padding: '18px',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--color-paper-raised)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <span className="editorial-kicker">
                  {roman}. ROLLING WINDOW — {period.toUpperCase()}
                </span>
                {!isInsuff && (
                  <Badge variant={isProfitable ? 'profit' : 'loss'}>
                    {isProfitable ? 'PROFITABLE EDGE' : 'NO EDGE'}
                  </Badge>
                )}
              </div>

              {isInsuff ? (
                <div style={{ color: 'var(--color-ink-muted)', fontSize: '12px', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontStyle: 'italic', fontFamily: 'var(--font-precision)', padding: '24px 0' }}>
                  Insufficient data recorded (Min. 5 trades)
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingBottom: '10px', borderBottom: '1px solid var(--color-rule)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span className="editorial-kicker">WIN RATE</span>
                      <span
                        className="tabular-nums"
                        style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: '26px',
                          color: data.win_rate_pct >= 55 ? 'var(--color-profit)' : data.win_rate_pct >= 44 ? 'var(--color-ink)' : 'var(--color-loss)',
                        }}
                      >
                        {data.win_rate_pct.toFixed(1)}%
                      </span>
                    </div>
                    <div style={{ width: '100%', height: '3px', background: 'var(--color-rule)', overflow: 'hidden' }}>
                      <div
                        style={{
                          height: '100%',
                          width: `${Math.min(100, Math.max(0, data.win_rate_pct))}%`,
                          background: data.win_rate_pct >= 55 ? 'var(--color-profit)' : data.win_rate_pct >= 44 ? 'var(--color-brass)' : 'var(--color-loss)',
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px solid var(--color-rule)' }}>
                    <span style={{ fontSize: '12px', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>Expectancy</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: data.expectancy_per_trade_R >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>{fmt.r(data.expectancy_per_trade_R)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px solid var(--color-rule)' }}>
                    <span style={{ fontSize: '12px', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>Avg R:R</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{(data.avg_rr_achieved ?? 0).toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px solid var(--color-rule)' }}>
                    <span style={{ fontSize: '12px', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>Trades</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{data.total_trades ?? 0}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '12px', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>Avg Hold</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{fmt.hours(data.avg_holding_hours ?? 0)}</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Quantitative Protocol Guide */}
      <Card title="QUANTITATIVE PROTOCOL — STATISTICAL EDGE & EXPECTANCY MANDATE">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', fontSize: '12px', color: 'var(--color-ink)' }}>
          <div style={{ borderLeft: '1px solid var(--color-ledger-green)', paddingLeft: '12px' }}>
            <div className="editorial-kicker" style={{ color: 'var(--color-ledger-green)', marginBottom: '4px' }}>I. BENCHMARK WIN RATE (≥ 50%)</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.5 }}>Minimum win rate required to maintain statistical edge across FX and commodities markets.</div>
          </div>
          <div style={{ borderLeft: '1px solid var(--color-ink)', paddingLeft: '12px' }}>
            <div className="editorial-kicker" style={{ marginBottom: '4px' }}>II. EXPECTANCY R (&gt; +0.20 R)</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.5 }}>Formula: (WR × Avg Win R) - (LR × Avg Loss R). Computes mathematical expectancy per unit of risk.</div>
          </div>
          <div style={{ borderLeft: '1px solid var(--color-brass)', paddingLeft: '12px' }}>
            <div className="editorial-kicker" style={{ color: 'var(--color-brass)', marginBottom: '4px' }}>III. RISK GATE MITIGATION</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.5 }}>When 14-day rolling expectancy falls below zero, the risk gate engages capital protection protocols and reduces position sizing.</div>
          </div>
        </div>
      </Card>
    </div>
  );
};

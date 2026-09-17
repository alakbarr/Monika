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
        <div style={{ 
          background: 'var(--color-surface)', 
          border: '1px solid var(--color-loss)',
          borderLeft: '4px solid var(--color-loss)',
          borderRadius: '2px', 
          padding: '16px 20px', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '16px',
        }}>
          <AlertTriangle color="var(--color-loss)" size={22} />
          <div>
            <div style={{ 
              fontWeight: 'var(--weight-bold)', 
              color: 'var(--color-loss)', 
              fontSize: 'var(--text-body-md)', 
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)'
            }}>
              [ WARNING // NEGATIVE EXPECTANCY DEFICIT ]
            </div>
            <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', marginTop: '4px', lineHeight: 1.4 }}>
              Expectancy is negative across recent evaluation periods. Review analysis and arbitration quality.
            </div>
          </div>
        </div>
      )}

      <div className="edge-periods-grid" style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', 
        gap: '16px' 
      }}>
        {periods.map(period => {
          const data = edgeMetrics.edge_metrics?.[period];
          if (!data) {
            return (
              <div key={period} className="win-window ledger-card" style={{
                padding: '16px',
                border: '2px solid var(--color-rule)',
                borderRadius: 'var(--radius-card)',
                background: 'var(--color-paper-raised)',
                boxShadow: 'var(--shadow-card)',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}>
                <div style={{
                  display: 'inline-block',
                  fontSize: 'var(--text-caption)',
                  fontWeight: 'bold',
                  color: 'var(--color-ink)',
                  background: 'var(--color-paper)',
                  padding: '3px 8px',
                  borderRadius: '2px',
                  border: '1px solid var(--color-rule)',
                  alignSelf: 'flex-start',
                }}>
                  [ EVALUATION WINDOW: {period} ]
                </div>
                <div style={{ color: 'var(--color-ink-soft)', padding: '24px 8px', textAlign: 'center', fontSize: 'var(--text-xs)' }}>
                  — No closed trades archived for window {period} —
                </div>
              </div>
            );
          }
          const isInsuff = data.insufficient_data;
          const isProfitable = data.is_profitable;

          return (
            <div key={period} className="win-window ledger-card" style={{
              border: isProfitable && !isInsuff ? '2px solid var(--color-ledger-green)' : '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              padding: '18px',
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--color-paper-raised)',
              boxShadow: 'var(--shadow-card)',
            }}>
              <div style={{ 
                display: 'inline-block',
                fontSize: 'var(--text-caption)', 
                fontWeight: 'var(--weight-bold)', 
                color: 'var(--color-ink)',
                background: 'var(--color-surface)',
                padding: '4px 10px',
                borderRadius: '2px', 
                textTransform: 'uppercase', 
                letterSpacing: '0.08em', 
                marginBottom: '16px',
                alignSelf: 'flex-start',
                border: '1.5px solid var(--color-rule)',
                fontFamily: 'var(--font-precision)'
              }}>
                [ WINDOW: {period} ]
              </div>
              
              {isInsuff ? (
                <div style={{ color: 'var(--color-ink-muted)', fontSize: 'var(--text-body-sm)', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontStyle: 'italic', fontFamily: 'var(--font-precision)' }}>
                  Insufficient data recorded (Min. 5 trades)
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: 1 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingBottom: '12px', borderBottom: '1px solid var(--color-rule)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontWeight: 'var(--weight-medium)', fontFamily: 'var(--font-precision)' }}>Win Rate</span>
                      <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body-md)', color: data.win_rate_pct >= 55 ? 'var(--color-profit)' : data.win_rate_pct >= 44 ? 'var(--color-brass)' : 'var(--color-loss)' }}>
                        {data.win_rate_pct.toFixed(1)}%
                      </span>
                    </div>
                    {/* Mini progress bar for Win Rate */}
                    <div style={{ width: '100%', height: '6px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ 
                        height: '100%', 
                        width: `${Math.min(100, Math.max(0, data.win_rate_pct))}%`,
                        background: data.win_rate_pct >= 55 ? 'var(--color-profit)' : data.win_rate_pct >= 44 ? 'var(--color-brass)' : 'var(--color-loss)',
                        borderRadius: '1px',
                      }} />
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px dotted var(--color-rule)' }}>
                    <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Expectancy</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', fontWeight: 'var(--weight-bold)', color: data.expectancy_per_trade_R >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>{fmt.r(data.expectancy_per_trade_R)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px dotted var(--color-rule)' }}>
                    <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Avg R:R</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{(data.avg_rr_achieved ?? 0).toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px dotted var(--color-rule)' }}>
                    <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Trades</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{data.total_trades ?? 0}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '12px' }}>
                    <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Avg Hold</span>
                    <span style={{ fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{fmt.hours(data.avg_holding_hours ?? 0)}</span>
                  </div>
                  <div style={{ marginTop: 'auto', paddingTop: '8px' }}>
                    <div style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                      <Badge variant={isProfitable ? 'profit' : 'loss'}>
                        {isProfitable ? 'PROFITABLE EDGE' : 'NO EDGE'}
                      </Badge>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Retro Documentation Guide Card */}
      <Card
        title="QUANTITATIVE PROTOCOL: STATISTICAL EDGE & EXPECTANCY MANDATE"
        variant="yellow"
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px', fontSize: 'var(--text-xs)', color: 'var(--color-ink)' }}>
          <div style={{ borderLeft: '3px solid var(--color-ledger-green)', paddingLeft: '10px' }}>
            <div style={{ fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>Benchmark Win Rate (≥ 50%)</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.4 }}>Minimum win rate required to maintain statistical edge across FX and commodities markets.</div>
          </div>
          <div style={{ borderLeft: '3px solid var(--color-win-blue)', paddingLeft: '10px' }}>
            <div style={{ fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>Expectancy R (&gt; +0.20 R)</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.4 }}>Formula: (WR × Avg Win R) - (LR × Avg Loss R). Computes mathematical expectancy per unit of risk.</div>
          </div>
          <div style={{ borderLeft: '3px solid var(--color-brass)', paddingLeft: '10px' }}>
            <div style={{ fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '4px' }}>Risk Gate Mitigation (Guardian)</div>
            <div style={{ color: 'var(--color-ink-soft)', lineHeight: 1.4 }}>When 14-day rolling expectancy falls below zero, the risk gate engages capital protection protocols and reduces position sizing.</div>
          </div>
        </div>
      </Card>
    </div>
  );
};


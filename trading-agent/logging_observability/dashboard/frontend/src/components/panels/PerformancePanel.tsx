import React from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { WinRateGauge } from '../charts/WinRateGauge';
import { FactorHeatmap } from '../charts/FactorHeatmap';
import { DecisionDistChart } from '../charts/DecisionDistribution';
import { EquityChart } from '../charts/EquityChart';
import { Skeleton } from '../ui/Skeleton';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { Lock, Unlock, CheckCircle2, AlertTriangle, GraduationCap } from 'lucide-react';

export const PerformancePanel: React.FC = () => {
  const { paperStats, factorAnalysis, decisionDist, loading } = useDashboardStore();

  const equityPoints = React.useMemo(() => {
    if (!paperStats?.recent_20 || paperStats.recent_20.length === 0) return [];
    let eq = 10000;
    const points: Array<{ index: number; equity: number; symbol?: string; exit_reason?: string }> = [
      { index: 0, equity: eq, symbol: 'START' },
    ];
    paperStats.recent_20.forEach((t, i) => {
      eq = eq * (1 + (t.pnl_pct || 0) / 100);
      points.push({
        index: i + 1,
        equity: Number(eq.toFixed(2)),
        symbol: t.symbol,
        exit_reason: t.exit_reason,
      });
    });
    return points;
  }, [paperStats]);

  if (loading) return (
    <div style={{ display: 'grid', gap: '16px' }}>
      {[1, 2, 3].map(i => (
        <div key={i} className="ledger-card" style={{ padding: '24px', height: '200px' }}>
          <Skeleton height="20px" width="40%" />
          <div style={{ height: '16px' }} />
          <Skeleton height="140px" />
        </div>
      ))}
    </div>
  );

  const totalTrades = paperStats?.total_trades ?? 0;
  const winRate = paperStats?.win_rate_pct ?? 0;
  const hasEdge = paperStats?.has_positive_edge ?? false;
  const targetTrades = 50;
  const targetWinRate = 55.0;

  const tradeProgress = Math.min(100, Math.round((totalTrades / targetTrades) * 100));
  const tradesPassed = totalTrades >= targetTrades;
  const winRatePassed = winRate >= targetWinRate;
  const edgePassed = hasEdge;
  const isGraduated = tradesPassed && winRatePassed && edgePassed;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Graduation Gate Progress Card */}
      <Card
        title="PAPER TRADING GRADUATION GATE & LIVE READINESS"
        variant={isGraduated ? 'green' : 'yellow'}
        header={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <GraduationCap size={16} color={isGraduated ? 'var(--color-profit)' : 'var(--color-brass)'} />
              <span style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '12px' }}>
                Paper Trading Graduation Gate
              </span>
            </div>
            <Badge variant={isGraduated ? 'profit' : 'warn'}>
              {isGraduated ? 'GRADUATION READY (55%+ WR & 50+ TRADES)' : `LOCKED (${Math.max(0, targetTrades - totalTrades)} TRADES REMAINING)`}
            </Badge>
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '4px 0' }}>
          {/* Progress Bar & Status Line */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-precision)' }}>
              <span style={{ fontWeight: 600, color: 'var(--color-ink)' }}>
                Sample Size Progress: {totalTrades} / {targetTrades} Completed Trades ({tradeProgress}%)
              </span>
              <span style={{ color: 'var(--color-ink-muted)' }}>
                Requirement: 50 Out-of-Sample Trades @ ≥55% Win Rate
              </span>
            </div>
            {/* Visual Progress Bar */}
            <div
              style={{
                width: '100%',
                height: '14px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '3px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <div
                style={{
                  width: `${tradeProgress}%`,
                  height: '100%',
                  background: isGraduated
                    ? 'linear-gradient(90deg, var(--color-profit-dim, #16a34a) 0%, var(--color-profit, #22c55e) 100%)'
                    : 'linear-gradient(90deg, var(--color-brass, #b45309) 0%, var(--color-warning, #f59e0b) 100%)',
                  transition: 'width 0.4s ease',
                }}
              />
            </div>
          </div>

          {/* 3 Qualification Verification Checkpoints */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
            <div
              style={{
                padding: '10px 14px',
                background: 'var(--color-surface-card)',
                border: `1.5px solid ${tradesPassed ? 'var(--color-profit)' : 'var(--color-rule)'}`,
                borderRadius: '3px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              {tradesPassed ? <CheckCircle2 size={18} color="var(--color-profit)" /> : <AlertTriangle size={18} color="var(--color-warning)" />}
              <div>
                <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Target Sample Size
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: tradesPassed ? 'var(--color-profit)' : 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                  {totalTrades} / {targetTrades} Trades {tradesPassed ? '✓' : `(${tradeProgress}%)`}
                </div>
              </div>
            </div>

            <div
              style={{
                padding: '10px 14px',
                background: 'var(--color-surface-card)',
                border: `1.5px solid ${winRatePassed ? 'var(--color-profit)' : 'var(--color-rule)'}`,
                borderRadius: '3px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              {winRatePassed ? <CheckCircle2 size={18} color="var(--color-profit)" /> : <AlertTriangle size={18} color="var(--color-warning)" />}
              <div>
                <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Win Rate Benchmark
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: winRatePassed ? 'var(--color-profit)' : 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                  {fmt.pct(winRate)} / ≥{targetWinRate.toFixed(1)}% {winRatePassed ? '✓' : '✗'}
                </div>
              </div>
            </div>

            <div
              style={{
                padding: '10px 14px',
                background: 'var(--color-surface-card)',
                border: `1.5px solid ${edgePassed ? 'var(--color-profit)' : 'var(--color-rule)'}`,
                borderRadius: '3px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              {edgePassed ? <CheckCircle2 size={18} color="var(--color-profit)" /> : <AlertTriangle size={18} color="var(--color-warning)" />}
              <div>
                <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Positive Edge
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: edgePassed ? 'var(--color-profit)' : 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                  {fmt.r(paperStats?.expectancy_per_trade_R)} {edgePassed ? '✓ (Positive)' : '✗ (Negative)'}
                </div>
              </div>
            </div>

            <div
              style={{
                padding: '10px 14px',
                background: isGraduated ? 'var(--color-profit-dim, rgba(22, 163, 74, 0.1))' : 'var(--color-surface-card)',
                border: `1.5px solid ${isGraduated ? 'var(--color-profit)' : 'var(--color-rule)'}`,
                borderRadius: '3px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              {isGraduated ? <Unlock size={18} color="var(--color-profit)" /> : <Lock size={18} color="var(--color-warning)" />}
              <div>
                <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Live Mode Lock Status
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: isGraduated ? 'var(--color-profit)' : 'var(--color-warning)', fontFamily: 'var(--font-precision)' }}>
                  {isGraduated ? 'UNLOCKED' : 'LOCKED'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Top row: Win Rate + Key Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(260px, 1fr) 2fr',
        gap: '20px',
      }}>
        <Card
          title="OVERALL WIN RATE"
          variant="green"
        >
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '12px 0',
              minHeight: '180px',
              width: '100%',
            }}
          >
            {paperStats ? (
              <WinRateGauge winRate={paperStats.win_rate_pct} />
            ) : (
              <div style={{ color: 'var(--color-ink-muted)', padding: '40px', fontFamily: 'var(--font-precision)' }}>No data</div>
            )}
          </div>
        </Card>

        <Card
          title="PAPER TRADING PERFORMANCE & AUDIT LEDGER"
          variant="green"
        >
          {paperStats ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '1px',
              background: 'var(--color-rule)',
              borderRadius: '2px',
              overflow: 'hidden',
              border: '1px solid var(--color-rule)',
            }}>
              {[
                { label: 'Total Trades', value: paperStats.total_trades, mono: true },
                { label: 'Win Rate', value: fmt.pct(paperStats.win_rate_pct), mono: true, color: paperStats.win_rate_pct >= 45 ? 'var(--color-profit)' : 'var(--color-loss)' },
                { label: 'Avg Win', value: fmt.pct(paperStats.avg_win_pct, true), mono: true, color: 'var(--color-profit)' },
                { label: 'Avg Loss', value: fmt.pct(-paperStats.avg_loss_pct, true), mono: true, color: 'var(--color-loss)' },
                { label: 'Avg R:R', value: paperStats.avg_rr_achieved != null ? paperStats.avg_rr_achieved.toFixed(2) : '0.00', mono: true },
                { label: 'Expectancy', value: fmt.r(paperStats.expectancy_per_trade_R), mono: true, color: paperStats.has_positive_edge ? 'var(--color-profit)' : 'var(--color-loss)' },
                { label: 'Avg Win Hold', value: fmt.hours(paperStats.avg_win_hold_hours), mono: true },
                { label: 'Avg Loss Hold', value: fmt.hours(paperStats.avg_loss_hold_hours), mono: true },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: 'var(--color-surface-card)',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}>
                  <div style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--color-ink-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    fontWeight: 'var(--weight-medium)',
                    fontFamily: 'var(--font-precision)'
                  }}>
                    {label}
                  </div>
                  <div style={{
                    fontSize: 'var(--text-title-sm)',
                    fontWeight: 'var(--weight-bold)',
                    fontFamily: 'var(--font-precision)',
                    fontVariantNumeric: 'tabular-nums',
                    color: color || 'var(--color-ink)',
                  }}>
                    {value}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--color-ink-muted)', fontSize: 'var(--text-body-sm)', padding: '20px', fontFamily: 'var(--font-precision)' }}>
              No paper trading data available.
            </div>
          )}
        </Card>
      </div>

      {/* Paper Trading Simulated Equity Curve */}
      {equityPoints.length > 1 && (
        <Card
          title="OUT-OF-SAMPLE SIMULATED EQUITY CURVE (LAST 20 PAPER TRADES)"
          variant="green"
        >
          <div style={{ padding: '8px 0' }}>
            <EquityChart data={equityPoints} startEquity={10000} height={140} />
          </div>
        </Card>
      )}

      {/* Symbol breakdown */}
      {paperStats?.by_symbol && Object.keys(paperStats.by_symbol).length > 0 && (
        <Card
          title="PERFORMANCE BY ASSET / SYMBOL"
          variant="green"
          style={{ padding: '0', overflow: 'hidden' }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr>
                  {['Symbol', 'Trades', 'Wins', 'Win Rate', 'P&L %'].map(h => (
                    <th key={h} style={{
                      padding: '12px 16px',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-ink-muted)',
                      fontWeight: 'var(--weight-bold)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      borderBottom: '1px solid var(--color-rule)',
                      fontFamily: 'var(--font-precision)'
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(paperStats.by_symbol)
                  .sort(([, a], [, b]) => b.pnl_pct - a.pnl_pct)
                  .map(([sym, stats]) => (
                    <tr key={sym} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                      <td style={{
                        padding: '12px 16px',
                        fontFamily: 'var(--font-precision)',
                        fontWeight: 'var(--weight-bold)',
                        color: 'var(--color-ink)',
                        fontSize: 'var(--text-body-sm)',
                      }}>
                        {sym}
                      </td>
                      <td style={{
                        padding: '12px 16px',
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                        color: 'var(--color-ink-muted)',
                        fontSize: 'var(--text-body-sm)',
                      }}>
                        {stats.trades}
                      </td>
                      <td style={{
                        padding: '12px 16px',
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                        color: 'var(--color-profit)',
                        fontSize: 'var(--text-body-sm)',
                      }}>
                        {stats.wins}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                        }}>
                          <div style={{
                            width: '80px',
                            height: '6px',
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-rule)',
                            borderRadius: '2px',
                            overflow: 'hidden',
                          }}>
                            <div style={{
                              width: `${stats.win_rate}%`,
                              height: '100%',
                              background: stats.win_rate >= 55
                                ? 'var(--color-profit)'
                                : stats.win_rate >= 44
                                ? 'var(--color-brass)'
                                : 'var(--color-loss)',
                              borderRadius: '1px',
                            }} />
                          </div>
                          <span style={{
                            fontFamily: 'var(--font-precision)',
                            fontVariantNumeric: 'tabular-nums',
                            fontWeight: 'var(--weight-bold)',
                            fontSize: 'var(--text-body-sm)',
                            color: stats.win_rate >= 55
                              ? 'var(--color-profit)'
                              : stats.win_rate >= 44
                              ? 'var(--color-brass)'
                              : 'var(--color-loss)',
                          }}>
                            {stats.win_rate.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td style={{
                        padding: '12px 16px',
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 'var(--weight-bold)',
                        fontSize: 'var(--text-body-sm)',
                        color: stats.pnl_pct >= 0
                          ? 'var(--color-profit)'
                          : 'var(--color-loss)',
                      }}>
                        {fmt.pct(stats.pnl_pct, true)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Factor Effectiveness */}
      {factorAnalysis && !factorAnalysis.insufficient_data && (
        <Card
          title={`CONFLUENCE FACTOR EFFECTIVENESS (${factorAnalysis.total_trades_analyzed} Trades · ${factorAnalysis.days_analyzed}d)`}
          variant="green"
        >
          <FactorHeatmap data={factorAnalysis.factor_effectiveness} />
        </Card>
      )}

      {/* Decision Distribution */}
      {decisionDist && (
        <Card
          title="TRADING DECISION DISTRIBUTION (30D)"
          variant="green"
        >
          <DecisionDistChart data={decisionDist} />
          {/* Session buckets */}
          {paperStats?.session_buckets && (
            <div style={{
              marginTop: '28px',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: '12px',
            }}>
              {Object.entries(paperStats.session_buckets)
                .filter(([, d]) => d.total >= 2)
                .map(([key, data]) => {
                  const wr = data.total > 0 ? data.wins / data.total * 100 : 0;
                  return (
                    <div key={key} style={{
                      background: 'var(--color-surface)',
                      borderRadius: '2px',
                      padding: '14px',
                      border: '1px solid var(--color-rule)',
                    }}>
                      <div style={{
                        fontSize: 'var(--text-xs)',
                        color: 'var(--color-ink-muted)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        marginBottom: '6px',
                        lineHeight: 1.3,
                        fontWeight: 'var(--weight-semibold)',
                        fontFamily: 'var(--font-precision)'
                      }}>
                        {data.label}
                      </div>
                      <div style={{
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 'var(--weight-bold)',
                        fontSize: 'var(--text-title-sm)',
                        color: wr >= 55
                          ? 'var(--color-profit)'
                          : wr >= 44
                          ? 'var(--color-brass)'
                          : 'var(--color-loss)',
                        marginBottom: '4px'
                      }}>
                        {wr.toFixed(0)}%
                      </div>
                      <div style={{
                        fontSize: 'var(--text-xs)',
                        color: 'var(--color-ink-muted)',
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                      }}>
                        {data.wins}W / {data.total} trades
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};


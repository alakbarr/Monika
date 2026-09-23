import React, { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { TypewriterButton } from '../ui/TypewriterButton';
import { api } from '../../lib/api';
import type { BacktestRunItem, BacktestTradeItem, BacktestRunDetails } from '../../types/api';
import { EquityChart } from '../charts/EquityChart';
import {
  Play,
  RotateCw,
  Layers,
  Activity,
  TrendingUp,
  BarChart2,
} from 'lucide-react';

export const BacktestPanel: React.FC = () => {
  const [runs, setRuns] = useState<BacktestRunItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runDetails, setRunDetails] = useState<BacktestRunDetails | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [detailsLoading, setDetailsLoading] = useState<boolean>(false);
  const [launching, setLaunching] = useState<boolean>(false);
  const [launchMsg, setLaunchMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Launch Form State
  const [formDays, setFormDays] = useState<number>(30);
  const [formMode, setFormMode] = useState<string>('full');
  const [formEquity, setFormEquity] = useState<number>(10000);
  const [formStepHours, setFormStepHours] = useState<number>(6);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.backtestRuns(30, 0);
      setRuns(res.runs || []);
      if (res.runs && res.runs.length > 0 && selectedRunId === null) {
        setSelectedRunId(res.runs[0].id);
      }
    } catch (err: any) {
      console.error('Failed to load backtest runs:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedRunId]);

  const fetchRunDetails = useCallback(async (runId: number) => {
    setDetailsLoading(true);
    try {
      const res = await api.backtestRunDetails(runId);
      setRunDetails(res);
    } catch (err: any) {
      console.error(`Failed to load details for run #${runId}:`, err);
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    if (selectedRunId !== null) {
      fetchRunDetails(selectedRunId);
    }
  }, [selectedRunId, fetchRunDetails]);

  // Cumulative Equity Curve
  const equityCurve = React.useMemo(() => {
    if (!runDetails || !runDetails.trades || runDetails.trades.length === 0) return [];
    const startEq = runDetails.run.initial_equity || 10000;
    let curr = startEq;
    const points: Array<{ index: number; equity: number; symbol?: string; exit_reason?: string }> = [
      { index: 0, equity: curr, symbol: 'START' },
    ];
    const sortedTrades = [...runDetails.trades].sort((a, b) => {
      const ta = a.entry_time ? new Date(a.entry_time).getTime() : 0;
      const tb = b.entry_time ? new Date(b.entry_time).getTime() : 0;
      return ta - tb;
    });

    sortedTrades.forEach((t, i) => {
      curr = curr * (1 + (t.pnl_pct || 0) / 100);
      points.push({
        index: i + 1,
        equity: Number(curr.toFixed(2)),
        symbol: t.symbol,
        exit_reason: t.exit_reason,
      });
    });
    return points;
  }, [runDetails]);

  // Institutional Quant Metrics calculation
  const quantMetrics = React.useMemo(() => {
    if (!runDetails || !runDetails.trades || runDetails.trades.length === 0) return null;
    const trades = runDetails.trades;
    const returns = trades.map(t => (t.pnl_pct || 0) / 100);
    const n = trades.length;

    const meanReturn = returns.reduce((a, b) => a + b, 0) / n;
    const negativeReturns = returns.filter(r => r < 0);
    const downsideVariance = negativeReturns.length > 0
      ? negativeReturns.reduce((acc, r) => acc + Math.pow(r, 2), 0) / n
      : 0;
    const downsideDev = Math.sqrt(downsideVariance);
    const sortino = downsideDev > 0 ? (meanReturn / downsideDev) * Math.sqrt(252) : null;

    const run = runDetails.run;
    const totalReturnPct = run.initial_equity > 0 ? (run.final_equity - run.initial_equity) / run.initial_equity : 0;
    const maxDdPct = run.max_drawdown_pct > 0 ? run.max_drawdown_pct : 0.001;
    const calmar = totalReturnPct / maxDdPct;

    const sortedReturns = [...returns].sort((a, b) => a - b);
    const cutoffIndex = Math.max(1, Math.floor(n * 0.05));
    const worstReturns = sortedReturns.slice(0, cutoffIndex);
    const cvar95 = (worstReturns.reduce((a, b) => a + b, 0) / worstReturns.length) * 100;

    const wins = trades.filter(t => (t.pnl_pct || 0) > 0).length;
    const p = wins / n;
    const z = 1.95996;
    const denominator = 1 + (z * z) / n;
    const centerAdjusted = p + (z * z) / (2 * n);
    const margin = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n);
    const wilsonLow = Math.max(0, (centerAdjusted - margin) / denominator) * 100;
    const wilsonHigh = Math.min(1, (centerAdjusted + margin) / denominator) * 100;

    const winningTrades = trades.filter(t => (t.pnl_pct || 0) > 0);
    const avgWin = winningTrades.length > 0 ? winningTrades.reduce((a, t) => a + t.pnl_pct, 0) / winningTrades.length : 0;
    const avgLoss = negativeReturns.length > 0 ? Math.abs(negativeReturns.reduce((a, r) => a + r * 100, 0) / negativeReturns.length) : 0;
    const payoffRatio = avgLoss > 0 ? avgWin / avgLoss : 0;
    const expectancy = (p * avgWin) - ((1 - p) * avgLoss);

    return {
      sortino: sortino !== null ? sortino.toFixed(2) : '—',
      calmar: calmar.toFixed(2),
      cvar95: `${cvar95.toFixed(2)}%`,
      wilsonLow: wilsonLow.toFixed(1),
      wilsonHigh: wilsonHigh.toFixed(1),
      payoffRatio: payoffRatio.toFixed(2),
      expectancy: `${expectancy >= 0 ? '+' : ''}${expectancy.toFixed(2)}%`,
    };
  }, [runDetails]);

  const handleLaunchBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    setLaunching(true);
    setLaunchMsg(null);
    try {
      const res = await api.triggerBacktest({
        days: formDays,
        mode: formMode,
        initial_equity: formEquity,
        step_hours: formStepHours,
      });
      setLaunchMsg({ type: 'ok', text: res.message || 'Backtest queued successfully.' });
      setTimeout(() => fetchRuns(), 2000);
    } catch (err: any) {
      setLaunchMsg({ type: 'err', text: err.message || 'Failed to trigger backtest.' });
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontFamily: 'var(--font-precision)' }}>
      {/* Header Bar */}
      <div
        className="win-window ledger-card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-paper-raised)',
          padding: '12px 18px',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: '4px',
              background: 'var(--color-win-yellow)',
              border: '1.5px solid var(--color-rule)',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#1C1917',
            }}
          >
            <Layers size={20} />
          </div>
          <div>
            <h2
              style={{
                fontSize: 'var(--text-title-sm)',
                fontWeight: 800,
                margin: 0,
                color: 'var(--color-ink)',
                letterSpacing: '0.04em',
              }}
            >
              POINT-IN-TIME BACKTEST ENGINE // HISTORICAL REPLAY
            </h2>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
              Simulate full multi-agent cycles against historical tick data with zero lookahead bias.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TypewriterButton size="sm" onClick={() => fetchRuns()} disabled={loading}>
            <RotateCw size={12} className={loading ? 'animate-spin' : ''} /> [ REFRESH RUNS ]
          </TypewriterButton>
        </div>
      </div>

      {/* Main Grid: Launch Form & Runs List */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 380px) 1fr', gap: '16px' }}>
        {/* Launch Form Card */}
        <Card
          header={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Play size={14} color="var(--color-profit)" />
              <span>[ LAUNCH NEW SIMULATION ]</span>
            </div>
          }
        >
          <form onSubmit={handleLaunchBacktest} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>
                LOOKBACK WINDOW (DAYS)
              </label>
              <input
                type="number"
                min={1}
                max={365}
                value={formDays}
                onChange={(e) => setFormDays(Number(e.target.value))}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-body-sm)',
                  marginTop: '4px',
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>
                SIMULATION MODE
              </label>
              <select
                value={formMode}
                onChange={(e) => setFormMode(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-body-sm)',
                  marginTop: '4px',
                }}
              >
                <option value="full">Full Simulation (Point-in-Time)</option>
                <option value="replay">Tick Replay Mode</option>
                <option value="walk_forward">Walk-Forward Purged</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>
                  INITIAL EQUITY ($)
                </label>
                <input
                  type="number"
                  min={100}
                  step={500}
                  value={formEquity}
                  onChange={(e) => setFormEquity(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    color: 'var(--color-ink)',
                    fontSize: 'var(--text-body-sm)',
                    marginTop: '4px',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>
                  STEP (HOURS)
                </label>
                <input
                  type="number"
                  min={1}
                  max={24}
                  value={formStepHours}
                  onChange={(e) => setFormStepHours(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    color: 'var(--color-ink)',
                    fontSize: 'var(--text-body-sm)',
                    marginTop: '4px',
                  }}
                />
              </div>
            </div>

            {launchMsg && (
              <div
                style={{
                  padding: '8px 12px',
                  borderRadius: '2px',
                  fontSize: 'var(--text-xs)',
                  background: launchMsg.type === 'ok' ? 'var(--color-profit-bg)' : 'var(--color-loss-bg)',
                  color: launchMsg.type === 'ok' ? 'var(--color-profit)' : 'var(--color-loss)',
                  border: `1px solid ${launchMsg.type === 'ok' ? 'var(--color-profit)' : 'var(--color-loss)'}`,
                }}
              >
                {launchMsg.text}
              </div>
            )}

            <TypewriterButton type="submit" variant="primary" disabled={launching} style={{ marginTop: '8px' }}>
              <Play size={12} /> {launching ? '[ QUEUING BACKTEST... ]' : '[ START BACKTEST RUN ]'}
            </TypewriterButton>
          </form>
        </Card>

        {/* Historical Runs Table */}
        <Card
          header={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>[ HISTORICAL BACKTEST RUNS ({runs.length}) ]</span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)' }}>
                Click a run to inspect trade ledger
              </span>
            </div>
          }
        >
          {loading ? (
            <Skeleton height="180px" />
          ) : runs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--color-ink-soft)' }}>
              — No backtest runs recorded. Launch your first simulation above —
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-rule)', textAlign: 'left', color: 'var(--color-ink-muted)' }}>
                    <th style={{ padding: '8px' }}>ID / MODE</th>
                    <th style={{ padding: '8px' }}>PERIOD</th>
                    <th style={{ padding: '8px' }}>EQUITY</th>
                    <th style={{ padding: '8px' }}>WIN RATE</th>
                    <th style={{ padding: '8px' }}>SHARPE</th>
                    <th style={{ padding: '8px' }}>MAX DD</th>
                    <th style={{ padding: '8px' }}>TRADES</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const isSelected = selectedRunId === r.id;
                    const pnl = r.final_equity - r.initial_equity;
                    return (
                      <tr
                        key={r.id}
                        onClick={() => setSelectedRunId(r.id)}
                        style={{
                          borderBottom: '1px solid var(--color-rule)',
                          cursor: 'pointer',
                          background: isSelected ? 'var(--color-paper-raised)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '8px' }}>
                          <div style={{ fontWeight: 700 }}>#{r.id}</div>
                          <Badge variant="neutral">{r.mode.toUpperCase()}</Badge>
                        </td>
                        <td style={{ padding: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                          {r.start_date ? r.start_date.slice(0, 10) : '—'} → {r.end_date ? r.end_date.slice(0, 10) : '—'}
                        </td>
                        <td style={{ padding: '8px' }}>
                          <div style={{ fontWeight: 700, color: pnl >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                            ${r.final_equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                            Start: ${r.initial_equity.toLocaleString()}
                          </div>
                        </td>
                        <td style={{ padding: '8px', fontWeight: 700 }}>
                          {(r.win_rate * 100).toFixed(1)}%
                        </td>
                        <td style={{ padding: '8px' }}>
                          {r.sharpe_ratio ? r.sharpe_ratio.toFixed(2) : '—'}
                        </td>
                        <td style={{ padding: '8px', color: 'var(--color-loss)' }}>
                          {(r.max_drawdown_pct * 100).toFixed(1)}%
                        </td>
                        <td style={{ padding: '8px', fontWeight: 700 }}>
                          {r.total_trades}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Selected Run Details: Equity Curve & Quant Metrics */}
      {selectedRunId !== null && runDetails && runDetails.trades.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 1.2fr) 1fr', gap: '16px' }}>
          {/* Equity Curve Chart */}
          <Card
            header={
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TrendingUp size={14} color="var(--color-profit)" />
                <span>[ SIMULATED EQUITY CURVE — RUN #{selectedRunId} ]</span>
              </div>
            }
          >
            <div style={{ padding: '8px 0' }}>
              <EquityChart data={equityCurve} startEquity={runDetails.run.initial_equity || 10000} height={170} />
            </div>
          </Card>

          {/* Institutional Quant Risk & Edge Metrics */}
          {quantMetrics && (
            <Card
              header={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <BarChart2 size={14} color="var(--color-profit)" />
                  <span>[ INSTITUTIONAL QUANT METRICS ]</span>
                </div>
              }
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>SORTINO (ANN.)</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px', color: 'var(--color-profit)' }}>
                    {quantMetrics.sortino}
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>Downside penalty</div>
                </div>

                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>CALMAR RATIO</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px' }}>
                    {quantMetrics.calmar}
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>Return / Max DD</div>
                </div>

                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>CVaR (95%)</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px', color: 'var(--color-loss)' }}>
                    {quantMetrics.cvar95}
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>Tail expected shortfall</div>
                </div>

                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>WILSON 95% CI</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px' }}>
                    {quantMetrics.wilsonLow}% - {quantMetrics.wilsonHigh}%
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>True WR confidence</div>
                </div>

                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>PAYOFF RATIO</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px' }}>
                    {quantMetrics.payoffRatio}x
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>Avg Win / Avg Loss</div>
                </div>

                <div style={{ padding: '10px', background: 'var(--color-surface)', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontWeight: 700 }}>EXPECTANCY</div>
                  <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 800, marginTop: '4px', color: 'var(--color-profit)' }}>
                    {quantMetrics.expectancy}
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)' }}>Per trade edge</div>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Selected Run Details: Executed Trades */}
      {selectedRunId !== null && (
        <Card
          header={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={14} color="var(--color-profit)" />
                <span>[ EXECUTION TRADES LEDGER — RUN #{selectedRunId} ]</span>
              </div>
              {runDetails && (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)' }}>
                  Total Trades: {runDetails.trades_count}
                </span>
              )}
            </div>
          }
        >
          {detailsLoading ? (
            <Skeleton height="150px" />
          ) : !runDetails || runDetails.trades.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--color-ink-soft)' }}>
              — No trades executed during this backtest simulation —
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-rule)', textAlign: 'left', color: 'var(--color-ink-muted)' }}>
                    <th style={{ padding: '8px' }}>SYMBOL / DIR</th>
                    <th style={{ padding: '8px' }}>ENTRY</th>
                    <th style={{ padding: '8px' }}>EXIT</th>
                    <th style={{ padding: '8px' }}>PNL (PIPS / %)</th>
                    <th style={{ padding: '8px' }}>LOTS</th>
                    <th style={{ padding: '8px' }}>EXIT REASON</th>
                    <th style={{ padding: '8px' }}>RATIONALE</th>
                  </tr>
                </thead>
                <tbody>
                  {runDetails.trades.map((t: BacktestTradeItem) => {
                    const isWin = t.pnl_pct >= 0;
                    return (
                      <tr key={t.id} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                        <td style={{ padding: '8px' }}>
                          <div style={{ fontWeight: 800 }}>{t.symbol}</div>
                          <Badge variant={t.direction === 'buy' ? 'active' : 'warn'}>
                            {t.direction.toUpperCase()}
                          </Badge>
                        </td>
                        <td style={{ padding: '8px' }}>
                          <div>${t.entry_price.toFixed(5)}</div>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                            {t.entry_time ? t.entry_time.slice(0, 16).replace('T', ' ') : '—'}
                          </div>
                        </td>
                        <td style={{ padding: '8px' }}>
                          <div>${t.exit_price.toFixed(5)}</div>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                            {t.exit_time ? t.exit_time.slice(0, 16).replace('T', ' ') : '—'}
                          </div>
                        </td>
                        <td style={{ padding: '8px' }}>
                          <div style={{ fontWeight: 800, color: isWin ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                            {isWin ? '+' : ''}{t.pnl_pct.toFixed(2)}% ({t.pnl_pips.toFixed(1)} pips)
                          </div>
                        </td>
                        <td style={{ padding: '8px' }}>{t.executed_lots}</td>
                        <td style={{ padding: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                          {t.exit_reason}
                        </td>
                        <td style={{ padding: '8px', fontSize: 'var(--text-xs)', maxWidth: '300px' }}>
                          {t.rationale || '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

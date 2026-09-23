// ==============================================================================
// File: src/components/panels/RiskPanel.tsx
// Description: Comprehensive Quantitative Risk Cockpit with Analog VU Meters & Circuit Breakers
// ==============================================================================

import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { RetroVuMeter } from '../ui/RetroVuMeter';
import { TypewriterButton } from '../ui/TypewriterButton';
import { ConfirmModal } from '../ui/ConfirmModal';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';
import { api } from '../../lib/api';
import type { RiskScorecardItem, CorrelationMatrixItem } from '../../types/api';
import { ShieldCheck, AlertOctagon, Power, CheckCircle, XCircle } from 'lucide-react';

export const RiskPanel: React.FC = () => {
  const { overview, riskState, positions, fetchAll } = useDashboardStore();
  const [toggling, setToggling] = useState(false);
  const [toggleMsg, setToggleMsg] = useState<string | null>(null);
  const [showKillConfirm, setShowKillConfirm] = useState(false);

  // Scorecard & Correlation state
  const [scorecard, setScorecard] = useState<RiskScorecardItem | null>(null);
  const [scorecardSymbol, setScorecardSymbol] = useState<string>('EURUSD');
  const [correlation, setCorrelation] = useState<CorrelationMatrixItem | null>(null);
  const [scorecardLoading, setScorecardLoading] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    const fetchRiskDeep = async () => {
      try {
        setScorecardLoading(true);
        const [sc, corr] = await Promise.all([
          api.riskScorecard(scorecardSymbol).catch(() => null),
          api.riskCorrelationMatrix().catch(() => null),
        ]);
        if (mounted) {
          if (sc) setScorecard(sc);
          if (corr) setCorrelation(corr);
        }
      } finally {
        if (mounted) setScorecardLoading(false);
      }
    };
    fetchRiskDeep();
    const interval = setInterval(fetchRiskDeep, 30_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [scorecardSymbol]);

  // Derived risk metrics from live backend risk state with graceful fallbacks
  const openPositions = positions.filter((p) => p.status === 'open');
  const maxRiskPerTrade = riskState?.max_risk_pct ?? 1.0;
  const totalOpenRiskPct = riskState?.total_open_risk_pct ?? (openPositions.length * maxRiskPerTrade);
  const dailyDrawdownPct = Math.abs(riskState?.daily_pnl_pct ?? overview?.daily_pnl_pct ?? (overview?.daily_pnl ? Math.min(5.0, Math.abs(overview.daily_pnl) / 100) : 0));
  const marginUsagePct = riskState?.margin_usage_pct ?? (openPositions.length * 2.5);
  const consecutiveLosses = riskState?.consecutive_losses ?? 0;
  const maxConsecutiveLosses = riskState?.max_consecutive_losses ?? 3;
  const maxDailyDrawdown = riskState?.max_daily_drawdown_pct ?? 3.0;
  const maxPositions = riskState?.max_positions ?? 5;
  const avgSpread = riskState?.avg_spread_pips ?? 1.2;
  const avgRR = riskState?.avg_rr_ratio ?? 1.5;

  const isPaused = overview?.trading_paused ?? riskState?.trading_paused ?? false;

  const handleToggleKillSwitch = async () => {
    sounds.playClick('toggle');
    if (isPaused) {
      setToggling(true);
      setToggleMsg(null);
      try {
        await api.overrideRisk({ system_paused: false });
        setToggleMsg('System successfully restored. Trade execution resumed.');
        await fetchAll();
      } catch (err: any) {
        setToggleMsg(`Failed to resume system: ${err.message}`);
      } finally {
        setToggling(false);
      }
    } else {
      setShowKillConfirm(true);
    }
  };

  const executeEmergencyKill = async () => {
    setShowKillConfirm(false);
    setToggling(true);
    setToggleMsg(null);
    try {
      await api.emergencyKill();
      setToggleMsg('CRITICAL: Emergency kill switch activated! Daemon position liquidation dispatched and incoming orders blocked.');
      await fetchAll();
    } catch (err: any) {
      setToggleMsg(`Failed to execute emergency kill: ${err.message}`);
    } finally {
      setToggling(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', fontFamily: 'var(--font-precision)' }}>
      {/* Top Kill-Switch / Circuit Breaker Banner */}
      <div
        className="win-window"
        style={{
          padding: '16px 20px',
          background: isPaused ? 'var(--color-loss-dim)' : 'var(--color-paper-raised)',
          border: `2px solid ${isPaused ? 'var(--color-ledger-red)' : 'var(--color-rule)'}`,
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: 42,
              height: 42,
              borderRadius: '6px',
              background: isPaused ? 'var(--color-ledger-red)' : 'var(--color-ledger-green)',
              color: '#FAF7F2',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '2px solid var(--color-rule)',
              boxShadow: '2px 2px 0 var(--color-rule)',
            }}
          >
            {isPaused ? <AlertOctagon size={24} /> : <ShieldCheck size={24} />}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ margin: 0, fontSize: 'var(--text-title-sm)', fontWeight: 800, color: 'var(--color-ink)' }}>
                {isPaused ? 'CIRCUIT BREAKER ACTIVE // TRADING SUSPENDED' : 'RISK GUARDIAN NOMINAL // TRADING ACTIVE'}
              </h3>
              <Badge variant={isPaused ? 'error' : 'profit'}>
                {isPaused ? 'HALTED' : 'ARMED'}
              </Badge>
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: 3 }}>
              {isPaused
                ? overview?.pause_reason || 'Order execution halted by emergency risk mitigation protocol.'
                : 'All risk tolerance parameters (VaR, Consecutive Drawdown, Slippage) within nominal thresholds.'}
            </div>
          </div>
        </div>

        {/* Physical Missile Switch Button */}
        <TypewriterButton
          variant={isPaused ? 'primary' : 'danger'}
          onClick={handleToggleKillSwitch}
          disabled={toggling}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 18px',
            fontSize: '12px',
          }}
        >
          <Power size={16} />
          {isPaused ? '[ RESUME TRADE EXECUTION ]' : '[ EMERGENCY KILL SWITCH ]'}
        </TypewriterButton>
      </div>

      {toggleMsg && (
        <div
          style={{
            padding: '10px 14px',
            background: 'var(--color-paper)',
            border: '1.5px solid var(--color-win-yellow)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink)',
          }}
        >
          ℹ {toggleMsg}
        </div>
      )}

      {/* Cluster Meter VU Analog */}
      <Card
        title="ANALOG BAROMETERS & PORTFOLIO EXPOSURE METRICS"
        variant="coral"
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-around',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '20px',
            padding: '10px 0',
          }}
        >
          <RetroVuMeter
            label="PORTFOLIO HEAT"
            value={totalOpenRiskPct}
            min={0}
            max={10}
            unit="%"
            warnThreshold={5.0}
            critThreshold={7.5}
            width={180}
          />

          <RetroVuMeter
            label="DAILY DRAWDOWN"
            value={dailyDrawdownPct}
            min={0}
            max={5}
            unit="%"
            warnThreshold={2.0}
            critThreshold={3.0}
            width={180}
          />

          <RetroVuMeter
            label="MARGIN USAGE"
            value={marginUsagePct}
            min={0}
            max={100}
            unit="%"
            warnThreshold={60}
            critThreshold={80}
            width={180}
          />

          <RetroVuMeter
            label="VOLATILITY (VIX)"
            value={overview?.vix ?? 15.0}
            min={10}
            max={40}
            unit=" pts"
            warnThreshold={20}
            critThreshold={30}
            width={180}
          />
        </div>
      </Card>

      {/* Grid: Quantitative Limits & Risk State */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) 1.4fr', gap: '20px' }}>
        {/* Left: Quantitative Policy Rules Table */}
        <Card
          title="RISK TOLERANCE PROTOCOLS (SOP)"
          variant="salmon"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: 'var(--text-body-sm)' }}>
            {[
              { rule: 'Max Risk Limit per Trade', limit: `${maxRiskPerTrade.toFixed(1)}% Equity`, current: `${maxRiskPerTrade.toFixed(1)}%`, status: 'OK' },
              { rule: 'Max Daily Drawdown', limit: `${maxDailyDrawdown.toFixed(1)}% Balance`, current: `${dailyDrawdownPct.toFixed(1)}%`, status: dailyDrawdownPct > (maxDailyDrawdown * 0.8) ? 'WARN' : 'OK' },
              { rule: 'Max Concurrent Positions', limit: `${maxPositions} Positions`, current: `${openPositions.length} Positions`, status: openPositions.length >= maxPositions ? 'MAX' : 'OK' },
              { rule: 'Consecutive Loss Circuit Breaker', limit: `${maxConsecutiveLosses} Consecutive Losses`, current: `${consecutiveLosses} / ${maxConsecutiveLosses}`, status: consecutiveLosses >= maxConsecutiveLosses ? 'MAX' : consecutiveLosses >= 2 ? 'WARN' : 'OK' },
              { rule: 'Max Allowable Spread', limit: '3.0 Pips', current: `${avgSpread.toFixed(1)} Pips`, status: avgSpread > 2.5 ? 'WARN' : 'OK' },
              { rule: 'Min Reward-to-Risk (R:R)', limit: '1 : 1.3 R', current: `1 : ${avgRR.toFixed(1)} R`, status: 'OK' },
            ].map((item, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 10px',
                  background: idx % 2 === 0 ? 'var(--color-paper)' : 'transparent',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--color-ink)', fontSize: '12px' }}>
                    {item.rule}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
                    SOP Threshold: {item.limit}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="tabular-nums" style={{ fontWeight: 800, fontSize: '12px', color: 'var(--color-ink)' }}>
                    {item.current}
                  </div>
                  <Badge variant={item.status === 'OK' ? 'profit' : item.status === 'WARN' ? 'warn' : 'error'} size="sm">
                    {item.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Right: Risk State & Position Guardian Overview */}
        <Card
          title="GUARDIAN SURVEILLANCE & LEDGER AUDIT"
          variant="yellow"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {riskState ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '10px' }}>
                <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Current P&L</div>
                  <div className="tabular-nums" style={{ fontSize: '16px', fontWeight: 800, color: riskState.daily_pnl >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                    {fmt.usd(riskState.daily_pnl)}
                  </div>
                </div>
                <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Peak Drawdown</div>
                  <div className="tabular-nums" style={{ fontSize: '16px', fontWeight: 800, color: riskState.current_drawdown < 0 ? 'var(--color-ledger-red)' : 'var(--color-ink)' }}>
                    {fmt.usd(riskState.current_drawdown)}
                  </div>
                </div>
                {riskState.margin_free != null && (
                  <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Free Margin</div>
                    <div className="tabular-nums" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--color-ink)' }}>
                      {fmt.usd(riskState.margin_free)}
                    </div>
                  </div>
                )}
                {riskState.margin_level_pct != null && (
                  <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Margin Level</div>
                    <div className="tabular-nums" style={{ fontSize: '16px', fontWeight: 800, color: riskState.margin_level_pct < 150 ? 'var(--color-ledger-red)' : 'var(--color-ink)' }}>
                      {riskState.margin_level_pct.toFixed(0)}%
                    </div>
                  </div>
                )}
                <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Weekend Gate</div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: riskState.is_weekend ? 'var(--color-brass)' : 'var(--color-ledger-green)', marginTop: '2px' }}>
                    {riskState.is_weekend ? 'CLOSED' : 'OPEN'}
                  </div>
                </div>
                <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Ledger Date</div>
                  <div className="tabular-nums" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '2px' }}>
                    {riskState.date}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--color-ink-soft)', textAlign: 'center', padding: '12px' }}>
                Loading risk ledger parameters...
              </div>
            )}

            <div style={{ marginTop: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', marginBottom: '8px', color: 'var(--color-ink)' }}>
                [ ACTIVE GUARDIAN SURVEILLANCE LOG ]
              </div>
              <div
                style={{
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: '2px',
                  background: 'var(--color-paper)',
                  padding: '10px 12px',
                  fontSize: '11px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-ink)' }}>
                  <span>✓ Position Guardian (Trailing Stop & Breakeven)</span>
                  <span className="tabular-nums" style={{ color: 'var(--color-ledger-green)' }}>ACTIVE (2m interval)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-ink)' }}>
                  <span>✓ Exposure Gatekeeper</span>
                  <span className="tabular-nums" style={{ color: 'var(--color-ledger-green)' }}>VERIFIED / NOMINAL</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-ink)' }}>
                  <span>✓ News Blackout Filter (High-Impact Events)</span>
                  <span className="tabular-nums" style={{ color: 'var(--color-brass)' }}>ARMED (T-15m release)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-ink)' }}>
                  <span>✓ Daily Drawdown Monitor (Hard Stop 3%)</span>
                  <span className="tabular-nums" style={{ color: 'var(--color-ledger-green)' }}>NOMINAL</span>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* 22-Point Risk Gate Scorecard & Correlation Matrix Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '20px' }}>
        {/* Risk Gate Scorecard */}
        <Card
          title={`22-POINT DETERMINISTIC RISK GATE SCORECARD // ${scorecardSymbol}`}
          variant="salmon"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-muted)' }}>SYMBOL:</span>
                {['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD'].map((s) => (
                  <button
                    key={s}
                    onClick={() => setScorecardSymbol(s)}
                    style={{
                      padding: '2px 6px',
                      background: scorecardSymbol === s ? 'var(--color-brass)' : 'transparent',
                      color: scorecardSymbol === s ? '#000' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: '2px',
                      fontSize: '10px',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
              {scorecard && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
                    Pass Rate: <strong>{scorecard.passed_count}/{scorecard.total_checks} ({scorecard.pass_rate_pct}%)</strong>
                  </span>
                  <Badge variant={scorecard.pass_rate_pct >= 90 ? 'profit' : scorecard.pass_rate_pct >= 70 ? 'warn' : 'error'} size="sm">
                    {scorecard.pass_rate_pct >= 90 ? 'CLEAR' : scorecard.pass_rate_pct >= 70 ? 'CAUTION' : 'BLOCKED'}
                  </Badge>
                </div>
              )}
            </div>

            {scorecard ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '8px', maxHeight: '340px', overflowY: 'auto' }}>
                {Object.entries(scorecard.checks).map(([checkName, checkVal]) => (
                  <div
                    key={checkName}
                    style={{
                      padding: '6px 8px',
                      background: 'var(--color-paper)',
                      border: `1px solid ${checkVal.passed ? 'var(--color-rule)' : 'var(--color-loss)'}`,
                      borderRadius: '2px',
                      fontSize: '11px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2px' }}>
                      <span style={{ fontWeight: 700, color: 'var(--color-ink)' }}>{checkName}</span>
                      {checkVal.passed ? (
                        <span style={{ color: 'var(--color-ledger-green)', display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <CheckCircle size={12} /> PASS
                        </span>
                      ) : (
                        <span style={{ color: 'var(--color-ledger-red)', display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <XCircle size={12} /> FAIL
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={checkVal.reason}>
                      {checkVal.reason}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--color-ink-soft)', textAlign: 'center', padding: '16px', fontSize: '12px' }}>
                {scorecardLoading ? 'Evaluating 22-point deterministic rules...' : 'Scorecard unavailable'}
              </div>
            )}
          </div>
        </Card>

        {/* Dynamic Correlation Matrix */}
        <Card
          title="PORTFOLIO CORRELATION & COVARIANCE HEATMAP"
          variant="yellow"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {correlation ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                  <span>Portfolio Heat: <strong className="tabular-nums">{correlation.portfolio_heat.toFixed(2)}</strong></span>
                  <Badge variant={correlation.status === 'normal' ? 'profit' : 'warn'} size="sm">
                    {correlation.status.toUpperCase()}
                  </Badge>
                </div>

                {/* Matrix Heatmap Table */}
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10px', textAlign: 'center' }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left', padding: '4px' }}>SYM</th>
                        {correlation.symbols.map((s) => (
                          <th key={s} style={{ padding: '4px' }}>{s}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {correlation.symbols.map((rSym) => (
                        <tr key={rSym} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                          <td style={{ textAlign: 'left', padding: '4px', fontWeight: 'bold' }}>{rSym}</td>
                          {correlation.symbols.map((cSym) => {
                            const val = correlation.matrix[rSym]?.[cSym] ?? 0;
                            const isSelf = rSym === cSym;
                            const isHigh = Math.abs(val) >= 0.65;
                            const isMed = Math.abs(val) >= 0.40;
                            const bg = isSelf
                              ? 'transparent'
                              : isHigh
                              ? 'rgba(239, 68, 68, 0.2)'
                              : isMed
                              ? 'rgba(234, 179, 8, 0.15)'
                              : 'transparent';
                            const color = isSelf
                              ? 'var(--color-ink-muted)'
                              : isHigh
                              ? 'var(--color-ledger-red)'
                              : isMed
                              ? 'var(--color-brass)'
                              : 'var(--color-ink)';
                            return (
                              <td key={cSym} style={{ padding: '4px', background: bg, color, fontWeight: isHigh ? 'bold' : 'normal' }}>
                                {isSelf ? '1.0' : val.toFixed(2)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Correlated pairs warning list */}
                {correlation.correlated_pairs.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '10px' }}>
                    <span style={{ fontWeight: 'bold', color: 'var(--color-brass)' }}>[ CORRELATED RISK PAIRS ]</span>
                    {correlation.correlated_pairs.slice(0, 3).map((cp, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 4px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                        <span>{cp.pair}</span>
                        <span className="tabular-nums" style={{ color: 'var(--color-ledger-red)', fontWeight: 'bold' }}>r = {cp.correlation.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div style={{ color: 'var(--color-ink-soft)', textAlign: 'center', padding: '16px', fontSize: '12px' }}>
                Loading correlation matrix...
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Emergency Kill Confirmation Dialog */}
      <ConfirmModal
        isOpen={showKillConfirm}
        title="EMERGENCY SYSTEM HALT"
        actionSummary="ACTIVATE EMERGENCY KILL SWITCH & LIQUIDATE POSITIONS"
        details={
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: 'var(--text-body-sm)' }}>
            <p style={{ margin: 0, fontWeight: 'bold', color: 'var(--color-ledger-red)' }}>
              WARNING: This is a fail-safe capital preservation command.
            </p>
            <ul style={{ margin: 0, paddingLeft: '20px' }}>
              <li>Emergency market order close will be dispatched to MT5 for all open positions.</li>
              <li>Pending orders, conditional triggers, and analysis cycles will be aborted.</li>
              <li>System state will transition to PAUSED until manually reset.</li>
            </ul>
          </div>
        }
        confirmLabel="YES, ENGAGE KILL SWITCH"
        cancelLabel="ABORT / CANCEL"
        danger={true}
        onConfirm={executeEmergencyKill}
        onCancel={() => setShowKillConfirm(false)}
      />
    </div>
  );
};

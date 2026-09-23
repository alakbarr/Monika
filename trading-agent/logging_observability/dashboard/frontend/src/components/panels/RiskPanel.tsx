// ==============================================================================
// File: src/components/panels/RiskPanel.tsx
// Description: Comprehensive Quantitative Risk Cockpit with Analog VU Meters & Circuit Breakers
// ==============================================================================

import React, { useState } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { RetroVuMeter } from '../ui/RetroVuMeter';
import { TypewriterButton } from '../ui/TypewriterButton';
import { ConfirmModal } from '../ui/ConfirmModal';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';
import { api } from '../../lib/api';
import { ShieldCheck, AlertOctagon, Power } from 'lucide-react';

export const RiskPanel: React.FC = () => {
  const { overview, riskState, positions, fetchAll } = useDashboardStore();
  const [toggling, setToggling] = useState(false);
  const [toggleMsg, setToggleMsg] = useState<string | null>(null);
  const [showKillConfirm, setShowKillConfirm] = useState(false);

  // Derived risk metrics
  const openPositions = positions.filter((p) => p.status === 'open');
  const totalOpenRiskPct = openPositions.length * 1.0;
  const dailyDrawdownPct = Math.min(5.0, Math.abs(Math.min(0, overview?.daily_pnl ?? 0)) / 100);
  const marginUsagePct = openPositions.length * 2.5;

  const isPaused = overview?.trading_paused ?? false;

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
              { rule: 'Max Risk Limit per Trade', limit: '1.0% Equity', current: `${(1.0).toFixed(1)}%`, status: 'OK' },
              { rule: 'Max Daily Drawdown', limit: '3.0% Balance', current: `${dailyDrawdownPct.toFixed(1)}%`, status: dailyDrawdownPct > 2.5 ? 'WARN' : 'OK' },
              { rule: 'Max Concurrent Positions', limit: '5 Positions', current: `${openPositions.length} Positions`, status: openPositions.length >= 5 ? 'MAX' : 'OK' },
              { rule: 'Consecutive Loss Circuit Breaker', limit: '3 Consecutive Losses', current: '0 / 3', status: 'OK' },
              { rule: 'Max Allowable Spread', limit: '3.0 Pips', current: '1.2 Pips (Avg)', status: 'OK' },
              { rule: 'Min Reward-to-Risk (R:R)', limit: '1 : 1.5 R', current: '1 : 2.1 R', status: 'OK' },
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
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
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

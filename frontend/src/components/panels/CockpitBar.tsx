import React, { useMemo, useState } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { SegmentedProgressBar } from '../ui/SegmentedProgressBar';
import { fmt, vixSentiment } from '../../lib/formatters';
import { api } from '../../lib/api';

interface CockpitBarProps {
  showSmcChart?: boolean;
  onToggleSmcChart?: () => void;
}

interface ScrubPoint {
  index: number;
  equity: number;
  returnPct: number;
  label: string;
}

export const CockpitBar: React.FC<CockpitBarProps> = ({
  showSmcChart = false,
  onToggleSmcChart,
}) => {
  const { overview, paperStats, riskState, loading, wsConnected, fetchAll } = useDashboardStore();
  const [scrubIndex, setScrubIndex] = useState<number | null>(null);
  const [triggeringCycle, setTriggeringCycle] = useState(false);

  const dailyPnl = overview?.daily_pnl ?? 0;
  const totalPnlPct = paperStats?.total_pnl_pct ?? overview?.daily_pnl_pct ?? 0;

  // Fail-closed verified equity resolution (never invent a hardcoded $10,000 fallback)
  const verifiedCurrentEquity = useMemo<number | null>(() => {
    if (overview?.account_equity != null && overview.account_equity > 0) {
      return overview.account_equity;
    }
    if (riskState?.account_equity != null && riskState.account_equity > 0) {
      return riskState.account_equity;
    }
    if (
      riskState?.margin_used != null &&
      riskState?.margin_free != null &&
      riskState.margin_used + riskState.margin_free > 0
    ) {
      return Number((riskState.margin_used + riskState.margin_free).toFixed(2));
    }
    if (overview?.account_balance != null && overview.account_balance > 0) {
      return Number((overview.account_balance + dailyPnl).toFixed(2));
    }
    if (riskState?.account_balance != null && riskState.account_balance > 0) {
      return Number((riskState.account_balance + dailyPnl).toFixed(2));
    }
    return null;
  }, [overview, riskState, dailyPnl]);

  const hasVerifiedEquity = verifiedCurrentEquity !== null;
  const sessionBaseEquity =
    verifiedCurrentEquity !== null
      ? Math.max(1, Number((verifiedCurrentEquity - dailyPnl).toFixed(2)))
      : null;

  // Build interactive scrubbing equity series anchored to verified account equity (or indexed 100.0 if unverified)
  const series = useMemo<ScrubPoint[]>(() => {
    const recent = paperStats?.recent_20 ?? [];
    if (verifiedCurrentEquity !== null && sessionBaseEquity !== null) {
      if (recent.length === 0) {
        const pct = ((verifiedCurrentEquity - sessionBaseEquity) / sessionBaseEquity) * 100;
        return [
          { index: 0, equity: sessionBaseEquity, returnPct: 0, label: 'SESSION OPEN' },
          { index: 1, equity: verifiedCurrentEquity, returnPct: Number(pct.toFixed(2)), label: 'LIVE SNAPSHOT' },
        ];
      }

      // Reconstruct path ending at verifiedCurrentEquity so live snapshot is 100% consistent with account telemetry
      const relMultipliers: number[] = [1.0];
      let mult = 1.0;
      recent.forEach((t) => {
        mult = mult * (1 + (t.pnl_pct || 0) / 100);
        relMultipliers.push(mult);
      });
      const finalMult = relMultipliers[relMultipliers.length - 1] || 1.0;
      const startAnchor = verifiedCurrentEquity / finalMult;

      const pts: ScrubPoint[] = [
        { index: 0, equity: Number(startAnchor.toFixed(2)), returnPct: 0, label: 'WINDOW BASELINE' },
      ];
      recent.forEach((t, idx) => {
        const eqVal = startAnchor * relMultipliers[idx + 1];
        const retPct = ((eqVal - startAnchor) / startAnchor) * 100;
        pts.push({
          index: idx + 1,
          equity: Number(eqVal.toFixed(2)),
          returnPct: Number(retPct.toFixed(2)),
          label: `TRADE #${idx + 1} · ${t.symbol} (${t.exit_reason || 'CLOSED'})`,
        });
      });
      // Ensure the final live point matches verifiedCurrentEquity exactly
      pts[pts.length - 1] = {
        ...pts[pts.length - 1],
        equity: verifiedCurrentEquity,
        returnPct:
          overview?.daily_pnl_pct != null
            ? Number(overview.daily_pnl_pct.toFixed(2))
            : Number((((verifiedCurrentEquity - sessionBaseEquity) / sessionBaseEquity) * 100).toFixed(2)),
        label: 'LIVE VERIFIED EQUITY',
      };
      return pts;
    }

    // Unverified dollar equity: compute pure normalized index (Base 100.0) for chart shape only
    let idxVal = 100.0;
    const pts: ScrubPoint[] = [{ index: 0, equity: 100.0, returnPct: 0, label: 'INDEX BASE (100.0)' }];
    recent.forEach((t, idx) => {
      idxVal = idxVal * (1 + (t.pnl_pct || 0) / 100);
      pts.push({
        index: idx + 1,
        equity: Number(idxVal.toFixed(2)),
        returnPct: Number((idxVal - 100.0).toFixed(2)),
        label: `TRADE #${idx + 1} · ${t.symbol} (${t.exit_reason || 'CLOSED'})`,
      });
    });
    return pts;
  }, [paperStats, verifiedCurrentEquity, sessionBaseEquity, overview]);

  const activePoint =
    scrubIndex !== null && series[scrubIndex]
      ? series[scrubIndex]
      : series[series.length - 1];

  const displayedEquity = hasVerifiedEquity ? (activePoint?.equity ?? verifiedCurrentEquity!) : 0;
  const displayedReturnPct = activePoint?.returnPct ?? totalPnlPct;
  const displayedDeltaUsd =
    hasVerifiedEquity && sessionBaseEquity !== null
      ? scrubIndex !== null && series[0]
        ? displayedEquity - series[0].equity
        : dailyPnl
      : dailyPnl;

  const wholeDollars = Math.floor(Math.abs(displayedEquity)).toLocaleString('en-US');
  const cents = Math.round((Math.abs(displayedEquity) % 1) * 100)
    .toString()
    .padStart(2, '0');

  const isPositive = displayedDeltaUsd >= 0;
  const deltaColor =
    Math.abs(displayedDeltaUsd) < 0.005
      ? 'var(--color-ink-muted)'
      : isPositive
      ? 'var(--color-profit)'
      : 'var(--color-loss)';

  const totalTrades = paperStats?.total_trades ?? 0;
  const winRate = paperStats?.win_rate_pct ?? 0;
  const winRateDisplay = totalTrades > 0 ? `${winRate.toFixed(1)}%` : '—';
  const vix = overview?.vix ?? null;
  const vixS = vix != null ? vixSentiment(vix) : { label: 'N/A', color: 'var(--color-ink-soft)' };

  const ddPct = Math.abs(overview?.drawdown_pct ?? 0);
  const maxDdCap = riskState?.max_daily_drawdown_pct ?? 3.0;

  // Build SVG path for interactive scrubbing equity curve
  const svgWidth = 1000;
  const svgHeight = 148;
  const { linePath, areaPath, coords } = useMemo(() => {
    if (series.length < 2) {
      return {
        linePath: `M 0 ${svgHeight / 2} L ${svgWidth} ${svgHeight / 2}`,
        areaPath: `M 0 ${svgHeight / 2} L ${svgWidth} ${svgHeight / 2} L ${svgWidth} ${svgHeight} L 0 ${svgHeight} Z`,
        coords: [{ x: 0, y: svgHeight / 2 }, { x: svgWidth, y: svgHeight / 2 }],
      };
    }
    const values = series.map((p) => p.equity);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = Math.max(maxVal - minVal, 1);
    const padTop = 18;
    const padBottom = 18;
    const usableH = svgHeight - padTop - padBottom;

    const pts = series.map((p, i) => {
      const x = (i / (series.length - 1)) * svgWidth;
      const y = padTop + usableH - ((p.equity - minVal) / range) * usableH;
      return { x, y };
    });

    const d = pts
      .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`)
      .join(' ');
    const area = `${d} L ${svgWidth} ${svgHeight} L 0 ${svgHeight} Z`;
    return { linePath: d, areaPath: area, coords: pts };
  }, [series]);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (series.length < 2) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.round(relX * (series.length - 1));
    setScrubIndex(idx);
  };

  const handleTriggerCycle = async () => {
    if (triggeringCycle) return;
    setTriggeringCycle(true);
    try {
      await api.triggerCycle(true, 'Manual cycle triggered from Capital Desk');
      await fetchAll();
    } catch {
      // Handled by global error state
    } finally {
      setTriggeringCycle(false);
    }
  };

  return (
    <section
      className="liquid-glass-panel editorial-section"
      aria-label="Portfolio Equity Monument & Telemetry Ribbon"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '18px',
        padding: '20px 24px',
      }}
    >
      {!wsConnected && (
        <div
          style={{
            padding: '6px 12px',
            background: 'var(--color-loss-soft)',
            border: '1px solid var(--color-loss)',
            borderRadius: '2px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            color: 'var(--color-loss)',
            letterSpacing: '0.06em',
          }}
        >
          <span>STALE TELEMETRY — REALTIME STREAM DISCONNECTED · DISPLAYING LAST RECORDED SNAPSHOT</span>
          <span>RECONNECTING…</span>
        </div>
      )}

      {/* Sculptural Hero Equity Monument Row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '20px',
        }}
      >
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '6px',
            }}
          >
            <span className="editorial-kicker">
              {scrubIndex !== null ? `HISTORICAL SCRUB · ${activePoint.label}` : 'NET PORTFOLIO LIQUIDATION VALUE'}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--color-ink-soft)',
                padding: '1px 6px',
                border: '1px solid var(--color-border)',
                borderRadius: '2px',
              }}
            >
              {overview?.is_live ? 'LIVE BROKER LEDGER' : 'PAPER VALIDATION LEDGER'}
            </span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: '16px',
              flexWrap: 'wrap',
            }}
          >
            <div className="equity-monument tabular-nums">
              {loading ? (
                '—'
              ) : !hasVerifiedEquity ? (
                <span style={{ fontSize: '36px', color: 'var(--color-warn)', fontFamily: 'var(--font-mono)' }}>
                  UNVERIFIED
                </span>
              ) : (
                <>
                  {displayedEquity < 0 ? '-$' : '$'}
                  {wholeDollars}
                  <span className="cents">.{cents}</span>
                </>
              )}
            </div>

            {!hasVerifiedEquity && !loading && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  fontWeight: 600,
                  color: 'var(--color-warn)',
                  background: 'var(--color-warn-bg)',
                  border: '1px solid var(--color-warn-border)',
                  padding: '3px 8px',
                  borderRadius: 'var(--radius-xs)',
                }}
              >
                ACCOUNT EQUITY TELEMETRY OFFLINE · FAIL-CLOSED
              </span>
            )}

            <div
              className="tabular-nums"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                fontWeight: 600,
                color: deltaColor,
                padding: '3px 8px',
                borderRadius: '2px',
                background:
                  Math.abs(displayedDeltaUsd) < 0.005
                    ? 'var(--color-surface-well)'
                    : isPositive
                    ? 'var(--color-profit-soft)'
                    : 'var(--color-loss-soft)',
              }}
            >
              <span>
                {isPositive ? '+' : ''}
                {fmt.usd(displayedDeltaUsd, false)}
              </span>
              <span>
                ({isPositive ? '+' : ''}
                {displayedReturnPct.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>

        {/* Right KPI Strip + SMC Chart Toggle */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '24px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <div>
              <div className="editorial-kicker">EXPECTANCY / TRADE</div>
              <div
                className="tabular-nums"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '15px',
                  fontWeight: 600,
                  color: paperStats?.has_positive_edge ? 'var(--color-profit)' : 'var(--color-ink)',
                  marginTop: '2px',
                }}
              >
                {fmt.pct(paperStats?.expectancy_per_trade_pct, true)}
              </div>
            </div>
            <div>
              <div className="editorial-kicker">AVG R:R ACHIEVED</div>
              <div
                className="tabular-nums"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '15px',
                  fontWeight: 600,
                  color: 'var(--color-ink)',
                  marginTop: '2px',
                }}
              >
                {paperStats?.avg_rr_achieved != null ? `${paperStats.avg_rr_achieved.toFixed(2)}R` : '—'}
              </div>
            </div>
            <div>
              <div className="editorial-kicker">WIN RATE ({totalTrades}/50)</div>
              <div
                className="tabular-nums"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '15px',
                  fontWeight: 600,
                  color: winRate >= 55 ? 'var(--color-profit)' : 'var(--color-ink)',
                  marginTop: '2px',
                }}
              >
                {winRateDisplay}
              </div>
            </div>
          </div>

          {onToggleSmcChart && (
            <button
              type="button"
              onClick={onToggleSmcChart}
              style={{
                padding: '6px 12px',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: showSmcChart ? 'var(--color-surface)' : 'var(--color-ink)',
                background: showSmcChart ? 'var(--color-ink)' : 'transparent',
                border: '1px solid var(--color-border-strong)',
                borderRadius: '2px',
                cursor: 'pointer',
              }}
            >
              {showSmcChart ? 'HIDE SMC CHART' : 'INSPECT SMC & TIMESFM CHART'}
            </button>
          )}
        </div>
      </div>

      {/* Interactive Scrubbing Equity Curve SVG */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: `${svgHeight}px`,
          borderTop: '1px solid var(--color-border)',
          borderBottom: '1px solid var(--color-border)',
          cursor: 'crosshair',
        }}
      >
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height: '100%', display: 'block', overflow: 'visible' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setScrubIndex(null)}
        >
          <defs>
            <linearGradient id="monika-equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={isPositive ? 'var(--color-profit)' : 'var(--color-loss)'}
                stopOpacity="0.14"
              />
              <stop
                offset="100%"
                stopColor={isPositive ? 'var(--color-profit)' : 'var(--color-loss)'}
                stopOpacity="0.0"
              />
            </linearGradient>
          </defs>

          {/* Subtle horizontal baseline */}
          <line
            x1={0}
            y1={svgHeight / 2}
            x2={svgWidth}
            y2={svgHeight / 2}
            stroke="var(--color-border)"
            strokeDasharray="3 3"
            strokeWidth={1}
          />

          {/* Area fill */}
          <path d={areaPath} fill="url(#monika-equity-fill)" />

          {/* Crisp 1.75px equity trajectory */}
          <path
            d={linePath}
            fill="none"
            stroke={isPositive ? 'var(--color-profit)' : 'var(--color-loss)'}
            strokeWidth={1.75}
            vectorEffect="non-scaling-stroke"
          />

          {/* Active Scrub Crosshair Hairline & Pin */}
          {scrubIndex !== null && coords[scrubIndex] && (
            <g>
              <line
                x1={coords[scrubIndex].x}
                y1={0}
                x2={coords[scrubIndex].x}
                y2={svgHeight}
                stroke="var(--color-ink)"
                strokeWidth={1}
                strokeDasharray="2 2"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={coords[scrubIndex].x}
                cy={coords[scrubIndex].y}
                r={4}
                fill="var(--color-surface)"
                stroke="var(--color-ink)"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>

        <div
          style={{
            position: 'absolute',
            right: '8px',
            bottom: '6px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--color-ink-soft)',
            pointerEvents: 'none',
          }}
        >
          {scrubIndex !== null ? 'RELEASE CURSOR TO RETURN TO LIVE LEDGER' : 'HOVER CURVE TO SCRUB HISTORICAL EQUITY'}
        </div>
      </div>

      {/* 6-Cell Continuous Telemetry Ribbon */}
      <div className="cockpit-bar" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(175px, 1fr))' }}>
        {/* 1. Net Daily P&L */}
        <div className="cockpit-item swiss-crosshair">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="editorial-kicker">NET DAILY P&L</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                fontWeight: 600,
                color:
                  Math.abs(dailyPnl) < 0.005
                    ? 'var(--color-ink-soft)'
                    : dailyPnl > 0
                    ? 'var(--color-profit)'
                    : 'var(--color-loss)',
              }}
            >
              {Math.abs(dailyPnl) < 0.005 ? 'FLAT' : dailyPnl > 0 ? 'PROFIT' : 'LOSS'}
            </span>
          </div>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '18px',
              fontWeight: 600,
              color:
                Math.abs(dailyPnl) < 0.005
                  ? 'var(--color-ink)'
                  : dailyPnl > 0
                  ? 'var(--color-profit)'
                  : 'var(--color-loss)',
            }}
          >
            {loading ? '…' : fmt.usd(dailyPnl, true)}
          </div>
          <div className="tabular-nums" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
            Session Return: {overview?.daily_pnl_pct != null ? `${overview.daily_pnl_pct.toFixed(2)}%` : '0.00%'}
          </div>
        </div>

        {/* 2. Free Margin & Margin Level */}
        <div className="cockpit-item swiss-crosshair">
          <span className="editorial-kicker">MARGIN TELEMETRY</span>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--color-ink)',
            }}
          >
            {riskState?.margin_free != null ? fmt.usd(riskState.margin_free, false) : '$10,000.00'}
          </div>
          <div className="tabular-nums" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
            Level: {riskState?.margin_level_pct != null ? `${riskState.margin_level_pct.toFixed(0)}%` : '100%'} · Used:{' '}
            {riskState?.margin_usage_pct != null ? `${riskState.margin_usage_pct.toFixed(1)}%` : '0.0%'}
          </div>
        </div>

        {/* 3. Daily Drawdown vs Mechanical RiskGate Cap */}
        <div className="cockpit-item swiss-crosshair">
          <SegmentedProgressBar
            value={ddPct}
            max={maxDdCap}
            label="DRAWDOWN VS CAP"
            valueDisplay={`${ddPct.toFixed(2)}% / ${maxDdCap.toFixed(1)}%`}
          />
          <div className="tabular-nums" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
            Max DD: {fmt.usd(overview?.current_drawdown ?? 0)} (Hard Gate {maxDdCap.toFixed(1)}%)
          </div>
        </div>

        {/* 4. Win Rate & Graduation Gate */}
        <div className="cockpit-item swiss-crosshair">
          <SegmentedProgressBar
            value={totalTrades > 0 ? winRate : 0}
            max={100}
            label="WIN RATE BENCHMARK"
            valueDisplay={winRateDisplay}
          />
          <div className="tabular-nums" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
            SOP Gate: ≥55.0% ({totalTrades}/50 Paper Trades)
          </div>
        </div>

        {/* 5. VIX Volatility Regime */}
        <div className="cockpit-item swiss-crosshair">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="editorial-kicker">VIX REGIME</span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                fontWeight: 600,
                color: vixS.color,
              }}
            >
              <span style={{ width: 5, height: 5, background: vixS.color, display: 'inline-block' }} />
              {vixS.label.toUpperCase()}
            </span>
          </div>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--color-ink)',
            }}
          >
            {vix != null ? vix.toFixed(2) : '—'}
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
            S&P 500 Implied Volatility
          </div>
        </div>

        {/* 6. Active Positions & Cycle Execution */}
        <div className="cockpit-item swiss-crosshair">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="editorial-kicker">EXECUTION ENGINE</span>
            <button
              type="button"
              onClick={handleTriggerCycle}
              disabled={triggeringCycle}
              style={{
                padding: '2px 6px',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--color-ink)',
                background: 'transparent',
                border: '1px solid var(--color-border-strong)',
                borderRadius: '2px',
                cursor: triggeringCycle ? 'wait' : 'pointer',
              }}
              title="Trigger immediate autonomous analysis cycle"
            >
              {triggeringCycle ? 'RUNNING…' : '+ RUN CYCLE'}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span
              className="tabular-nums"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '18px',
                fontWeight: 600,
                color: 'var(--color-ink)',
              }}
            >
              {overview?.open_positions_count ?? 0}
            </span>
            <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-soft)' }}>
              OPEN POSITIONS
            </span>
          </div>
          <div
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              color: overview?.trading_paused ? 'var(--color-loss)' : 'var(--color-profit)',
            }}
          >
            {overview?.trading_paused ? '■ HALTED' : '■ ACTIVE ENGINE'}
          </div>
        </div>
      </div>
    </section>
  );
};

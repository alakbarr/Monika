import React from 'react';
import { TrendingUp, DollarSign, Target, Zap, Calculator, Activity } from 'lucide-react';
import { MetricCard } from '../ui/MetricCard';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

export const AgentStatusBar: React.FC = () => {
  const { overview, paperStats, loading } = useDashboardStore();

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
        gap: '12px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <MetricCard
        title="Open Positions"
        value={overview?.open_positions_count ?? 0}
        subtitle="Currently Active"
        icon={<TrendingUp size={16} color="var(--color-brass)" />}
        loading={loading}
      />

      <MetricCard
        title="Daily P&L"
        value={
          <span
            style={{
              color: (overview?.daily_pnl ?? 0) >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
            }}
          >
            {(overview?.daily_pnl ?? 0) >= 0 ? '▲ +' : '▼ '}
            {fmt.usd(Math.abs(overview?.daily_pnl ?? 0))}
          </span>
        }
        subtitle={`Drawdown: ${fmt.usd(overview?.current_drawdown ?? 0)}`}
        accent={!overview?.trading_paused}
        icon={<DollarSign size={16} color="var(--color-brass)" />}
        loading={loading}
      />

      <MetricCard
        title="Win Rate"
        value={`${paperStats?.win_rate_pct?.toFixed(1) ?? '—'}%`}
        subtitle={`${paperStats?.total_trades ?? 0} trades evaluated`}
        icon={<Target size={16} color="var(--color-brass)" />}
        loading={loading}
      />

      <MetricCard
        title="Edge Status"
        value={
          paperStats ? (
            <span
              style={{
                color: paperStats.has_positive_edge
                  ? 'var(--color-ledger-green)'
                  : paperStats.edge_alert
                  ? 'var(--color-ledger-red)'
                  : 'var(--color-brass)',
                fontSize: 'var(--text-title-sm)',
                fontWeight: 'bold',
              }}
            >
              {paperStats.has_positive_edge ? '[ POSITIVE ]' : paperStats.edge_alert ? '[ NO EDGE ]' : '[ NEUTRAL ]'}
            </span>
          ) : (
            '—'
          )
        }
        subtitle={paperStats ? `${fmt.r(paperStats.expectancy_per_trade_R)} / trade` : ''}
        icon={<Zap size={16} color="var(--color-brass)" />}
        loading={loading}
      />

      <MetricCard
        title="Expectancy"
        value={fmt.pct(paperStats?.expectancy_per_trade_pct, true)}
        subtitle={`Avg R:R ${paperStats?.avg_rr_achieved?.toFixed(2) ?? '—'}`}
        icon={<Calculator size={16} color="var(--color-ink-soft)" />}
        loading={loading}
      />

      <MetricCard
        title="VIX Volatility"
        value={overview?.vix?.toFixed(2) ?? '—'}
        subtitle={overview?.vix_date ? fmt.datetime(overview.vix_date) : ''}
        icon={<Activity size={16} color="var(--color-brass)" />}
        loading={loading}
      />
    </div>
  );
};

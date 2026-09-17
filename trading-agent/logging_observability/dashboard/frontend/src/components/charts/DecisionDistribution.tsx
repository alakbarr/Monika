import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { DecisionDistribution } from '../../types/api';

interface DecisionDistChartProps {
  data: DecisionDistribution;
}

const DECISION_COLORS: Record<string, string> = {
  buy: 'var(--color-ledger-green)',
  sell: 'var(--color-ledger-red)',
  wait: 'var(--color-brass)',
  avoid: 'var(--color-ink-soft)',
};

export const DecisionDistChart: React.FC<DecisionDistChartProps> = ({ data }) => {
  const chartData = Object.entries(data).map(([symbol, stats]) => ({
    symbol,
    buy: stats.buy || 0,
    sell: stats.sell || 0,
    wait: stats.wait || 0,
    avoid: stats.avoid || 0,
    trade_rate: stats.trade_rate_pct,
  }));

  return (
    <div>
      {/* Vintage decision legend */}
      <div
        style={{
          display: 'flex',
          gap: '16px',
          marginBottom: '12px',
          fontSize: '11px',
          fontFamily: 'var(--font-precision)',
          color: 'var(--color-ink-soft)',
          justifyContent: 'flex-end',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ width: 9, height: 9, background: 'var(--color-ledger-green)', display: 'inline-block', borderRadius: 1, border: '1px solid var(--color-rule)' }} />
          Long (Buy)
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ width: 9, height: 9, background: 'var(--color-ledger-red)', display: 'inline-block', borderRadius: 1, border: '1px solid var(--color-rule)' }} />
          Short (Sell)
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ width: 9, height: 9, background: 'var(--color-brass)', display: 'inline-block', borderRadius: 1, border: '1px solid var(--color-rule)' }} />
          Wait (Hold)
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <span style={{ width: 9, height: 9, background: 'var(--color-ink-soft)', display: 'inline-block', borderRadius: 1, border: '1px solid var(--color-rule)' }} />
          Neutral / Avoid
        </span>
      </div>

      <ResponsiveContainer width="100%" height={180}>
      <BarChart data={chartData} barSize={12} barGap={2}>
        <XAxis
          dataKey="symbol"
          tick={{ fill: 'var(--color-ink-soft)', fontSize: 10, fontFamily: 'var(--font-precision)' }}
          axisLine={{ stroke: 'var(--color-rule)' }}
          tickLine={false}
        />
        <YAxis hide />
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            return (
              <div
                className="ledger-card"
                style={{
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: 'var(--radius-card)',
                  padding: '8px 12px',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-precision)',
                  boxShadow: '2px 2px 0 var(--color-rule)',
                }}
              >
                <div style={{ fontWeight: 700, marginBottom: '6px', color: 'var(--color-ink)' }}>
                  {label}
                </div>
                {payload.map((p: any) => (
                  <div
                    key={p.dataKey}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: '16px',
                      color: DECISION_COLORS[p.dataKey] || 'var(--color-ink-soft)',
                      fontFamily: 'var(--font-precision)',
                    }}
                  >
                    <span style={{ textTransform: 'uppercase' }}>{p.dataKey}</span>
                    <span className="tabular-nums" style={{ fontWeight: 700 }}>{p.value}</span>
                  </div>
                ))}
              </div>
            );
          }}
        />
        <Bar dataKey="buy" stackId="a" fill="var(--color-ledger-green)" radius={[0, 0, 0, 0]} />
        <Bar dataKey="sell" stackId="a" fill="var(--color-ledger-red)" />
        <Bar dataKey="wait" stackId="a" fill="var(--color-brass)" />
        <Bar dataKey="avoid" stackId="a" fill="var(--color-ink-soft)" radius={[1, 1, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
    </div>
  );
};

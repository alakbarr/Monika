import React from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { format, parseISO } from 'date-fns';
import type { VixDataPoint } from '../../types/api';
import { vixSentiment } from '../../lib/formatters';

interface VixSparklineProps {
  data: VixDataPoint[];
  height?: number;
  showAxes?: boolean;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as VixDataPoint;
  const s = vixSentiment(d.close);
  return (
    <div
      className="ledger-card"
      style={{
        background: 'var(--color-paper-raised)',
        border: '1px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        padding: '6px 10px',
        fontFamily: 'var(--font-precision)',
        boxShadow: '2px 2px 0 var(--color-rule)',
      }}
    >
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
        {format(parseISO(d.date), 'dd MMM')}
      </div>
      <div
        className="tabular-nums"
        style={{
          fontSize: 'var(--text-body-sm)',
          fontFamily: 'var(--font-precision)',
          color: 'var(--color-brass)',
          fontWeight: 700,
        }}
      >
        VIX {d.close.toFixed(2)}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: s.color, fontWeight: 'bold' }}>{s.label}</div>
    </div>
  );
};

export const VixSparkline: React.FC<VixSparklineProps> = ({
  data,
  height = 80,
  showAxes = false,
}) => {
  const max = Math.max(...data.map((d) => d.close));
  const min = Math.min(...data.map((d) => d.close));
  const latest = data[data.length - 1];
  const s = latest ? vixSentiment(latest.close) : { color: 'var(--color-brass)' };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="vixGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={s.color} stopOpacity={0.15} />
            <stop offset="95%" stopColor={s.color} stopOpacity={0} />
          </linearGradient>
        </defs>
        {showAxes && (
          <XAxis
            dataKey="date"
            tickFormatter={(v) => format(parseISO(v), 'dd')}
            tick={{ fill: 'var(--color-ink-soft)', fontSize: 9, fontFamily: 'var(--font-precision)' }}
            axisLine={{ stroke: 'var(--color-rule)' }}
            tickLine={false}
          />
        )}
        {showAxes && (
          <YAxis
            domain={[Math.floor(min) - 2, Math.ceil(max) + 2]}
            tick={{ fill: 'var(--color-ink-soft)', fontSize: 9, fontFamily: 'var(--font-precision)' }}
            axisLine={{ stroke: 'var(--color-rule)' }}
            tickLine={false}
            width={28}
          />
        )}
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={20} stroke="var(--color-brass)" strokeDasharray="2 2" strokeWidth={1} />
        <ReferenceLine y={30} stroke="var(--color-ledger-red)" strokeDasharray="2 2" strokeWidth={1} />
        <Area
          type="monotone"
          dataKey="close"
          stroke={s.color}
          strokeWidth={1.5}
          fill="url(#vixGradient)"
          dot={false}
          activeDot={{ r: 3, fill: 'var(--color-brass-bright)', stroke: 'var(--color-paper-raised)', strokeWidth: 1.5 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
};

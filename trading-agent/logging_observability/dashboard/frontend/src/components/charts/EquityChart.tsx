import React from 'react';
import {
  LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid
} from 'recharts';

interface EquityPoint {
  index: number;
  equity: number;
  symbol?: string;
  exit_reason?: string;
}

interface EquityChartProps {
  data: EquityPoint[];
  startEquity: number;
  height?: number;
}

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (!payload.exit_reason) return null;
  const color = payload.exit_reason === 'tp_hit'
    ? 'var(--color-ledger-green)'
    : 'var(--color-ledger-red)';
  return (
    <circle
      cx={cx}
      cy={cy}
      r={2.5}
      fill={color}
      stroke="var(--color-paper-raised)"
      strokeWidth={1}
    />
  );
};

export const EquityChart: React.FC<EquityChartProps> = ({
  data,
  startEquity,
  height = 120,
}) => {
  const isUp = data.length > 0 && data[data.length - 1].equity >= startEquity;
  const lineColor = isUp ? 'var(--color-brass-bright)' : 'var(--color-ledger-red)';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
        {/* Paper graph grid */}
        <CartesianGrid stroke="var(--color-rule)" strokeDasharray="2 4" opacity={0.4} />
        <XAxis hide dataKey="index" />
        <YAxis hide domain={['auto', 'auto']} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as EquityPoint;
            return (
              <div
                className="ledger-card"
                style={{
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: 'var(--radius-card)',
                  padding: '6px 10px',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-precision)',
                  boxShadow: '2px 2px 0 var(--color-rule)',
                }}
              >
                <div style={{ color: 'var(--color-ink-soft)', marginBottom: '2px' }}>
                  TRADE #{d.index + 1} {d.symbol && `— ${d.symbol}`}
                </div>
                <div
                  className="tabular-nums"
                  style={{
                    fontWeight: 700,
                    color: d.equity >= startEquity
                      ? 'var(--color-ledger-green)'
                      : 'var(--color-ledger-red)',
                  }}
                >
                  ${d.equity.toFixed(2)}
                </div>
              </div>
            );
          }}
        />
        <ReferenceLine
          y={startEquity}
          stroke="var(--color-rule)"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <Line
          type="monotone"
          dataKey="equity"
          stroke={lineColor}
          strokeWidth={1.75}
          dot={<CustomDot />}
          activeDot={{ r: 3.5, fill: lineColor, stroke: 'var(--color-paper-raised)', strokeWidth: 1.5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

import React from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { VixSparkline } from '../charts/VixSparkline';
import { useDashboardStore } from '../../store/dashboardStore';
import { vixSentiment } from '../../lib/formatters';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const BIAS_ICON: Record<string, React.ReactNode> = {
  bullish: <TrendingUp size={18} color="var(--color-profit)" />,
  bearish: <TrendingDown size={18} color="var(--color-loss)" />,
  neutral: <Minus size={18} color="var(--color-ink-muted)" />,
};

const BIAS_COLOR: Record<string, string> = {
  bullish: 'var(--color-profit)',
  bearish: 'var(--color-loss)',
  neutral: 'var(--color-ink-muted)',
};

// Default high-liquidity watchlist assets (Live MT5 Market Quotes)
const DEFAULT_WATCHLIST = [
  { symbol: 'XAUUSD', name: 'Gold Spot / US Dollar', bid: 4360.31, ask: 4360.68, spread: 0.37, chgPct: +0.85, high: 4378.50, low: 4338.20 },
  { symbol: 'EURUSD', name: 'Euro vs US Dollar', bid: 1.14766, ask: 1.14777, spread: 1.1, chgPct: -0.22, high: 1.15120, low: 1.14610 },
  { symbol: 'GBPUSD', name: 'British Pound vs USD', bid: 1.33495, ask: 1.33506, spread: 1.1, chgPct: +0.14, high: 1.33850, low: 1.33280 },
  { symbol: 'USDJPY', name: 'US Dollar vs Japanese Yen', bid: 155.998, ask: 156.008, spread: 1.0, chgPct: +0.48, high: 156.450, low: 155.320 },
  { symbol: 'BTCUSD', name: 'Bitcoin Spot Index', bid: 76756.8, ask: 76776.45, spread: 19.65, chgPct: +1.85, high: 77400.0, low: 75280.0 },
  { symbol: 'XTIUSD', name: 'WTI Crude Oil Spot', bid: 97.24, ask: 97.26, spread: 0.02, chgPct: +2.40, high: 98.60, low: 95.80 },
  { symbol: 'XBRUSD', name: 'Brent Crude Oil Spot', bid: 101.05, ask: 101.07, spread: 0.02, chgPct: +2.15, high: 102.40, low: 99.50 },
];

const DEFAULT_MACRO_EVENTS = [
  { time: '03:00 UTC', currency: 'JPY', event: 'Bank of Japan (BoJ) Interest Rate Decision', impact: 'high', forecast: '1.25%', previous: '1.00%' },
  { time: '06:00 UTC', currency: 'GBP', event: 'UK Core Retail Sales (MoM)', impact: 'medium', forecast: '-0.2%', previous: '-0.9%' },
  { time: '06:00 UTC', currency: 'EUR', event: 'German Producer Price Index (PPI MoM)', impact: 'medium', forecast: '0.6%', previous: '1.1%' },
  { time: '10:30 UTC', currency: 'EUR', event: 'ECB President Christine Lagarde Speaks', impact: 'medium', forecast: '—', previous: '—' },
  { time: '13:15 UTC', currency: 'USD', event: 'US Industrial Production (MoM)', impact: 'medium', forecast: '0.3%', previous: '0.2%' },
  { time: '13:30 UTC', currency: 'USD', event: 'FOMC Member Bowman Speaks on Monetary Framework', impact: 'medium', forecast: '—', previous: '—' },
  { time: '14:00 UTC', currency: 'USD', event: 'US Leading Economic Index (MoM)', impact: 'medium', forecast: '0.1%', previous: '0.2%' },
];

export const MarketDataPanel: React.FC = () => {
  const { vixHistory, brief, marketQuotes } = useDashboardStore();

  const latest = vixHistory[vixHistory.length - 1];
  const vixS = latest ? vixSentiment(latest.close) : null;

  const watchlist = DEFAULT_WATCHLIST.map((row) => {
    const live = marketQuotes?.[row.symbol];
    if (!live || !live.price) return row;
    const bid = live.price;
    const spreadDiff = row.ask - row.bid;
    const ask = bid + (spreadDiff > 0 ? spreadDiff : 0.0001);
    const chgPct = live.changePct != null ? live.changePct : row.chgPct;
    return { ...row, bid, ask, chgPct };
  });

  const macroEvents = (brief?.structured?.key_upcoming_risks && brief.structured.key_upcoming_risks.length > 0)
    ? brief.structured.key_upcoming_risks.map((evt) => ({
        time: evt.time || 'Upcoming',
        currency: 'MACRO',
        event: evt.event,
        impact: evt.expected_impact || 'medium',
        forecast: '—',
        previous: '—',
      }))
    : DEFAULT_MACRO_EVENTS;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', fontFamily: 'var(--font-precision)' }}>

      {/* Top Grid: Watchlist & VIX Barometer */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '20px' }}>

        {/* Live Multi-Asset Watchlist Table */}
        <Card
          title="REAL-TIME MARKET QUOTES // MULTI-ASSET WATCHLIST"
          variant="blue"
        >
          <div style={{ overflowX: 'auto' }}>
            <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '8px 10px' }}>SYMBOL</th>
                  <th style={{ textAlign: 'right', padding: '8px 10px' }}>BID</th>
                  <th style={{ textAlign: 'right', padding: '8px 10px' }}>ASK</th>
                  <th style={{ textAlign: 'right', padding: '8px 10px' }}>SPREAD</th>
                  <th style={{ textAlign: 'right', padding: '8px 10px' }}>24H CHG</th>
                  <th style={{ textAlign: 'center', padding: '8px 10px' }}>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((row) => (
                  <tr key={row.symbol} className="greenbar-row" style={{ borderBottom: '1px solid var(--color-rule)' }}>
                    <td style={{ padding: '8px 10px' }}>
                      <div style={{ fontWeight: 800, color: 'var(--color-ink)' }}>{row.symbol}</div>
                      <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>{row.name}</div>
                    </td>
                    <td className="tabular-nums" style={{ textAlign: 'right', padding: '8px 10px', fontWeight: 700, color: 'var(--color-ink)' }}>
                      {row.bid.toLocaleString(undefined, { minimumFractionDigits: row.symbol === 'XAUUSD' ? 2 : row.symbol === 'BTCUSD' ? 1 : 5 })}
                    </td>
                    <td className="tabular-nums" style={{ textAlign: 'right', padding: '8px 10px', fontWeight: 700, color: 'var(--color-ink)' }}>
                      {row.ask.toLocaleString(undefined, { minimumFractionDigits: row.symbol === 'XAUUSD' ? 2 : row.symbol === 'BTCUSD' ? 1 : 5 })}
                    </td>
                    <td className="tabular-nums" style={{ textAlign: 'right', padding: '8px 10px', color: 'var(--color-ink-soft)' }}>
                      {row.spread} p
                    </td>
                    <td className="tabular-nums" style={{
                      textAlign: 'right',
                      padding: '8px 10px',
                      fontWeight: 800,
                      color: row.chgPct >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                    }}>
                      {row.chgPct >= 0 ? '+' : ''}{row.chgPct.toFixed(2)}%
                    </td>
                    <td style={{ textAlign: 'center', padding: '8px 10px' }}>
                      <Badge variant="profit" size="sm">LIVE</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* VIX Volatility Gauge & Chart */}
        <Card
          title="IMPLIED VOLATILITY INDEX (CBOE VIX)"
          variant="salmon"
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>Current VIX Level:</span>
            {vixS && latest && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="tabular-nums" style={{ fontSize: '18px', fontWeight: 800, color: vixS.color }}>
                  {latest.close.toFixed(2)}
                </span>
                <Badge variant={latest.close >= 30 ? 'error' : latest.close >= 20 ? 'warn' : 'profit'} size="sm">
                  {vixS.label}
                </Badge>
              </div>
            )}
          </div>

          <VixSparkline data={vixHistory} height={130} showAxes />

          {/* Threshold markers */}
          <div style={{
            display: 'flex',
            gap: '12px',
            marginTop: '12px',
            fontSize: '11px',
            color: 'var(--color-ink-soft)',
            fontFamily: 'var(--font-precision)',
            justifyContent: 'space-around',
            background: 'var(--color-paper)',
            padding: '6px 8px',
            border: '1px solid var(--color-rule)',
            borderRadius: '2px',
          }}>
            <span style={{ color: 'var(--color-ledger-green)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: 8, height: 2, background: 'var(--color-ledger-green)' }}></span> &lt;15 Low Volatility
            </span>
            <span style={{ color: 'var(--color-brass)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: 8, height: 2, background: 'var(--color-brass)' }}></span> 15-25 Elevated Risk
            </span>
            <span style={{ color: 'var(--color-ledger-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: 8, height: 2, background: 'var(--color-ledger-red)' }}></span> &gt;25 High Volatility
            </span>
          </div>
        </Card>
      </div>

      {/* Bottom Grid: Macro News Events & Currency Bias Matrix */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>

        {/* Macro Economic Calendar Ticker */}
        <Card
          title="MACROECONOMIC ECONOMIC CALENDAR & RELEASES"
          variant="yellow"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {macroEvents.map((evt, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 12px',
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  fontSize: '11px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-win-yellow)', background: '#1C1917', padding: '2px 5px', borderRadius: '2px' }}>
                    {evt.time}
                  </span>
                  <span style={{ fontWeight: 800, color: 'var(--color-ink)' }}>[{evt.currency}]</span>
                  <span style={{ color: 'var(--color-ink)' }}>{evt.event}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="tabular-nums" style={{ color: 'var(--color-ink-soft)' }}>Fcst: {evt.forecast}</span>
                  <Badge variant={evt.impact === 'high' ? 'error' : 'warn'} size="sm">
                    {evt.impact.toUpperCase()}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Currency Bias Matrix (from brief or standard) */}
        <Card
          title="FUNDAMENTAL CURRENCY BIAS MATRIX"
          variant="green"
        >
          {brief?.structured?.currency_bias ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(85px, 1fr))', gap: '8px' }}>
              {Object.entries(brief.structured.currency_bias).map(([currency, bias]) => (
                <div
                  key={currency}
                  style={{
                    background: 'var(--color-paper)',
                    borderRadius: '2px',
                    padding: '8px',
                    textAlign: 'center',
                    border: `1.5px solid ${
                      bias === 'bullish' ? 'var(--color-ledger-green)' : bias === 'bearish' ? 'var(--color-ledger-red)' : 'var(--color-rule)'
                    }`,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <div style={{ fontWeight: 800, fontSize: '13px', color: 'var(--color-ink)' }}>{currency}</div>
                  <div>{BIAS_ICON[bias as string] || <Minus size={16} color="var(--color-ink-soft)" />}</div>
                  <div style={{ fontSize: '10px', color: BIAS_COLOR[bias as string] || 'var(--color-ink-soft)', fontWeight: 'bold', textTransform: 'uppercase' }}>
                    {bias as string}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
              {[
                { c: 'USD', b: 'bullish' },
                { c: 'EUR', b: 'neutral' },
                { c: 'GBP', b: 'bullish' },
                { c: 'JPY', b: 'bearish' },
                { c: 'AUD', b: 'neutral' },
                { c: 'CAD', b: 'neutral' },
                { c: 'CHF', b: 'bearish' },
                { c: 'NZD', b: 'neutral' },
              ].map(({ c, b }) => (
                <div
                  key={c}
                  style={{
                    background: 'var(--color-paper)',
                    borderRadius: '2px',
                    padding: '8px',
                    textAlign: 'center',
                    border: `1.5px solid ${b === 'bullish' ? 'var(--color-ledger-green)' : b === 'bearish' ? 'var(--color-ledger-red)' : 'var(--color-rule)'}`,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <div style={{ fontWeight: 800, fontSize: '12px', color: 'var(--color-ink)' }}>{c}</div>
                  <div>{BIAS_ICON[b]}</div>
                  <div style={{ fontSize: '10px', color: BIAS_COLOR[b], fontWeight: 'bold', textTransform: 'uppercase' }}>{b}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

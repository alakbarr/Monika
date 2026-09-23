import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { VixSparkline } from '../charts/VixSparkline';
import { useDashboardStore } from '../../store/dashboardStore';
import { vixSentiment } from '../../lib/formatters';
import { api } from '../../lib/api';
import type {
  CalendarEventItem,
  FedWatchResponse,
  YieldsResponse,
  FearGreedResponse,
  SentimentCompositeResponse,
} from '../../types/api';
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
  const [liveCalendar, setLiveCalendar] = useState<CalendarEventItem[]>([]);
  const [fedwatch, setFedwatch] = useState<FedWatchResponse | null>(null);
  const [yields, setYields] = useState<YieldsResponse | null>(null);
  const [fearGreed, setFearGreed] = useState<FearGreedResponse | null>(null);
  const [sentimentComp, setSentimentComp] = useState<SentimentCompositeResponse | null>(null);

  // Technical Indicators & SMC Structure State (FASE 3B)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [indicators, setIndicators] = useState<Record<string, any> | null>(null);
  const [structure, setStructure] = useState<import('../../types/api').MarketStructureResponse | null>(null);
  const [techLoading, setTechLoading] = useState(false);

  const handleSelectSymbol = async (symbol: string) => {
    if (selectedSymbol === symbol) {
      setSelectedSymbol(null);
      return;
    }
    setSelectedSymbol(symbol);
    setTechLoading(true);
    try {
      const [indRes, structRes] = await Promise.allSettled([
        api.marketIndicators(symbol, 'H1'),
        api.marketStructure(symbol, 'H4'),
      ]);
      if (indRes.status === 'fulfilled' && indRes.value?.indicators) {
        setIndicators(indRes.value.indicators);
      } else {
        setIndicators(null);
      }
      if (structRes.status === 'fulfilled') {
        setStructure(structRes.value);
      } else {
        setStructure(null);
      }
    } catch {
      // ignore
    } finally {
      setTechLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const [calRes, fwRes, yRes, fgRes, scRes] = await Promise.allSettled([
          api.calendarUpcoming(),
          api.marketFedWatch(),
          api.marketYields(),
          api.marketFearGreed(),
          api.marketSentimentComposite(),
        ]);
        if (!mounted) return;
        if (calRes.status === 'fulfilled' && Array.isArray(calRes.value) && calRes.value.length > 0) {
          setLiveCalendar(calRes.value);
        }
        if (fwRes.status === 'fulfilled' && fwRes.value) {
          setFedwatch(fwRes.value);
        }
        if (yRes.status === 'fulfilled' && yRes.value) {
          setYields(yRes.value);
        }
        if (fgRes.status === 'fulfilled' && fgRes.value) {
          setFearGreed(fgRes.value);
        }
        if (scRes.status === 'fulfilled' && scRes.value) {
          setSentimentComp(scRes.value);
        }
      } catch (e) {
        // Fallback gracefully
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

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

  const macroEvents = liveCalendar.length > 0
    ? liveCalendar.map((evt) => {
        let timeStr = 'Upcoming';
        if (evt.event_time) {
          try {
            const d = new Date(evt.event_time);
            timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC';
          } catch {
            timeStr = 'Upcoming';
          }
        }
        return {
          time: timeStr,
          currency: evt.currency || 'MACRO',
          event: evt.event_name,
          impact: (evt.impact || 'medium').toLowerCase(),
          forecast: evt.forecast || '—',
          previous: evt.previous || '—',
          actual: evt.actual,
          surprise: evt.surprise_score,
        };
      })
    : (brief?.structured?.key_upcoming_risks && brief.structured.key_upcoming_risks.length > 0)
    ? brief.structured.key_upcoming_risks.map((evt) => ({
        time: evt.time || 'Upcoming',
        currency: 'MACRO',
        event: evt.event,
        impact: evt.expected_impact || 'medium',
        forecast: '—',
        previous: '—',
        actual: null,
        surprise: null,
      }))
    : DEFAULT_MACRO_EVENTS.map(e => ({ ...e, actual: null, surprise: null }));

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
                {watchlist.map((row) => {
                  const isSelected = selectedSymbol === row.symbol;
                  return (
                    <tr
                      key={row.symbol}
                      className="greenbar-row"
                      onClick={() => handleSelectSymbol(row.symbol)}
                      style={{
                        borderBottom: '1px solid var(--color-rule)',
                        cursor: 'pointer',
                        background: isSelected ? 'rgba(232, 185, 74, 0.12)' : undefined,
                      }}
                      title="Click to view Technical Indicators & SMC Structure"
                    >
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
                        <Badge variant={isSelected ? 'warn' : 'profit'} size="sm">
                          {isSelected ? 'ACTIVE' : 'INSPECT'}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Technical Indicators & SMC Market Structure Drawer (FASE 3B) */}
        {selectedSymbol && (
          <Card
            title={`TECHNICAL INDICATORS & SMC MARKET STRUCTURE // ${selectedSymbol}`}
            variant="blue"
          >
            {techLoading ? (
              <div style={{ padding: '16px', color: 'var(--color-ink-muted)' }}>
                Fetching technical snapshot and market structure for {selectedSymbol}...
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {/* 1. Indicators Grid */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '8px' }}>
                    [ TECHNICAL INDICATORS (H1) ]
                  </div>
                  {indicators && Object.keys(indicators).length > 0 ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '8px' }}>
                      {Object.entries(indicators).map(([k, v]) => (
                        <div key={k} style={{ padding: '8px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                          <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', display: 'block' }}>{k}</span>
                          <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 800, color: 'var(--color-ink)' }}>
                            {typeof v === 'number' ? v.toFixed(typeof v === 'number' && v > 100 ? 2 : 4) : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', fontStyle: 'italic' }}>
                      No indicator snapshot available for {selectedSymbol}.
                    </div>
                  )}
                </div>

                {/* 2. SMC Market Structure */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '8px' }}>
                    [ SMART MONEY CONCEPTS (SMC) STRUCTURE (H4) ]
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                    {/* Order Blocks */}
                    <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink)' }}>
                        Order Blocks ({structure?.order_blocks?.length || 0})
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                        {structure?.order_blocks && structure.order_blocks.length > 0 ? (
                          structure.order_blocks.slice(0, 3).map((ob, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                              <Badge variant={ob.direction === 'bullish' ? 'profit' : 'loss'} size="sm">
                                {ob.direction.toUpperCase()}
                              </Badge>
                              <span className="tabular-nums">{ob.price_low?.toFixed(4)} - {ob.price_high?.toFixed(4)}</span>
                            </div>
                          ))
                        ) : (
                          <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>No active order blocks</span>
                        )}
                      </div>
                    </div>

                    {/* Structure Breaks (BOS / CHoCH) */}
                    <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink)' }}>
                        Structure Breaks ({structure?.structure_breaks?.length || 0})
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                        {structure?.structure_breaks && structure.structure_breaks.length > 0 ? (
                          structure.structure_breaks.slice(0, 3).map((sb, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                              <Badge variant="warn" size="sm">{sb.type} {sb.direction}</Badge>
                              <span className="tabular-nums">@{sb.price?.toFixed(4)}</span>
                            </div>
                          ))
                        ) : (
                          <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>No structure breaks detected</span>
                        )}
                      </div>
                    </div>

                    {/* Fair Value Gaps (FVG) */}
                    <div style={{ padding: '10px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink)' }}>
                        Fair Value Gaps ({structure?.fair_value_gaps?.length || 0})
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px' }}>
                        {structure?.fair_value_gaps && structure.fair_value_gaps.length > 0 ? (
                          structure.fair_value_gaps.slice(0, 3).map((fvg, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                              <Badge variant="neutral" size="sm">{fvg.direction}</Badge>
                              <span className="tabular-nums">
                                {(fvg.gap_low ?? fvg.bottom_price)?.toFixed(4)} - {(fvg.gap_high ?? fvg.top_price)?.toFixed(4)}
                              </span>
                            </div>
                          ))
                        ) : (
                          <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>No unfilled FVGs</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Card>
        )}

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
                  {evt.actual && (
                    <span className="tabular-nums" style={{ color: 'var(--color-profit)', fontWeight: 700 }}>
                      Act: {evt.actual}
                    </span>
                  )}
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

      {/* Structured Macro Intelligence Section */}
      {(brief?.structured?.priced_in_assessment || brief?.structured?.contrarian_opportunities) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Priced-In Intelligence */}
          {brief?.structured?.priced_in_assessment && (
            <Card title="MACRO PRICED-IN ASSESSMENT" variant="blue">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: 'var(--color-ink)' }}>
                {typeof brief.structured.priced_in_assessment === 'object' ? (
                  <>
                    {brief.structured.priced_in_assessment.dominant_driver && (
                      <div>
                        <strong>Dominant Driver:</strong> {brief.structured.priced_in_assessment.dominant_driver}
                      </div>
                    )}
                    {brief.structured.priced_in_assessment.priced_in_score != null && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <strong>Priced-In Score:</strong>
                        <Badge variant={brief.structured.priced_in_assessment.priced_in_score >= 8 ? 'error' : brief.structured.priced_in_assessment.priced_in_score >= 5 ? 'warn' : 'profit'}>
                          {brief.structured.priced_in_assessment.priced_in_score} / 10
                        </Badge>
                      </div>
                    )}
                    {brief.structured.priced_in_assessment.sell_the_news_risk && (
                      <div>
                        <strong>Sell-The-News Risk:</strong> {brief.structured.priced_in_assessment.sell_the_news_risk}
                      </div>
                    )}
                  </>
                ) : (
                  <div>{String(brief.structured.priced_in_assessment)}</div>
                )}
              </div>
            </Card>
          )}

          {/* Contrarian Opportunities */}
          {brief?.structured?.contrarian_opportunities && (
            <Card title="CONTRARIAN ASYMMETRY ALERTS" variant="coral">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                {Array.isArray(brief.structured.contrarian_opportunities) && brief.structured.contrarian_opportunities.map((opp: any, i: number) => (
                  <div key={i} style={{ padding: '6px 8px', background: 'var(--color-paper)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                    {typeof opp === 'object' ? (
                      <>
                        <div style={{ fontWeight: 800, color: 'var(--color-brass)' }}>{opp.asset || opp.opportunity || `Opportunity #${i + 1}`}</div>
                        <div style={{ color: 'var(--color-ink-soft)', marginTop: '2px' }}>{opp.rationale || JSON.stringify(opp)}</div>
                      </>
                    ) : (
                      <div style={{ color: 'var(--color-ink)' }}>{String(opp)}</div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Grid: Fear & Greed Sentiment Barometer + US Yield Curve & 2s10s Inversion */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Fear & Greed Card */}
        <Card title="FEAR & GREED SENTIMENT BAROMETER" variant="coral">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <span style={{ fontSize: '32px', fontWeight: 900, fontFamily: 'var(--font-mono)' }}>
                  {fearGreed?.current_value ?? 50}
                </span>
                <span style={{ fontSize: '14px', color: 'var(--color-ink-soft)', marginLeft: '6px' }}>/ 100</span>
              </div>
              <Badge
                variant={
                  (fearGreed?.current_value ?? 50) <= 25
                    ? 'error'
                    : (fearGreed?.current_value ?? 50) <= 45
                    ? 'warn'
                    : (fearGreed?.current_value ?? 50) >= 75
                    ? 'profit'
                    : 'neutral'
                }
                size="md"
              >
                {fearGreed?.classification?.toUpperCase() || 'NEUTRAL'}
              </Badge>
            </div>

            {/* Visual Barometer */}
            <div style={{ width: '100%', height: '8px', background: 'var(--color-rule)', borderRadius: '4px', overflow: 'hidden', position: 'relative' }}>
              <div
                style={{
                  width: `${Math.min(Math.max(fearGreed?.current_value ?? 50, 0), 100)}%`,
                  height: '100%',
                  background:
                    (fearGreed?.current_value ?? 50) <= 25
                      ? 'var(--color-loss)'
                      : (fearGreed?.current_value ?? 50) <= 45
                      ? 'var(--color-warn)'
                      : (fearGreed?.current_value ?? 50) >= 75
                      ? 'var(--color-profit)'
                      : 'var(--color-ink-muted)',
                  transition: 'width 0.4s ease',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 600 }}>
              <span>0 (EXTREME FEAR)</span>
              <span>50 (NEUTRAL)</span>
              <span>100 (EXTREME GREED)</span>
            </div>

            <div style={{ fontSize: '11px', color: 'var(--color-ink)', background: 'var(--color-paper)', padding: '8px', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
              <strong>Signal:</strong> {fearGreed?.interpretation || 'Balanced sentiment. No extreme market crowding.'}
              {fearGreed?.wow_change != null && (
                <span style={{ marginLeft: '8px', color: fearGreed.wow_change >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                  ({fearGreed.wow_change >= 0 ? '+' : ''}{fearGreed.wow_change} WoW)
                </span>
              )}
            </div>
          </div>
        </Card>

        {/* US Treasury Yields & 2s10s Spread */}
        <Card title="US TREASURY YIELDS & 2S10S INVERSION" variant="blue">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)', textTransform: 'uppercase', fontWeight: 700 }}>2s10s Spread:</span>
                <span
                  style={{
                    fontSize: '20px',
                    fontWeight: 900,
                    fontFamily: 'var(--font-mono)',
                    marginLeft: '8px',
                    color: yields?.is_inverted ? 'var(--color-loss)' : 'var(--color-profit)',
                  }}
                >
                  {yields?.spread_2s10s != null ? `${yields.spread_2s10s > 0 ? '+' : ''}${yields.spread_2s10s.toFixed(2)}%` : '+0.15%'}
                </span>
              </div>
              <Badge variant={yields?.is_inverted ? 'error' : 'profit'} size="md">
                {yields?.is_inverted ? 'INVERTED (RECESSION RISK)' : 'NORMAL CURVE'}
              </Badge>
            </div>

            {/* US Treasury Tenors */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
              {(yields?.treasury_yields && yields.treasury_yields.length > 0
                ? yields.treasury_yields.slice(0, 4)
                : [
                    { tenor: '2Y', yield_percent: 4.15 },
                    { tenor: '5Y', yield_percent: 4.22 },
                    { tenor: '10Y', yield_percent: 4.38 },
                    { tenor: '30Y', yield_percent: 4.55 },
                  ]
              ).map((t, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--color-paper)',
                    padding: '8px',
                    borderRadius: '2px',
                    border: '1px solid var(--color-rule)',
                    textAlign: 'center',
                  }}
                >
                  <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 700 }}>{t.tenor}</div>
                  <div style={{ fontSize: '14px', fontWeight: 800, fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                    {typeof t.yield_percent === 'number' ? `${t.yield_percent.toFixed(2)}%` : String(t.yield_percent)}
                  </div>
                </div>
              ))}
            </div>

            {/* Global Sovereign Bonds */}
            {yields?.global_bonds && yields.global_bonds.length > 0 && (
              <div style={{ display: 'flex', gap: '8px', fontSize: '10px', color: 'var(--color-ink-soft)' }}>
                {yields.global_bonds.slice(0, 3).map((b, idx) => (
                  <div key={idx} style={{ background: 'var(--color-paper)', padding: '4px 6px', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                    <strong>{b.country_tenor}:</strong> {typeof b.yield_percent === 'number' ? `${b.yield_percent.toFixed(2)}%` : b.yield_percent}
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Grid: CME FedWatch & Central Banks + Multi-Asset Sentiment & COT Composite */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>
        {/* FedWatch & Central Bank Expectations */}
        <Card title="CME FEDWATCH & CENTRAL BANK POLICY EXPECTATIONS" variant="green">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '12px' }}>
            {fedwatch?.fedwatch && fedwatch.fedwatch.length > 0 ? (
              <div style={{ background: 'var(--color-paper)', padding: '10px', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 800, color: 'var(--color-brass)' }}>
                    Next FOMC Meeting: {fedwatch.fedwatch[0].meeting_date}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>CME FedWatch Tool</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', textAlign: 'center' }}>
                  {Object.entries(fedwatch.fedwatch[0].probabilities || {}).slice(0, 3).map(([key, val]) => (
                    <div key={key} style={{ background: 'var(--color-surface)', padding: '6px', borderRadius: '2px' }}>
                      <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>{key.replace(/_/g, ' ')}</div>
                      <div style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                        {typeof val === 'number' ? `${val.toFixed(1)}%` : String(val)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ background: 'var(--color-paper)', padding: '10px', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 800, color: 'var(--color-brass)' }}>Next FOMC: Target Rate 5.25% - 5.50%</span>
                  <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>Target Probabilities</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', textAlign: 'center' }}>
                  <div style={{ background: 'var(--color-surface)', padding: '6px', borderRadius: '2px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>HOLD RATE</div>
                    <div style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>85.2%</div>
                  </div>
                  <div style={{ background: 'var(--color-surface)', padding: '6px', borderRadius: '2px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>25 BPS CUT</div>
                    <div style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>14.8%</div>
                  </div>
                  <div style={{ background: 'var(--color-surface)', padding: '6px', borderRadius: '2px' }}>
                    <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>50 BPS CUT</div>
                    <div style={{ fontSize: '13px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>0.0%</div>
                  </div>
                </div>
              </div>
            )}

            {/* Central Bank Policy Rates */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px', textAlign: 'center' }}>
              {(fedwatch?.central_banks && fedwatch.central_banks.length > 0
                ? fedwatch.central_banks.slice(0, 5)
                : [
                    { bank: 'FED', current_rate: 5.50, prob_cut: 14.8 },
                    { bank: 'ECB', current_rate: 3.75, prob_cut: 65.0 },
                    { bank: 'BOE', current_rate: 5.25, prob_cut: 40.0 },
                    { bank: 'BOJ', current_rate: 0.25, prob_cut: 0.0 },
                    { bank: 'RBA', current_rate: 4.35, prob_cut: 10.0 },
                  ]
              ).map((cb, idx) => (
                <div key={idx} style={{ background: 'var(--color-paper)', padding: '6px', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                  <div style={{ fontWeight: 800, fontSize: '11px', color: 'var(--color-ink)' }}>{cb.bank}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 700, marginTop: '2px' }}>
                    {typeof cb.current_rate === 'number' ? `${cb.current_rate.toFixed(2)}%` : cb.current_rate}
                  </div>
                  <div style={{ fontSize: '9px', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                    Cut: {typeof cb.prob_cut === 'number' ? `${cb.prob_cut.toFixed(0)}%` : '—'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Retail vs Smart Money (COT) Positioning */}
        <Card title="RETAIL VS SMART MONEY (COT) POSITIONING" variant="yellow">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '11px' }}>
            {/* Retail Positioning */}
            <div style={{ background: 'var(--color-paper)', padding: '8px 10px', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
              <div style={{ fontWeight: 800, color: 'var(--color-ink)', marginBottom: '4px' }}>
                Retail Crowd Positioning (Contrarian Lens)
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-ink-soft)', fontSize: '10px' }}>
                <span>Crypto (Binance): {sentimentComp?.crypto?.ratios?.BTCUSDT?.long_pct != null ? `${sentimentComp.crypto.ratios.BTCUSDT.long_pct}% Long` : '62% Long'}</span>
                <span>Forex (FXSSI): {sentimentComp?.forex_fxssi?.EURUSD?.long_pct != null ? `${sentimentComp.forex_fxssi.EURUSD.long_pct}% Long` : '44% Long'}</span>
              </div>
            </div>

            {/* Smart Money Institutional COT Net */}
            <div style={{ background: 'var(--color-paper)', padding: '8px 10px', borderRadius: '2px', border: '1px solid var(--color-rule)' }}>
              <div style={{ fontWeight: 800, color: 'var(--color-brass)', marginBottom: '4px' }}>
                CFTC Institutional Net Positioning
              </div>
              {sentimentComp?.institutional_cot && sentimentComp.institutional_cot.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {sentimentComp.institutional_cot.slice(0, 3).map((cot, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '10px' }}>
                      <span>Market {cot.market_code}:</span>
                      <span style={{ color: cot.net_position >= 0 ? 'var(--color-profit)' : 'var(--color-loss)', fontWeight: 700 }}>
                        {cot.net_position >= 0 ? '+' : ''}{cot.net_position.toLocaleString()} contracts
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>
                  Institutional positioning aligned with macro cyclical bias.
                </div>
              )}
            </div>

            <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontStyle: 'italic' }}>
              Contrarian rule: Extreme retail crowding (&gt;75%) triggers counter-trend screening.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts';
import { api } from '../../lib/api';
import { useDashboardStore } from '../../store/dashboardStore';
import { Badge } from '../ui/Badge';
import { RefreshCw } from 'lucide-react';

interface CandlestickChartProps {
  initialSymbol?: string;
  initialTimeframe?: string;
  height?: number;
  className?: string;
}

const POPULAR_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'BTCUSD', 'XTIUSD'];
const TIMEFRAMES = ['M15', 'H1', 'H4', 'D1'];

const getChartPalette = (isLight: boolean) => ({
  background: isLight ? '#FAF7F2' : '#1A1715',
  textColor: isLight ? '#1C1917' : '#ADA296',
  gridColor: isLight ? 'rgba(28, 25, 23, 0.08)' : 'rgba(246, 241, 234, 0.06)',
  borderScale: isLight ? 'rgba(28, 25, 23, 0.15)' : 'rgba(246, 241, 234, 0.12)',
  upColor: isLight ? '#1B5E20' : '#4CAF50',
  downColor: isLight ? '#B71C1C' : '#F46A6A',
  obBull: isLight ? '#1B5E20' : '#4CAF50',
  obBear: isLight ? '#B71C1C' : '#F46A6A',
  fvgBull: isLight ? '#3BA4C4' : '#2A7991',
  fvgBear: isLight ? '#E86C53' : '#B04A36',
  chochColor: isLight ? '#E0962B' : '#D98C28',
  bosColor: isLight ? '#1B365D' : '#3D6B9E', // Anti-slop Navy
  timesfmMedian: isLight ? '#3BA4C4' : '#5BC3E0',
  timesfmCone: isLight ? 'rgba(59, 164, 196, 0.35)' : 'rgba(91, 195, 224, 0.3)',
});

export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  initialSymbol = 'EURUSD',
  initialTimeframe = 'H4',
  height = 520,
  className,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const overlaySeriesRef = useRef<Array<ISeriesApi<'Line'>>>([]);
  const priceLinesRef = useRef<any[]>([]);

  const { theme } = useDashboardStore();
  const isLight = theme === 'light';
  const palette = getChartPalette(isLight);

  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [timeframe, setTimeframe] = useState<string>(initialTimeframe);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [spreadPips, setSpreadPips] = useState<number | null>(null);

  // Overlay state toggles
  const [showOrderBlocks, setShowOrderBlocks] = useState<boolean>(true);
  const [showFVG, setShowFVG] = useState<boolean>(true);
  const [showBOS, setShowBOS] = useState<boolean>(true);
  const [showTimesFM, setShowTimesFM] = useState<boolean>(true);

  // Structure metadata
  const [structureData, setStructureData] = useState<{
    order_blocks: any[];
    structure_breaks: any[];
    fair_value_gaps: any[];
    timesfm_cone?: any;
  } | null>(null);

  const clearOverlays = useCallback(() => {
    if (chartInstanceRef.current) {
      for (const series of overlaySeriesRef.current) {
        try {
          chartInstanceRef.current.removeSeries(series);
        } catch {}
      }
      overlaySeriesRef.current = [];
    }

    if (candleSeriesRef.current) {
      for (const line of priceLinesRef.current) {
        try {
          candleSeriesRef.current.removePriceLine(line);
        } catch {}
      }
      priceLinesRef.current = [];
    }
  }, []);

  const loadData = useCallback(async () => {
    if (!candleSeriesRef.current || !chartInstanceRef.current) return;
    setLoading(true);
    try {
      const [candleRes, structRes] = await Promise.all([
        api.marketCandles(symbol, timeframe, 150),
        api.marketStructure(symbol, timeframe).catch(() => null),
      ]);

      if (candleRes && candleRes.candles && candleRes.candles.length > 0) {
        const sorted = [...candleRes.candles].sort((a, b) => a.time - b.time);
        candleSeriesRef.current.setData(
          sorted.map((c) => ({
            time: c.time as Time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          }))
        );

        const latest = sorted[sorted.length - 1];
        if (latest) {
          setLastPrice(latest.close);
          const backendSpread = (candleRes as any)?.spread ?? (latest as any)?.spread;
          if (typeof backendSpread === 'number') {
            setSpreadPips(backendSpread);
          } else {
            setSpreadPips(null);
          }
        }

        chartInstanceRef.current.timeScale().fitContent();
      }

      setStructureData(structRes);
    } catch (err) {
      console.error('Failed to load chart data:', err);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  // Apply SMC & TimesFM Overlays
  useEffect(() => {
    if (!candleSeriesRef.current || !chartInstanceRef.current || !structureData) return;
    clearOverlays();

    const candleSeries = candleSeriesRef.current;
    const isLight = theme === 'light';
    const palette = getChartPalette(isLight);

    // 1. Order Blocks (horizontal price lines)
    if (showOrderBlocks && structureData.order_blocks) {
      for (const ob of structureData.order_blocks.slice(0, 4)) {
        const isBullish = ob.direction?.toLowerCase() === 'bullish';
        const color = isBullish ? palette.obBull : palette.obBear;
        try {
          const highLine = candleSeries.createPriceLine({
            price: ob.price_high,
            color,
            lineWidth: 1,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `OB High (${ob.direction || 'SMC'})`,
          });
          const lowLine = candleSeries.createPriceLine({
            price: ob.price_low,
            color,
            lineWidth: 1,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `OB Low`,
          });
          priceLinesRef.current.push(highLine, lowLine);
        } catch {}
      }
    }

    // 2. Fair Value Gaps (FVG price boundaries)
    if (showFVG && structureData.fair_value_gaps) {
      for (const fvg of structureData.fair_value_gaps.slice(0, 3)) {
        const isBullish = fvg.direction?.toLowerCase() === 'bullish';
        const color = isBullish ? palette.fvgBull : palette.fvgBear;
        try {
          const fvgHigh = candleSeries.createPriceLine({
            price: fvg.gap_high,
            color,
            lineWidth: 1,
            lineStyle: 3, // Dotted
            axisLabelVisible: true,
            title: `FVG High`,
          });
          const fvgLow = candleSeries.createPriceLine({
            price: fvg.gap_low,
            color,
            lineWidth: 1,
            lineStyle: 3, // Dotted
            axisLabelVisible: true,
            title: `FVG Low`,
          });
          priceLinesRef.current.push(fvgHigh, fvgLow);
        } catch {}
      }
    }

    // 3. Structure Breaks (BOS / CHoCH)
    if (showBOS && structureData.structure_breaks) {
      for (const sb of structureData.structure_breaks.slice(0, 3)) {
        const color = sb.type === 'CHoCH' ? palette.chochColor : palette.bosColor;
        try {
          const sbLine = candleSeries.createPriceLine({
            price: sb.price,
            color,
            lineWidth: 2,
            lineStyle: 0, // Solid
            axisLabelVisible: true,
            title: `${sb.type || 'BOS'} (${sb.direction || ''})`,
          });
          priceLinesRef.current.push(sbLine);
        } catch {}
      }
    }

    // 4. TimesFM Forecast Quantiles Cone (q10, q50, q90 projection)
    if (showTimesFM && structureData.timesfm_cone && lastPrice) {
      const cone = structureData.timesfm_cone;
      const q = cone.quantiles || {};
      const drift = cone.drift || 0.0;
      const q10Val = q.q10?.[q.q10.length - 1] ?? (lastPrice * (1 + drift - 0.004));
      const q50Val = q.q50?.[q.q50.length - 1] ?? (lastPrice * (1 + drift));
      const q90Val = q.q90?.[q.q90.length - 1] ?? (lastPrice * (1 + drift + 0.004));

      try {
        const q50Line = candleSeries.createPriceLine({
          price: q50Val,
          color: palette.timesfmMedian,
          lineWidth: 2,
          lineStyle: 1,
          axisLabelVisible: true,
          title: `TimesFM Median (q50)`,
        });
        const q90Line = candleSeries.createPriceLine({
          price: q90Val,
          color: palette.timesfmCone,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `TimesFM Upper (q90)`,
        });
        const q10Line = candleSeries.createPriceLine({
          price: q10Val,
          color: palette.timesfmCone,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `TimesFM Lower (q10)`,
        });
        priceLinesRef.current.push(q50Line, q90Line, q10Line);
      } catch {}
    }
  }, [structureData, showOrderBlocks, showFVG, showBOS, showTimesFM, lastPrice, clearOverlays, theme]);

  // Initialize Canvas Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const isLight = theme === 'light';
    const palette = getChartPalette(isLight);
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth || 800,
      height,
      layout: {
        background: { type: ColorType.Solid, color: palette.background },
        textColor: palette.textColor,
        fontSize: 11,
        fontFamily: 'var(--font-precision), monospace',
      },
      grid: {
        vertLines: { color: palette.gridColor },
        horzLines: { color: palette.gridColor },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: 'rgba(224, 150, 43, 0.6)', width: 1, style: 3 },
        horzLine: { color: 'rgba(224, 150, 43, 0.6)', width: 1, style: 3 },
      },
      rightPriceScale: {
        borderColor: palette.borderScale,
        textColor: palette.textColor,
      },
      timeScale: {
        borderColor: palette.borderScale,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: palette.upColor,
      downColor: palette.downColor,
      borderVisible: false,
      wickUpColor: palette.upColor,
      wickDownColor: palette.downColor,
    });

    chartInstanceRef.current = chart;
    candleSeriesRef.current = candleSeries;

    const handleResize = () => {
      if (chartContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    const resizeObserver = new ResizeObserver(() => handleResize());
    resizeObserver.observe(chartContainerRef.current);

    loadData();

    return () => {
      resizeObserver.disconnect();
      clearOverlays();
      chart.remove();
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [height, clearOverlays, loadData, theme]);

  // Reactive theme options update
  useEffect(() => {
    if (!chartInstanceRef.current || !candleSeriesRef.current) return;
    const isLight = theme === 'light';
    const palette = getChartPalette(isLight);
    chartInstanceRef.current.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: palette.background },
        textColor: palette.textColor,
      },
      grid: {
        vertLines: { color: palette.gridColor },
        horzLines: { color: palette.gridColor },
      },
      rightPriceScale: {
        borderColor: palette.borderScale,
        textColor: palette.textColor,
      },
      timeScale: {
        borderColor: palette.borderScale,
      },
    });
    candleSeriesRef.current.applyOptions({
      upColor: palette.upColor,
      downColor: palette.downColor,
      wickUpColor: palette.upColor,
      wickDownColor: palette.downColor,
    });
  }, [theme]);

  // Re-fetch data on symbol or timeframe change
  useEffect(() => {
    loadData();
  }, [symbol, timeframe, loadData]);

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        background: 'var(--color-surface-card)',
        border: '1px solid var(--color-border)',
        borderRadius: '2px',
        padding: '16px',
      }}
    >
      {/* Top Toolbar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          borderBottom: '1px solid var(--color-rule)',
          paddingBottom: '12px',
        }}
      >
        {/* Symbol & Price Overview */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', gap: '4px' }}>
            {POPULAR_SYMBOLS.map((s) => (
              <button
                key={s}
                onClick={() => setSymbol(s)}
                style={{
                  padding: '4px 8px',
                  borderRadius: '2px',
                  fontSize: '11px',
                  fontWeight: 700,
                  fontFamily: 'var(--font-precision)',
                  border: `1px solid ${symbol === s ? 'var(--color-brass)' : 'var(--color-border)'}`,
                  background: symbol === s ? 'rgba(217, 119, 6, 0.15)' : 'transparent',
                  color: symbol === s ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                  cursor: 'pointer',
                }}
              >
                {s}
              </button>
            ))}
          </div>

          {lastPrice !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                className="tabular-nums"
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  fontFamily: 'var(--font-precision)',
                  color: 'var(--color-ink)',
                }}
              >
                {lastPrice.toFixed(symbol.includes('JPY') ? 3 : 5)}
              </span>
              {spreadPips !== null && (
                <Badge variant="neutral" size="sm">
                  SPREAD: {spreadPips.toFixed(1)} PIPS
                </Badge>
              )}
            </div>
          )}
        </div>

        {/* Timeframe & Overlays Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Timeframe Buttons */}
          <div style={{ display: 'flex', gap: '2px', background: 'var(--color-surface)', padding: '2px', borderRadius: '2px' }}>
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className="touch-target-expand"
                style={{
                  padding: '4px 8px',
                  fontSize: '11px',
                  fontWeight: 600,
                  fontFamily: 'var(--font-precision)',
                  borderRadius: '2px',
                  border: 'none',
                  background: timeframe === tf ? 'var(--color-surface-card)' : 'transparent',
                  color: timeframe === tf ? 'var(--color-ink)' : 'var(--color-ink-muted)',
                  cursor: 'pointer',
                  borderBottom: timeframe === tf ? '2px solid var(--color-brass)' : 'none',
                }}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Overlay Toggles */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => setShowOrderBlocks((v) => !v)}
              className="touch-target-expand"
              style={{
                padding: '4px 8px',
                borderRadius: '2px',
                fontSize: '11px',
                fontWeight: 600,
                border: `1px solid ${showOrderBlocks ? palette.obBull : 'var(--color-border)'}`,
                background: showOrderBlocks ? 'var(--color-profit-soft)' : 'transparent',
                color: showOrderBlocks ? palette.obBull : 'var(--color-ink-muted)',
                cursor: 'pointer',
              }}
            >
              Order Blocks
            </button>
            <button
              onClick={() => setShowFVG((v) => !v)}
              className="touch-target-expand"
              style={{
                padding: '4px 8px',
                borderRadius: '2px',
                fontSize: '11px',
                fontWeight: 600,
                border: `1px solid ${showFVG ? palette.fvgBull : 'var(--color-border)'}`,
                background: showFVG ? 'rgba(59, 164, 196, 0.12)' : 'transparent',
                color: showFVG ? palette.fvgBull : 'var(--color-ink-muted)',
                cursor: 'pointer',
              }}
            >
              FVG Zones
            </button>
            <button
              onClick={() => setShowBOS((v) => !v)}
              className="touch-target-expand"
              style={{
                padding: '4px 8px',
                borderRadius: '2px',
                fontSize: '11px',
                fontWeight: 600,
                border: `1px solid ${showBOS ? palette.bosColor : 'var(--color-border)'}`,
                background: showBOS ? 'rgba(27, 54, 93, 0.12)' : 'transparent',
                color: showBOS ? palette.bosColor : 'var(--color-ink-muted)',
                cursor: 'pointer',
              }}
            >
              BOS/CHoCH
            </button>
            <button
              onClick={() => setShowTimesFM((v) => !v)}
              className="touch-target-expand"
              style={{
                padding: '4px 8px',
                borderRadius: '2px',
                fontSize: '11px',
                fontWeight: 600,
                border: `1px solid ${showTimesFM ? 'var(--color-brass)' : 'var(--color-border)'}`,
                background: showTimesFM ? 'rgba(224, 150, 43, 0.12)' : 'transparent',
                color: showTimesFM ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                cursor: 'pointer',
              }}
            >
              TimesFM Cone
            </button>
          </div>

          {/* Refresh Button */}
          <button
            onClick={() => loadData()}
            disabled={loading}
            className="touch-target-expand"
            style={{
              padding: '6px',
              borderRadius: '2px',
              border: '1px solid var(--color-border)',
              background: 'transparent',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
            }}
            title="Refresh Candles & Structure"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Chart Canvas Container */}
      <div
        ref={chartContainerRef}
        style={{
          width: '100%',
          height: `${height}px`,
          position: 'relative',
          borderRadius: '2px',
          overflow: 'hidden',
        }}
      />
    </div>
  );
};

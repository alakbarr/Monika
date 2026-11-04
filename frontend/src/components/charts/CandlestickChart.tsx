// ==============================================================================
// File: src/components/charts/CandlestickChart.tsx
// Description: Swiss Editorial & Liquid Glass v4.0 Multi-Pane Financial Charting
// Workstation with Bidirectional Symbol & Config Sync, Native v5 Multi-Pane
// Rendering, Instant Client-Side Indicator Math, and Zero-Flicker WebSocket Ticks.
// ==============================================================================

import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type MouseEventParams,
} from 'lightweight-charts';
import { api } from '../../lib/api';
import { useDashboardStore } from '../../store/dashboardStore';
import { getChartPalette } from '../../theme/tokens';
import {
  computeClientIndicatorSeries,
  mergeRealtimeTickIntoCandles,
  countActiveIndicators,
  type ClientCandle,
} from '../../lib/chartIndicatorsClientMath';
import { IndicatorStudioPopover } from './IndicatorStudioPopover';
import {
  computeVisibleVolumeProfile,
  POPULAR_SYMBOLS,
  type HudData,
  type HudItem,
} from './candlestick/chartUtils';
import { ChartControlsToolbar } from './candlestick/ChartControlsToolbar';
import { ChartHud } from './candlestick/ChartHud';
import { ChartStatusBar } from './candlestick/ChartStatusBar';
import type {
  ActivePositionOverlay,
  AiProposalOverlay,
  IndicatorSummaryItem,
} from '../../types/api';

interface CandlestickChartProps {
  initialSymbol?: string;
  initialTimeframe?: string;
  height?: number;
  className?: string;
}

export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  initialSymbol = 'EURUSD',
  initialTimeframe = 'H4',
  height = 520,
  className,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const priceLinesRef = useRef<any[]>([]);
  const candlesRef = useRef<ClientCandle[]>([]);

  const { theme } = useDashboardStore();
  const isLight = theme === 'light';
  const palette = useMemo(() => getChartPalette(isLight), [isLight]);

  // Store bindings
  const storeSelectedSymbol = useDashboardStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useDashboardStore((s) => s.setSelectedSymbol);
  const chartConfigs = useDashboardStore((s) => s.chartConfigs);
  const loadChartConfigsFromServer = useDashboardStore((s) => s.loadChartConfigsFromServer);
  const saveChartWorkspaceConfig = useDashboardStore((s) => s.saveChartWorkspaceConfig);
  const applyChartPreset = useDashboardStore((s) => s.applyChartPreset);

  // Local state
  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [isStudioOpen, setIsStudioOpen] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [spreadPips, setSpreadPips] = useState<number | null>(null);

  // Chart data state
  const [candles, setCandles] = useState<ClientCandle[]>([]);
  const [structureData, setStructureData] = useState<any>(null);
  const [activePositions, setActivePositions] = useState<ActivePositionOverlay[]>([]);
  const [latestAiProposal, setLatestAiProposal] = useState<AiProposalOverlay | null>(null);
  const [_serverIndicatorSummary, setServerIndicatorSummary] = useState<IndicatorSummaryItem[]>([]);
  const [source, setSource] = useState<string>('mt5');
  const [hoveredHud, setHoveredHud] = useState<HudData | null>(null);

  // WebSocket tick feed
  const lastTick = useDashboardStore((s) => s.lastTickBySymbol[symbol]);

  // Load server configs once on mount
  useEffect(() => {
    loadChartConfigsFromServer();
  }, [loadChartConfigsFromServer]);

  // 1. Bidirectional Symbol Synchronization
  useEffect(() => {
    if (initialSymbol && initialSymbol !== symbol) {
      setSymbol(initialSymbol);
    }
  }, [initialSymbol, symbol]);

  useEffect(() => {
    if (storeSelectedSymbol && storeSelectedSymbol !== symbol) {
      setSymbol(storeSelectedSymbol);
    }
  }, [storeSelectedSymbol, symbol]);

  const handleSelectSymbol = useCallback((s: string) => {
    setSymbol(s);
    setSelectedSymbol(s);
  }, [setSelectedSymbol]);

  // Effective chart configuration
  const { config: activeConfig, isSymbolOverride } = useMemo(() => {
    const symKey = symbol ? symbol.toUpperCase() : '';
    if (symKey && chartConfigs.symbols[symKey]) {
      return { config: chartConfigs.symbols[symKey], isSymbolOverride: true };
    }
    return { config: chartConfigs.global, isSymbolOverride: false };
  }, [chartConfigs, symbol]);

  const isSymbolPinned = isSymbolOverride;
  const timeframe = activeConfig.timeframe || initialTimeframe || 'H4';
  const activeIndicatorsCount = useMemo(() => countActiveIndicators(activeConfig), [activeConfig]);

  // 2. Client-Side Indicator Mathematics (<16ms instant update)
  const clientIndicators = useMemo(() => {
    return computeClientIndicatorSeries(candles, activeConfig);
  }, [candles, activeConfig]);

  // Active Oscillators List (determines sub-panes 1..K)
  const activeOscillatorList = useMemo(() => {
    const list: Array<'volume' | 'rsi' | 'macd' | 'stochastic' | 'adx' | 'atr' | 'cvd'> = [];
    const osc = activeConfig.oscillators;
    if (osc.volume?.enabled) list.push('volume');
    if (osc.rsi?.enabled) list.push('rsi');
    if (osc.macd?.enabled) list.push('macd');
    if (osc.stochastic?.enabled) list.push('stochastic');
    if (osc.adx?.enabled) list.push('adx');
    if (osc.atr?.enabled) list.push('atr');
    if (osc.cvd_volatility?.enabled) list.push('cvd');
    return list;
  }, [activeConfig.oscillators]);

  // Escape key to exit fullscreen
  useEffect(() => {
    if (!isFullscreen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  // Clear previous price lines
  const clearPriceLines = useCallback(() => {
    if (candleSeriesRef.current) {
      for (const pl of priceLinesRef.current) {
        try {
          candleSeriesRef.current.removePriceLine(pl);
        } catch {
          // ignore
        }
      }
    }
    priceLinesRef.current = [];
  }, []);

  // Fetch workspace or fallback candles
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      let fetchedCandles: ClientCandle[] = [];
      let fetchedStructure: any = null;
      let fetchedPositions: ActivePositionOverlay[] = [];
      let fetchedAiProposal: AiProposalOverlay | null = null;
      let fetchedSummary: IndicatorSummaryItem[] = [];
      let detectedSource = 'mt5';

      try {
        const wsRes = await api.marketChartWorkspace(symbol, timeframe, 250);
        if (wsRes && Array.isArray(wsRes.candles) && wsRes.candles.length > 0) {
          fetchedCandles = wsRes.candles;
          fetchedStructure = wsRes.structure || null;
          fetchedPositions = wsRes.positions || [];
          fetchedAiProposal = wsRes.ai_proposals?.[0] || null;
          fetchedSummary = wsRes.summary || [];
          detectedSource = (wsRes as any).source || ((wsRes as any).is_synthetic ? 'synthetic_preview' : 'mt5');
        }
      } catch {
        // Fallback to marketCandles + marketStructure
        const [cRes, sRes] = await Promise.all([
          api.marketCandles(symbol, timeframe, 250),
          api.marketStructure(symbol, timeframe).catch(() => null),
        ]);
        if (cRes && Array.isArray(cRes.candles)) {
          fetchedCandles = cRes.candles;
          detectedSource = (cRes as any).is_synthetic ? 'synthetic_preview' : 'database';
          const backendSpread = (cRes as any)?.spread;
          if (typeof backendSpread === 'number') {
            setSpreadPips(backendSpread);
          }
        }
        fetchedStructure = sRes;
      }

      if (fetchedCandles.length > 0) {
        const sorted = [...fetchedCandles].sort((a, b) => a.time - b.time);
        setCandles(sorted);
        candlesRef.current = sorted;
        const latest = sorted[sorted.length - 1];
        setLastPrice(latest.close);
      } else {
        setCandles([]);
        candlesRef.current = [];
      }

      setStructureData(fetchedStructure);
      setActivePositions(fetchedPositions);
      setLatestAiProposal(fetchedAiProposal);
      setServerIndicatorSummary(fetchedSummary);
      setSource(detectedSource);
    } catch (err) {
      console.error('Failed to load chart data:', err);
      setSource('demo');
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  // Re-fetch data on symbol or timeframe change
  useEffect(() => {
    loadData();
  }, [symbol, timeframe, loadData]);

  // 4. Real-Time WebSocket Tick Updates (60fps Zero-Flicker)
  useEffect(() => {
    if (!lastTick || candlesRef.current.length === 0 || !candleSeriesRef.current) return;
    const tickPrice = typeof lastTick.bid === 'number' && lastTick.bid > 0
      ? lastTick.bid
      : typeof (lastTick as any).price === 'number'
      ? (lastTick as any).price
      : null;
    if (!tickPrice) return;

    const updatedCandles = mergeRealtimeTickIntoCandles(
      candlesRef.current,
      tickPrice,
      lastTick.timestamp,
      timeframe
    );
    candlesRef.current = updatedCandles;
    const lastCandle = updatedCandles[updatedCandles.length - 1];
    candleSeriesRef.current.update({
      time: lastCandle.time as Time,
      open: lastCandle.open,
      high: lastCandle.high,
      low: lastCandle.low,
      close: lastCandle.close,
    });
    setLastPrice(tickPrice);
    if (typeof lastTick.spread === 'number') {
      setSpreadPips(lastTick.spread);
    }
  }, [lastTick, timeframe]);

  // 3. Native Lightweight-Charts v5 Multi-Pane Rendering
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const totalChartHeight = isFullscreen
      ? Math.max(560, window.innerHeight - 190)
      : height + activeOscillatorList.length * 115;

    // Preserve previous visible logical range if chart was already active
    const prevRange = chartInstanceRef.current?.timeScale().getVisibleLogicalRange();

    // Cleanup previous chart instance
    clearPriceLines();
    if (chartInstanceRef.current) {
      try {
        chartInstanceRef.current.remove();
      } catch {
        // ignore
      }
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth || 800,
      height: totalChartHeight,
      layout: {
        background: { type: ColorType.Solid, color: palette.background },
        textColor: palette.textColor,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Fira Code', var(--font-mono), monospace",
        panes: {
          separatorColor: palette.gridColor,
          separatorHoverColor: palette.borderScale,
          enableResize: true,
        },
      },
      grid: {
        vertLines: { color: palette.gridColor },
        horzLines: { color: palette.gridColor },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: palette.borderScale, width: 1, style: 3 },
        horzLine: { color: palette.borderScale, width: 1, style: 3 },
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

    chartInstanceRef.current = chart;

    // --- Pane 0: Candlestick Series ---
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: palette.upColor,
      downColor: palette.downColor,
      borderVisible: false,
      wickUpColor: palette.upColor,
      wickDownColor: palette.downColor,
    }, 0);

    candleSeriesRef.current = candleSeries;

    if (candles.length > 0) {
      candleSeries.setData(
        candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      );
    }

    // --- Pane 0: Overlays ---
    const overlays = activeConfig.overlays;

    // EMA lines
    if (overlays.ema?.enabled && Array.isArray(overlays.ema.periods)) {
      for (const p of overlays.ema.periods) {
        const pts = clientIndicators.series[`ema_${p}`];
        if (pts && pts.length > 0) {
          const color =
            p <= 9
              ? palette.ema9
              : p <= 20
              ? palette.ema20
              : p <= 21
              ? palette.ema21
              : p <= 50
              ? palette.ema50
              : p <= 100
              ? palette.ema100
              : palette.ema200;
          const s = chart.addSeries(LineSeries, { color, lineWidth: 1 }, 0);
          s.setData(pts.map((pt) => ({ time: pt.time as Time, value: pt.value as number })));
        }
      }
    }

    // SMA lines
    if (overlays.sma?.enabled && Array.isArray(overlays.sma.periods)) {
      for (const p of overlays.sma.periods) {
        const pts = clientIndicators.series[`sma_${p}`];
        if (pts && pts.length > 0) {
          const color = p <= 20 ? palette.sma20 : p <= 50 ? palette.sma50 : palette.sma200;
          const s = chart.addSeries(LineSeries, { color, lineWidth: 1 }, 0);
          s.setData(pts.map((pt) => ({ time: pt.time as Time, value: pt.value as number })));
        }
      }
    }

    // WMA lines
    if (overlays.wma?.enabled && Array.isArray(overlays.wma.periods)) {
      for (const p of overlays.wma.periods) {
        const pts = clientIndicators.series[`wma_${p}`];
        if (pts && pts.length > 0) {
          const s = chart.addSeries(LineSeries, { color: palette.wma20, lineWidth: 1 }, 0);
          s.setData(pts.map((pt) => ({ time: pt.time as Time, value: pt.value as number })));
        }
      }
    }

    // Bollinger Bands
    if (overlays.bollinger?.enabled) {
      if (clientIndicators.series['bb_upper']) {
        const up = chart.addSeries(LineSeries, { color: palette.bbUpper, lineWidth: 1 }, 0);
        up.setData(clientIndicators.series['bb_upper'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['bb_mid']) {
        const mid = chart.addSeries(LineSeries, { color: palette.bbMid, lineWidth: 1, lineStyle: 2 }, 0);
        mid.setData(clientIndicators.series['bb_mid'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['bb_lower']) {
        const low = chart.addSeries(LineSeries, { color: palette.bbLower, lineWidth: 1 }, 0);
        low.setData(clientIndicators.series['bb_lower'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
    }

    // Keltner Channels
    if (overlays.keltner?.enabled) {
      if (clientIndicators.series['kc_upper']) {
        const up = chart.addSeries(LineSeries, { color: palette.kcUpper, lineWidth: 1 }, 0);
        up.setData(clientIndicators.series['kc_upper'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['kc_mid']) {
        const mid = chart.addSeries(LineSeries, { color: palette.kcMid, lineWidth: 1, lineStyle: 2 }, 0);
        mid.setData(clientIndicators.series['kc_mid'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['kc_lower']) {
        const low = chart.addSeries(LineSeries, { color: palette.kcLower, lineWidth: 1 }, 0);
        low.setData(clientIndicators.series['kc_lower'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
    }

    // Donchian Channels
    if (overlays.donchian?.enabled) {
      if (clientIndicators.series['dc_upper']) {
        const up = chart.addSeries(LineSeries, { color: palette.dcUpper, lineWidth: 1 }, 0);
        up.setData(clientIndicators.series['dc_upper'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['dc_mid']) {
        const mid = chart.addSeries(LineSeries, { color: palette.dcMid, lineWidth: 1, lineStyle: 2 }, 0);
        mid.setData(clientIndicators.series['dc_mid'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['dc_lower']) {
        const low = chart.addSeries(LineSeries, { color: palette.dcLower, lineWidth: 1 }, 0);
        low.setData(clientIndicators.series['dc_lower'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
    }

    // VWAP
    if (overlays.vwap?.enabled && clientIndicators.series['vwap']) {
      const vwapSeries = chart.addSeries(LineSeries, { color: palette.vwapColor, lineWidth: 2 }, 0);
      vwapSeries.setData(clientIndicators.series['vwap'].map((p) => ({ time: p.time as Time, value: p.value as number })));
    }

    // Supertrend
    if (overlays.supertrend?.enabled && clientIndicators.series['supertrend']) {
      const stSeries = chart.addSeries(LineSeries, { color: palette.supertrendBull, lineWidth: 2 }, 0);
      stSeries.setData(clientIndicators.series['supertrend'].map((p) => ({ time: p.time as Time, value: p.value as number })));
    }

    // Ichimoku Cloud
    if (overlays.ichimoku?.enabled) {
      if (clientIndicators.series['ichimoku_tenkan']) {
        const s = chart.addSeries(LineSeries, { color: palette.ichimokuTenkan, lineWidth: 1 }, 0);
        s.setData(clientIndicators.series['ichimoku_tenkan'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['ichimoku_kijun']) {
        const s = chart.addSeries(LineSeries, { color: palette.ichimokuKijun, lineWidth: 1 }, 0);
        s.setData(clientIndicators.series['ichimoku_kijun'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['ichimoku_senkou_a']) {
        const s = chart.addSeries(LineSeries, { color: palette.ichimokuSenkouA, lineWidth: 1, lineStyle: 2 }, 0);
        s.setData(clientIndicators.series['ichimoku_senkou_a'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
      if (clientIndicators.series['ichimoku_senkou_b']) {
        const s = chart.addSeries(LineSeries, { color: palette.ichimokuSenkouB, lineWidth: 1, lineStyle: 2 }, 0);
        s.setData(clientIndicators.series['ichimoku_senkou_b'].map((p) => ({ time: p.time as Time, value: p.value as number })));
      }
    }

    // --- Pane 0: Price Lines & Markers ---
    // Pivot Points
    if (overlays.pivot_points?.enabled) {
      const p = clientIndicators.series['pivot_p']?.[0]?.value as number | undefined;
      const r1 = clientIndicators.series['pivot_r1']?.[0]?.value as number | undefined;
      const s1 = clientIndicators.series['pivot_s1']?.[0]?.value as number | undefined;
      const r2 = clientIndicators.series['pivot_r2']?.[0]?.value as number | undefined;
      const s2 = clientIndicators.series['pivot_s2']?.[0]?.value as number | undefined;

      if (typeof p === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({ price: p, color: palette.pivotP, lineWidth: 1, lineStyle: 2, title: 'Pivot P' })
        );
      }
      if (typeof r1 === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({ price: r1, color: palette.pivotR, lineWidth: 1, lineStyle: 2, title: 'Pivot R1' })
        );
      }
      if (typeof s1 === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({ price: s1, color: palette.pivotS, lineWidth: 1, lineStyle: 2, title: 'Pivot S1' })
        );
      }
      if (typeof r2 === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({ price: r2, color: palette.pivotR, lineWidth: 1, lineStyle: 3, title: 'Pivot R2' })
        );
      }
      if (typeof s2 === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({ price: s2, color: palette.pivotS, lineWidth: 1, lineStyle: 3, title: 'Pivot S2' })
        );
      }
    }

    // SMC Order Blocks
    if (overlays.smc_order_blocks && structureData?.order_blocks) {
      for (const ob of structureData.order_blocks.slice(0, 4)) {
        const isBullish = (ob.direction || ob.type)?.toLowerCase() === 'bullish';
        const color = isBullish ? palette.obBull : palette.obBear;
        const high = ob.price_high ?? ob.top;
        const low = ob.price_low ?? ob.bottom;
        if (typeof high === 'number' && typeof low === 'number') {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: high,
              color,
              lineWidth: 1,
              lineStyle: 2,
              title: `OB High (${isBullish ? 'Bull' : 'Bear'})`,
            }),
            candleSeries.createPriceLine({
              price: low,
              color,
              lineWidth: 1,
              lineStyle: 2,
              title: 'OB Low',
            })
          );
        }
      }
    }

    // SMC Fair Value Gaps
    if (overlays.smc_fvg && structureData?.fair_value_gaps) {
      for (const fvg of structureData.fair_value_gaps.slice(0, 3)) {
        const isBullish = (fvg.direction || fvg.type)?.toLowerCase() === 'bullish';
        const color = isBullish ? palette.fvgBull : palette.fvgBear;
        const high = fvg.gap_high ?? fvg.top_price ?? fvg.top;
        const low = fvg.gap_low ?? fvg.bottom_price ?? fvg.bottom;
        if (typeof high === 'number' && typeof low === 'number') {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: high,
              color,
              lineWidth: 1,
              lineStyle: 3,
              title: 'FVG High',
            }),
            candleSeries.createPriceLine({
              price: low,
              color,
              lineWidth: 1,
              lineStyle: 3,
              title: 'FVG Low',
            })
          );
        }
      }
    }

    // SMC Liquidity Pools
    if (overlays.smc_liquidity && structureData?.liquidity_pools) {
      for (const pool of structureData.liquidity_pools.slice(0, 3)) {
        if (typeof pool.price === 'number') {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: pool.price,
              color: palette.eqPoolColor,
              lineWidth: 1,
              lineStyle: 2,
              title: `Liq Pool (${pool.type || 'EQ'})`,
            })
          );
        }
      }
    }

    // SMC Structure Breaks (Markers)
    if (overlays.smc_bos && (structureData?.structure_breaks || structureData?.breaks)) {
      const breaks = structureData.structure_breaks || structureData.breaks || [];
      const markers: any[] = [];
      for (const sb of breaks.slice(-8)) {
        if (sb.time) {
          const isBull = (sb.direction || '').toLowerCase() === 'bullish';
          markers.push({
            time: sb.time as Time,
            position: isBull ? 'belowBar' : 'aboveBar',
            color: sb.type === 'CHoCH' ? palette.chochColor : palette.bosColor,
            shape: isBull ? 'arrowUp' : 'arrowDown',
            text: `${sb.type || 'BOS'} (${sb.direction || ''})`,
          });
        }
      }
      if (markers.length > 0) {
        try {
          createSeriesMarkers(candleSeries, markers);
        } catch {
          // fallback if marker timestamps outside loaded bars
        }
      }
    }

    // Volume Profile POC / VAH / VAL
    if (overlays.volume_profile) {
      const vp = structureData?.volume_profile || computeVisibleVolumeProfile(candles);
      if (vp && typeof vp.poc === 'number') {
        priceLinesRef.current.push(
          candleSeries.createPriceLine({
            price: vp.poc,
            color: palette.pocColor,
            lineWidth: 2,
            lineStyle: 0,
            title: 'VP POC',
          }),
          candleSeries.createPriceLine({
            price: vp.vah,
            color: palette.vahValColor,
            lineWidth: 1,
            lineStyle: 2,
            title: 'VP VAH',
          }),
          candleSeries.createPriceLine({
            price: vp.val,
            color: palette.vahValColor,
            lineWidth: 1,
            lineStyle: 2,
            title: 'VP VAL',
          })
        );
      }
    }

    // TimesFM Forecast Cone
    if (overlays.timesfm_cone && structureData?.timesfm_cone && lastPrice) {
      const cone = structureData.timesfm_cone;
      const q = cone.quantiles || {};
      const drift = cone.drift || 0.0;
      const q10Val = q.q10?.[q.q10.length - 1] ?? lastPrice * (1 + drift - 0.004);
      const q50Val = q.q50?.[q.q50.length - 1] ?? lastPrice * (1 + drift);
      const q90Val = q.q90?.[q.q90.length - 1] ?? lastPrice * (1 + drift + 0.004);

      priceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: q50Val,
          color: palette.timesfmMedian,
          lineWidth: 2,
          lineStyle: 1,
          title: 'TimesFM q50',
        }),
        candleSeries.createPriceLine({
          price: q90Val,
          color: palette.timesfmCone,
          lineWidth: 1,
          lineStyle: 2,
          title: 'TimesFM q90',
        }),
        candleSeries.createPriceLine({
          price: q10Val,
          color: palette.timesfmCone,
          lineWidth: 1,
          lineStyle: 2,
          title: 'TimesFM q10',
        })
      );
    }

    // Active Positions
    if (overlays.show_positions && activePositions && activePositions.length > 0) {
      for (const pos of activePositions) {
        if (pos.symbol.toUpperCase() === symbol.toUpperCase() && typeof pos.entry_price === 'number') {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: pos.entry_price,
              color: palette.posEntry,
              lineWidth: 2,
              lineStyle: 0,
              title: `POS #${pos.ticket ?? pos.id} ${pos.direction.toUpperCase()}`,
            })
          );
          if (typeof pos.sl === 'number' && pos.sl > 0) {
            priceLinesRef.current.push(
              candleSeries.createPriceLine({
                price: pos.sl,
                color: palette.posSl,
                lineWidth: 1,
                lineStyle: 2,
                title: `SL #${pos.ticket ?? pos.id}`,
              })
            );
          }
          if (typeof pos.tp === 'number' && pos.tp > 0) {
            priceLinesRef.current.push(
              candleSeries.createPriceLine({
                price: pos.tp,
                color: palette.posTp,
                lineWidth: 1,
                lineStyle: 2,
                title: `TP #${pos.ticket ?? pos.id}`,
              })
            );
          }
        }
      }
    }

    // AI Proposals
    if (overlays.show_ai_proposals && latestAiProposal) {
      if (
        latestAiProposal.symbol.toUpperCase() === symbol.toUpperCase() &&
        typeof latestAiProposal.entry_price === 'number'
      ) {
        const confStr = latestAiProposal.confidence ? ` (${(latestAiProposal.confidence * 100).toFixed(0)}%)` : '';
        priceLinesRef.current.push(
          candleSeries.createPriceLine({
            price: latestAiProposal.entry_price,
            color: palette.aiEntry,
            lineWidth: 2,
            lineStyle: 1,
            title: `AI ${latestAiProposal.decision.toUpperCase()}${confStr}`,
          })
        );
        if (typeof latestAiProposal.sl === 'number' && latestAiProposal.sl > 0) {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: latestAiProposal.sl,
              color: palette.aiSl,
              lineWidth: 1,
              lineStyle: 2,
              title: 'AI SL',
            })
          );
        }
        if (typeof latestAiProposal.tp === 'number' && latestAiProposal.tp > 0) {
          priceLinesRef.current.push(
            candleSeries.createPriceLine({
              price: latestAiProposal.tp,
              color: palette.aiTp,
              lineWidth: 1,
              lineStyle: 2,
              title: 'AI TP',
            })
          );
        }
      }
    }

    // --- Panes 1..K: Synchronized Oscillators ---
    let currentPaneIndex = 1;

    for (const oscName of activeOscillatorList) {
      const paneIdx = currentPaneIndex++;

      if (oscName === 'volume') {
        const volSeries = chart.addSeries(
          HistogramSeries,
          {
            priceFormat: { type: 'volume' },
            priceScaleId: `vol_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['volume']) {
          volSeries.setData(
            clientIndicators.series['volume'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
              color: p.color || palette.volUp,
            }))
          );
        }
        if (clientIndicators.series['volume_ma'] && clientIndicators.series['volume_ma'].length > 0) {
          const maSeries = chart.addSeries(
            LineSeries,
            {
              color: palette.volMa,
              lineWidth: 1,
              priceScaleId: `vol_scale_${paneIdx}`,
            },
            paneIdx
          );
          maSeries.setData(
            clientIndicators.series['volume_ma'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
      } else if (oscName === 'rsi') {
        const rsiSeries = chart.addSeries(
          LineSeries,
          {
            color: palette.rsiLine,
            lineWidth: 2,
            priceScaleId: `rsi_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['rsi']) {
          rsiSeries.setData(
            clientIndicators.series['rsi'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        const ob = activeConfig.oscillators.rsi.overbought || 70;
        const os = activeConfig.oscillators.rsi.oversold || 30;
        rsiSeries.createPriceLine({ price: ob, color: palette.rsiBand, lineWidth: 1, lineStyle: 2, title: `OB ${ob}` });
        rsiSeries.createPriceLine({ price: 50, color: palette.borderScale, lineWidth: 1, lineStyle: 3, title: '50' });
        rsiSeries.createPriceLine({ price: os, color: palette.rsiBand, lineWidth: 1, lineStyle: 2, title: `OS ${os}` });
      } else if (oscName === 'macd') {
        const histSeries = chart.addSeries(
          HistogramSeries,
          {
            priceScaleId: `macd_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['macd_hist']) {
          histSeries.setData(
            clientIndicators.series['macd_hist'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
              color: (p.value as number) >= 0 ? palette.macdHistBull : palette.macdHistBear,
            }))
          );
        }
        const macdLine = chart.addSeries(
          LineSeries,
          {
            color: palette.macdLine,
            lineWidth: 2,
            priceScaleId: `macd_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['macd_line']) {
          macdLine.setData(
            clientIndicators.series['macd_line'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        const sigLine = chart.addSeries(
          LineSeries,
          {
            color: palette.macdSignal,
            lineWidth: 1,
            priceScaleId: `macd_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['macd_signal']) {
          sigLine.setData(
            clientIndicators.series['macd_signal'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        histSeries.createPriceLine({ price: 0, color: palette.borderScale, lineWidth: 1, lineStyle: 3 });
      } else if (oscName === 'stochastic') {
        const kSeries = chart.addSeries(
          LineSeries,
          {
            color: palette.stochK,
            lineWidth: 2,
            priceScaleId: `stoch_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['stoch_k']) {
          kSeries.setData(
            clientIndicators.series['stoch_k'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        const dSeries = chart.addSeries(
          LineSeries,
          {
            color: palette.stochD,
            lineWidth: 1,
            priceScaleId: `stoch_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['stoch_d']) {
          dSeries.setData(
            clientIndicators.series['stoch_d'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        kSeries.createPriceLine({ price: 80, color: palette.borderScale, lineWidth: 1, lineStyle: 2, title: '80' });
        kSeries.createPriceLine({ price: 20, color: palette.borderScale, lineWidth: 1, lineStyle: 2, title: '20' });
      } else if (oscName === 'adx') {
        const adxSeries = chart.addSeries(
          LineSeries,
          {
            color: palette.adxLine,
            lineWidth: 2,
            priceScaleId: `adx_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['adx']) {
          adxSeries.setData(
            clientIndicators.series['adx'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        const pDi = chart.addSeries(
          LineSeries,
          {
            color: palette.plusDi,
            lineWidth: 1,
            priceScaleId: `adx_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['plus_di']) {
          pDi.setData(
            clientIndicators.series['plus_di'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        const mDi = chart.addSeries(
          LineSeries,
          {
            color: palette.minusDi,
            lineWidth: 1,
            priceScaleId: `adx_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['minus_di']) {
          mDi.setData(
            clientIndicators.series['minus_di'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        adxSeries.createPriceLine({ price: 25, color: palette.borderScale, lineWidth: 1, lineStyle: 2, title: '25' });
      } else if (oscName === 'atr') {
        const atrSeries = chart.addSeries(
          LineSeries,
          {
            color: palette.atrLine,
            lineWidth: 2,
            priceScaleId: `atr_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series['atr']) {
          atrSeries.setData(
            clientIndicators.series['atr'].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
      } else if (oscName === 'cvd') {
        const mode = activeConfig.oscillators.cvd_volatility?.mode || 'cvd';
        const key = mode === 'yz_vol' ? 'yz_vol' : mode === 'ac1' ? 'ac1' : 'cvd';
        const cvdSeries = chart.addSeries(
          LineSeries,
          {
            color: mode === 'yz_vol' ? palette.yzVolLine : palette.cvdBull,
            lineWidth: 2,
            priceScaleId: `cvd_scale_${paneIdx}`,
          },
          paneIdx
        );
        if (clientIndicators.series[key]) {
          cvdSeries.setData(
            clientIndicators.series[key].map((p) => ({
              time: p.time as Time,
              value: p.value as number,
            }))
          );
        }
        if (mode === 'cvd' || mode === 'ac1') {
          cvdSeries.createPriceLine({ price: 0, color: palette.borderScale, lineWidth: 1, lineStyle: 3 });
        }
      }
    }

    // Configure pane stretch factors
    const panes = chart.panes();
    if (panes[0]) panes[0].setStretchFactor(3000);
    for (let i = 1; i < panes.length; i++) {
      panes[i]?.setStretchFactor(900);
    }

    // Restore or fit range
    if (prevRange) {
      try {
        chart.timeScale().setVisibleLogicalRange(prevRange);
      } catch {
        chart.timeScale().fitContent();
      }
    } else {
      chart.timeScale().fitContent();
    }

    // 5. Interactive Crosshair Legend HUD
    const handleCrosshair = (param: MouseEventParams<Time>) => {
      if (!param.time || !param.seriesData) {
        setHoveredHud(null);
        return;
      }

      const candleVal = param.seriesData.get(candleSeries as any) as any;
      if (candleVal && typeof candleVal.open === 'number') {
        const barTime = param.time;
        const cMatch = candlesRef.current.find((c) => c.time === barTime);
        const vol = cMatch?.volume ?? 0;
        const chg = candleVal.open > 0 ? ((candleVal.close - candleVal.open) / candleVal.open) * 100 : 0;

        const indVals: HudItem[] = [];
        for (const [key, pts] of Object.entries(clientIndicators.series)) {
          const pt = pts.find((p) => p.time === barTime);
          if (pt && typeof pt.value === 'number') {
            indVals.push({
              name: key.toUpperCase().replace(/_/g, ' '),
              value: pt.value,
              color: pt.color,
            });
          }
        }

        setHoveredHud({
          timeStr: typeof barTime === 'number' ? new Date(barTime * 1000).toLocaleString() : String(barTime),
          open: candleVal.open,
          high: candleVal.high,
          low: candleVal.low,
          close: candleVal.close,
          volume: vol,
          changePct: chg,
          indicators: indVals,
        });
      }
    };

    chart.subscribeCrosshairMove(handleCrosshair);

    const handleResize = () => {
      if (container && chartInstanceRef.current) {
        const newTotalHeight = isFullscreen
          ? Math.max(560, window.innerHeight - 190)
          : height + activeOscillatorList.length * 115;
        chartInstanceRef.current.applyOptions({
          width: container.clientWidth,
          height: newTotalHeight,
        });
      }
    };

    const resizeObserver = new ResizeObserver(() => handleResize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.unsubscribeCrosshairMove(handleCrosshair);
      clearPriceLines();
      try {
        chart.remove();
      } catch {
        // ignore
      }
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [
    candles,
    clientIndicators,
    structureData,
    activePositions,
    latestAiProposal,
    activeOscillatorList,
    activeConfig,
    lastPrice,
    isFullscreen,
    height,
    palette,
    symbol,
    timeframe,
    clearPriceLines,
  ]);

  // Display symbol pills
  const displaySymbols = useMemo(() => {
    const norm = symbol.toUpperCase();
    if (POPULAR_SYMBOLS.includes(norm)) {
      return POPULAR_SYMBOLS;
    }
    return [norm, ...POPULAR_SYMBOLS];
  }, [symbol]);

  // Active HUD default fallback (when crosshair is idle)
  const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null;
  const activeHud: HudData | null = hoveredHud || (latestCandle ? {
    timeStr: new Date(latestCandle.time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    open: latestCandle.open,
    high: latestCandle.high,
    low: latestCandle.low,
    close: latestCandle.close,
    volume: latestCandle.volume ?? 0,
    changePct: latestCandle.open > 0 ? ((latestCandle.close - latestCandle.open) / latestCandle.open) * 100 : 0,
    indicators: clientIndicators.summary.map((s) => ({
      name: s.name,
      value: s.value,
      color: s.signal === 'bullish' ? palette.upColor : s.signal === 'bearish' ? palette.downColor : undefined,
    })),
  } : null);

  // Timeframe selector handler
  const handleSelectTimeframe = (tf: string) => {
    saveChartWorkspaceConfig(
      symbol,
      { ...activeConfig, timeframe: tf },
      isSymbolPinned ? 'symbol' : 'global'
    );
  };

  // Toggle Vision Sync handler
  const handleToggleVisionSync = () => {
    saveChartWorkspaceConfig(
      symbol,
      { ...activeConfig, vision_sync_enabled: !activeConfig.vision_sync_enabled },
      isSymbolPinned ? 'symbol' : 'global'
    );
  };


  const totalChartHeight = isFullscreen
    ? Math.max(560, window.innerHeight - 190)
    : height + activeOscillatorList.length * 115;

  return (
    <section
      className={`editorial-section ${className ?? ''}`.trim()}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: '2px',
        padding: '16px',
        position: isFullscreen ? 'fixed' : 'relative',
        top: isFullscreen ? 0 : undefined,
        left: isFullscreen ? 0 : undefined,
        width: isFullscreen ? '100vw' : undefined,
        height: isFullscreen ? '100vh' : undefined,
        zIndex: isFullscreen ? 9999 : undefined,
        overflow: isFullscreen ? 'auto' : undefined,
        boxSizing: 'border-box',
      }}
    >
      {/* Workstation Controls Toolbar */}
      <ChartControlsToolbar
        symbol={symbol}
        displaySymbols={displaySymbols}
        lastPrice={lastPrice}
        spreadPips={spreadPips}
        source={source}
        timeframe={timeframe}
        loading={loading}
        activeConfig={activeConfig}
        isSymbolPinned={isSymbolPinned}
        isStudioOpen={isStudioOpen}
        isFullscreen={isFullscreen}
        activeIndicatorsCount={activeIndicatorsCount}
        onSelectSymbol={handleSelectSymbol}
        onSelectTimeframe={handleSelectTimeframe}
        onRefresh={() => loadData()}
        onApplyPreset={(pId) => applyChartPreset(symbol, pId, isSymbolPinned ? 'symbol' : 'global')}
        onOpenStudio={() => setIsStudioOpen(true)}
        onToggleVisionSync={handleToggleVisionSync}
        onToggleFullscreen={() => setIsFullscreen((v) => !v)}
      />
      {/* ==================================================================== */}
      {/* Chart Canvas & HUD Container                                         */}
      {/* ==================================================================== */}
      <div
        style={{
          width: '100%',
          position: 'relative',
          borderRadius: '2px',
          overflow: 'hidden',
          background: palette.background,
        }}
      >
        {/* HUD Crosshair & Indicators Overlay */}
        {/* HUD Crosshair & Indicators Overlay */}
        <ChartHud
          activeHud={activeHud}
          symbol={symbol}
          timeframe={timeframe}
          palette={palette}
          isLight={isLight}
        />

        <div
          ref={chartContainerRef}
          style={{
            width: '100%',
            height: `${totalChartHeight}px`,
            position: 'relative',
          }}
        />
      </div>

      {/* Footer Status Bar: SMC Telemetry & Model Projections */}
      <ChartStatusBar
        symbol={symbol}
        structureData={structureData}
        activePositions={activePositions}
        latestAiProposal={latestAiProposal}
      />
      {/* Indicator Studio Popover */}
      <IndicatorStudioPopover
        isOpen={isStudioOpen}
        onClose={() => setIsStudioOpen(false)}
        symbol={symbol}
      />
    </section>
  );
};

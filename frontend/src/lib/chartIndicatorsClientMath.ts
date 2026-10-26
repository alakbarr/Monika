// ==============================================================================
// File: src/lib/chartIndicatorsClientMath.ts
// Description: Deterministic Client-Side Technical Indicator Mathematics,
// Multi-Timeframe Candle Merging, Preset Configurations & Summary Generators.
// Pure TypeScript — Zero External Dependencies.
// ==============================================================================

import type {
  ChartPresetId,
  ChartOverlaysConfig,
  ChartOscillatorsConfig,
  ChartWorkspaceConfig,
  IndicatorSummaryItem,
  IndicatorTimePoint,
} from '../types/api';

export const TIMEFRAME_SECONDS: Record<string, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  M30: 1800,
  H1: 3600,
  H4: 14400,
  D1: 86400,
  W1: 604800,
};

export const CHART_PRESETS: Record<ChartPresetId, ChartWorkspaceConfig> = {
  smc_institutional: {
    preset_id: 'smc_institutional',
    timeframe: 'H4',
    vision_sync_enabled: true,
    overlays: {
      ema: { enabled: true, periods: [20, 50, 200] },
      sma: { enabled: false, periods: [50, 200] },
      wma: { enabled: false, periods: [20] },
      bollinger: { enabled: false, period: 20, std_dev: 2.0 },
      keltner: { enabled: false, window: 20, window_atr: 10, multiplier: 1.5 },
      donchian: { enabled: false, window: 20 },
      vwap: { enabled: true, window: null },
      supertrend: { enabled: false, period: 10, multiplier: 3.0 },
      ichimoku: { enabled: false, tenkan: 9, kijun: 26, senkou_b: 52 },
      pivot_points: { enabled: false, method: 'classic' },
      smc_order_blocks: true,
      smc_fvg: true,
      smc_bos: true,
      smc_liquidity: true,
      volume_profile: true,
      timesfm_cone: true,
      show_positions: true,
      show_ai_proposals: true,
    },
    oscillators: {
      volume: { enabled: true, ma_period: 20 },
      rsi: { enabled: true, period: 14, overbought: 70, oversold: 30 },
      macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
      stochastic: { enabled: false, k_period: 14, d_period: 3 },
      adx: { enabled: false, period: 14 },
      atr: { enabled: true, period: 14 },
      cvd_volatility: { enabled: false, mode: 'cvd', window: 20 },
    },
  },
  trend_momentum: {
    preset_id: 'trend_momentum',
    timeframe: 'H1',
    vision_sync_enabled: true,
    overlays: {
      ema: { enabled: true, periods: [9, 21, 50, 200] },
      sma: { enabled: false, periods: [50, 200] },
      wma: { enabled: false, periods: [20] },
      bollinger: { enabled: false, period: 20, std_dev: 2.0 },
      keltner: { enabled: false, window: 20, window_atr: 10, multiplier: 1.5 },
      donchian: { enabled: false, window: 20 },
      vwap: { enabled: true, window: null },
      supertrend: { enabled: true, period: 10, multiplier: 3.0 },
      ichimoku: { enabled: false, tenkan: 9, kijun: 26, senkou_b: 52 },
      pivot_points: { enabled: false, method: 'classic' },
      smc_order_blocks: true,
      smc_fvg: false,
      smc_bos: true,
      smc_liquidity: false,
      volume_profile: false,
      timesfm_cone: true,
      show_positions: true,
      show_ai_proposals: true,
    },
    oscillators: {
      volume: { enabled: true, ma_period: 20 },
      rsi: { enabled: true, period: 14, overbought: 70, oversold: 30 },
      macd: { enabled: true, fast: 12, slow: 26, signal: 9 },
      stochastic: { enabled: false, k_period: 14, d_period: 3 },
      adx: { enabled: true, period: 14 },
      atr: { enabled: true, period: 14 },
      cvd_volatility: { enabled: false, mode: 'cvd', window: 20 },
    },
  },
  volatility_reversion: {
    preset_id: 'volatility_reversion',
    timeframe: 'M15',
    vision_sync_enabled: true,
    overlays: {
      ema: { enabled: true, periods: [20, 50] },
      sma: { enabled: false, periods: [50, 200] },
      wma: { enabled: false, periods: [20] },
      bollinger: { enabled: true, period: 20, std_dev: 2.0 },
      keltner: { enabled: true, window: 20, window_atr: 10, multiplier: 1.5 },
      donchian: { enabled: true, window: 20 },
      vwap: { enabled: true, window: null },
      supertrend: { enabled: false, period: 10, multiplier: 3.0 },
      ichimoku: { enabled: false, tenkan: 9, kijun: 26, senkou_b: 52 },
      pivot_points: { enabled: true, method: 'camarilla' },
      smc_order_blocks: false,
      smc_fvg: true,
      smc_bos: false,
      smc_liquidity: true,
      volume_profile: true,
      timesfm_cone: false,
      show_positions: true,
      show_ai_proposals: true,
    },
    oscillators: {
      volume: { enabled: true, ma_period: 20 },
      rsi: { enabled: true, period: 14, overbought: 70, oversold: 30 },
      macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
      stochastic: { enabled: true, k_period: 14, d_period: 3 },
      adx: { enabled: false, period: 14 },
      atr: { enabled: true, period: 14 },
      cvd_volatility: { enabled: true, mode: 'yz_vol', window: 20 },
    },
  },
  quant_orderflow: {
    preset_id: 'quant_orderflow',
    timeframe: 'M5',
    vision_sync_enabled: true,
    overlays: {
      ema: { enabled: true, periods: [20, 50] },
      sma: { enabled: false, periods: [50, 200] },
      wma: { enabled: false, periods: [20] },
      bollinger: { enabled: false, period: 20, std_dev: 2.0 },
      keltner: { enabled: false, window: 20, window_atr: 10, multiplier: 1.5 },
      donchian: { enabled: false, window: 20 },
      vwap: { enabled: true, window: null },
      supertrend: { enabled: false, period: 10, multiplier: 3.0 },
      ichimoku: { enabled: false, tenkan: 9, kijun: 26, senkou_b: 52 },
      pivot_points: { enabled: false, method: 'classic' },
      smc_order_blocks: true,
      smc_fvg: true,
      smc_bos: true,
      smc_liquidity: true,
      volume_profile: true,
      timesfm_cone: true,
      show_positions: true,
      show_ai_proposals: true,
    },
    oscillators: {
      volume: { enabled: true, ma_period: 20 },
      rsi: { enabled: true, period: 14, overbought: 70, oversold: 30 },
      macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
      stochastic: { enabled: false, k_period: 14, d_period: 3 },
      adx: { enabled: false, period: 14 },
      atr: { enabled: true, period: 14 },
      cvd_volatility: { enabled: true, mode: 'cvd', window: 20 },
    },
  },
  custom: {
    preset_id: 'custom',
    timeframe: 'H4',
    vision_sync_enabled: true,
    overlays: {
      ema: { enabled: true, periods: [20, 50, 200] },
      sma: { enabled: false, periods: [50, 200] },
      wma: { enabled: false, periods: [20] },
      bollinger: { enabled: false, period: 20, std_dev: 2.0 },
      keltner: { enabled: false, window: 20, window_atr: 10, multiplier: 1.5 },
      donchian: { enabled: false, window: 20 },
      vwap: { enabled: true, window: null },
      supertrend: { enabled: false, period: 10, multiplier: 3.0 },
      ichimoku: { enabled: false, tenkan: 9, kijun: 26, senkou_b: 52 },
      pivot_points: { enabled: false, method: 'classic' },
      smc_order_blocks: true,
      smc_fvg: true,
      smc_bos: true,
      smc_liquidity: true,
      volume_profile: true,
      timesfm_cone: true,
      show_positions: true,
      show_ai_proposals: true,
    },
    oscillators: {
      volume: { enabled: true, ma_period: 20 },
      rsi: { enabled: true, period: 14, overbought: 70, oversold: 30 },
      macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
      stochastic: { enabled: false, k_period: 14, d_period: 3 },
      adx: { enabled: false, period: 14 },
      atr: { enabled: true, period: 14 },
      cvd_volatility: { enabled: false, mode: 'cvd', window: 20 },
    },
  },
};

export const DEFAULT_CHART_WORKSPACE_CONFIG: ChartWorkspaceConfig =
  CHART_PRESETS.smc_institutional;

export function normalizeChartWorkspaceConfig(
  raw?: Partial<ChartWorkspaceConfig> | null
): ChartWorkspaceConfig {
  const fallback = DEFAULT_CHART_WORKSPACE_CONFIG;
  if (!raw) return JSON.parse(JSON.stringify(fallback));

  const overlaysRaw: Partial<ChartOverlaysConfig> = raw.overlays || {};
  const oscillatorsRaw: Partial<ChartOscillatorsConfig> = raw.oscillators || {};

  return {
    preset_id: raw.preset_id || fallback.preset_id,
    timeframe: raw.timeframe || fallback.timeframe,
    vision_sync_enabled:
      typeof raw.vision_sync_enabled === 'boolean'
        ? raw.vision_sync_enabled
        : fallback.vision_sync_enabled,
    scope: raw.scope || 'global',
    symbol: raw.symbol,
    overlays: {
      ema: {
        enabled: Boolean(overlaysRaw.ema?.enabled ?? fallback.overlays.ema.enabled),
        periods: Array.isArray(overlaysRaw.ema?.periods)
          ? overlaysRaw.ema.periods
          : fallback.overlays.ema.periods,
      },
      sma: {
        enabled: Boolean(overlaysRaw.sma?.enabled ?? fallback.overlays.sma.enabled),
        periods: Array.isArray(overlaysRaw.sma?.periods)
          ? overlaysRaw.sma.periods
          : fallback.overlays.sma.periods,
      },
      wma: {
        enabled: Boolean(overlaysRaw.wma?.enabled ?? fallback.overlays.wma.enabled),
        periods: Array.isArray(overlaysRaw.wma?.periods)
          ? overlaysRaw.wma.periods
          : fallback.overlays.wma.periods,
      },
      bollinger: {
        enabled: Boolean(overlaysRaw.bollinger?.enabled ?? fallback.overlays.bollinger.enabled),
        period: Number(overlaysRaw.bollinger?.period ?? fallback.overlays.bollinger.period) || 20,
        std_dev: Number(overlaysRaw.bollinger?.std_dev ?? fallback.overlays.bollinger.std_dev) || 2,
      },
      keltner: {
        enabled: Boolean(overlaysRaw.keltner?.enabled ?? fallback.overlays.keltner.enabled),
        window: Number(overlaysRaw.keltner?.window ?? fallback.overlays.keltner.window) || 20,
        window_atr:
          Number(overlaysRaw.keltner?.window_atr ?? fallback.overlays.keltner.window_atr) || 10,
        multiplier:
          Number(overlaysRaw.keltner?.multiplier ?? fallback.overlays.keltner.multiplier) || 1.5,
      },
      donchian: {
        enabled: Boolean(overlaysRaw.donchian?.enabled ?? fallback.overlays.donchian.enabled),
        window: Number(overlaysRaw.donchian?.window ?? fallback.overlays.donchian.window) || 20,
      },
      vwap: {
        enabled: Boolean(overlaysRaw.vwap?.enabled ?? fallback.overlays.vwap.enabled),
        window: overlaysRaw.vwap?.window ?? fallback.overlays.vwap.window,
      },
      supertrend: {
        enabled: Boolean(overlaysRaw.supertrend?.enabled ?? fallback.overlays.supertrend.enabled),
        period: Number(overlaysRaw.supertrend?.period ?? fallback.overlays.supertrend.period) || 10,
        multiplier:
          Number(overlaysRaw.supertrend?.multiplier ?? fallback.overlays.supertrend.multiplier) || 3,
      },
      ichimoku: {
        enabled: Boolean(overlaysRaw.ichimoku?.enabled ?? fallback.overlays.ichimoku.enabled),
        tenkan: Number(overlaysRaw.ichimoku?.tenkan ?? fallback.overlays.ichimoku.tenkan) || 9,
        kijun: Number(overlaysRaw.ichimoku?.kijun ?? fallback.overlays.ichimoku.kijun) || 26,
        senkou_b:
          Number(overlaysRaw.ichimoku?.senkou_b ?? fallback.overlays.ichimoku.senkou_b) || 52,
      },
      pivot_points: {
        enabled: Boolean(
          overlaysRaw.pivot_points?.enabled ?? fallback.overlays.pivot_points.enabled
        ),
        method: overlaysRaw.pivot_points?.method || fallback.overlays.pivot_points.method,
      },
      smc_order_blocks: Boolean(
        overlaysRaw.smc_order_blocks ?? fallback.overlays.smc_order_blocks
      ),
      smc_fvg: Boolean(overlaysRaw.smc_fvg ?? fallback.overlays.smc_fvg),
      smc_bos: Boolean(overlaysRaw.smc_bos ?? fallback.overlays.smc_bos),
      smc_liquidity: Boolean(overlaysRaw.smc_liquidity ?? fallback.overlays.smc_liquidity),
      volume_profile: Boolean(overlaysRaw.volume_profile ?? fallback.overlays.volume_profile),
      timesfm_cone: Boolean(overlaysRaw.timesfm_cone ?? fallback.overlays.timesfm_cone),
      show_positions: Boolean(overlaysRaw.show_positions ?? fallback.overlays.show_positions),
      show_ai_proposals: Boolean(
        overlaysRaw.show_ai_proposals ?? fallback.overlays.show_ai_proposals
      ),
    },
    oscillators: {
      volume: {
        enabled: Boolean(oscillatorsRaw.volume?.enabled ?? fallback.oscillators.volume.enabled),
        ma_period:
          Number(oscillatorsRaw.volume?.ma_period ?? fallback.oscillators.volume.ma_period) || 20,
      },
      rsi: {
        enabled: Boolean(oscillatorsRaw.rsi?.enabled ?? fallback.oscillators.rsi.enabled),
        period: Number(oscillatorsRaw.rsi?.period ?? fallback.oscillators.rsi.period) || 14,
        overbought:
          Number(oscillatorsRaw.rsi?.overbought ?? fallback.oscillators.rsi.overbought) || 70,
        oversold:
          Number(oscillatorsRaw.rsi?.oversold ?? fallback.oscillators.rsi.oversold) || 30,
      },
      macd: {
        enabled: Boolean(oscillatorsRaw.macd?.enabled ?? fallback.oscillators.macd.enabled),
        fast: Number(oscillatorsRaw.macd?.fast ?? fallback.oscillators.macd.fast) || 12,
        slow: Number(oscillatorsRaw.macd?.slow ?? fallback.oscillators.macd.slow) || 26,
        signal: Number(oscillatorsRaw.macd?.signal ?? fallback.oscillators.macd.signal) || 9,
      },
      stochastic: {
        enabled: Boolean(
          oscillatorsRaw.stochastic?.enabled ?? fallback.oscillators.stochastic.enabled
        ),
        k_period:
          Number(oscillatorsRaw.stochastic?.k_period ?? fallback.oscillators.stochastic.k_period) ||
          14,
        d_period:
          Number(oscillatorsRaw.stochastic?.d_period ?? fallback.oscillators.stochastic.d_period) ||
          3,
      },
      adx: {
        enabled: Boolean(oscillatorsRaw.adx?.enabled ?? fallback.oscillators.adx.enabled),
        period: Number(oscillatorsRaw.adx?.period ?? fallback.oscillators.adx.period) || 14,
      },
      atr: {
        enabled: Boolean(oscillatorsRaw.atr?.enabled ?? fallback.oscillators.atr.enabled),
        period: Number(oscillatorsRaw.atr?.period ?? fallback.oscillators.atr.period) || 14,
      },
      cvd_volatility: {
        enabled: Boolean(
          oscillatorsRaw.cvd_volatility?.enabled ?? fallback.oscillators.cvd_volatility.enabled
        ),
        mode: oscillatorsRaw.cvd_volatility?.mode || fallback.oscillators.cvd_volatility.mode,
        window:
          Number(
            oscillatorsRaw.cvd_volatility?.window ?? fallback.oscillators.cvd_volatility.window
          ) || 20,
      },
    },
  };
}

export function countActiveIndicators(config: ChartWorkspaceConfig): {
  overlaysCount: number;
  oscillatorsCount: number;
  smcCount: number;
  total: number;
} {
  let overlaysCount = 0;
  const o = config.overlays;
  if (o.ema?.enabled) overlaysCount += o.ema.periods?.length || 0;
  if (o.sma?.enabled) overlaysCount += o.sma.periods?.length || 0;
  if (o.wma?.enabled) overlaysCount += o.wma.periods?.length || 0;
  if (o.bollinger?.enabled) overlaysCount += 1;
  if (o.keltner?.enabled) overlaysCount += 1;
  if (o.donchian?.enabled) overlaysCount += 1;
  if (o.vwap?.enabled) overlaysCount += 1;
  if (o.supertrend?.enabled) overlaysCount += 1;
  if (o.ichimoku?.enabled) overlaysCount += 1;
  if (o.pivot_points?.enabled) overlaysCount += 1;
  if (o.timesfm_cone) overlaysCount += 1;
  if (o.show_positions) overlaysCount += 1;
  if (o.show_ai_proposals) overlaysCount += 1;

  let smcCount = 0;
  if (o.smc_order_blocks) smcCount += 1;
  if (o.smc_fvg) smcCount += 1;
  if (o.smc_bos) smcCount += 1;
  if (o.smc_liquidity) smcCount += 1;
  if (o.volume_profile) smcCount += 1;

  let oscillatorsCount = 0;
  const osc = config.oscillators;
  if (osc.volume?.enabled) oscillatorsCount += 1;
  if (osc.rsi?.enabled) oscillatorsCount += 1;
  if (osc.macd?.enabled) oscillatorsCount += 1;
  if (osc.stochastic?.enabled) oscillatorsCount += 1;
  if (osc.adx?.enabled) oscillatorsCount += 1;
  if (osc.atr?.enabled) oscillatorsCount += 1;
  if (osc.cvd_volatility?.enabled) oscillatorsCount += 1;

  return {
    overlaysCount,
    oscillatorsCount,
    smcCount,
    total: overlaysCount + oscillatorsCount + smcCount,
  };
}

export interface ClientCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

/**
 * Merges an incoming live tick into candle array.
 * Either extends the active candle's high/low/close/volume or appends a new candle on bar boundary.
 */
export function mergeRealtimeTickIntoCandles(
  candles: ClientCandle[],
  tickPrice: number,
  tickTimestampIsoOrSec?: string | number,
  timeframe = 'H4'
): ClientCandle[] {
  if (typeof tickPrice !== 'number' || isNaN(tickPrice) || tickPrice <= 0) {
    return candles;
  }

  const tfSec = TIMEFRAME_SECONDS[timeframe] || 14400;

  let tickSec: number;
  if (typeof tickTimestampIsoOrSec === 'number') {
    tickSec = tickTimestampIsoOrSec > 1e11 ? Math.floor(tickTimestampIsoOrSec / 1000) : tickTimestampIsoOrSec;
  } else if (typeof tickTimestampIsoOrSec === 'string') {
    const parsed = Date.parse(tickTimestampIsoOrSec);
    tickSec = !isNaN(parsed) ? Math.floor(parsed / 1000) : Math.floor(Date.now() / 1000);
  } else {
    tickSec = Math.floor(Date.now() / 1000);
  }

  const barStartSec = Math.floor(tickSec / tfSec) * tfSec;

  if (!candles || candles.length === 0) {
    return [
      {
        time: barStartSec,
        open: tickPrice,
        high: tickPrice,
        low: tickPrice,
        close: tickPrice,
        volume: 1,
      },
    ];
  }

  const last = candles[candles.length - 1];
  const lastTime = typeof last.time === 'number' ? last.time : Number(last.time);

  if (lastTime === barStartSec) {
    const updatedLast: ClientCandle = {
      ...last,
      high: Math.max(last.high, tickPrice),
      low: Math.min(last.low, tickPrice),
      close: tickPrice,
      volume: (last.volume || 0) + 1,
    };
    return [...candles.slice(0, -1), updatedLast];
  } else if (barStartSec > lastTime) {
    const newCandle: ClientCandle = {
      time: barStartSec,
      open: tickPrice,
      high: tickPrice,
      low: tickPrice,
      close: tickPrice,
      volume: 1,
    };
    return [...candles, newCandle];
  }

  return candles;
}

// -----------------------------------------------------------------------------
// Mathematical Helpers
// -----------------------------------------------------------------------------

function calculateSMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (period <= 0 || closes.length < period) return result;

  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += closes[i];
  }
  result[period - 1] = sum / period;

  for (let i = period; i < closes.length; i++) {
    sum += closes[i] - closes[i - period];
    result[i] = sum / period;
  }
  return result;
}

function calculateEMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (period <= 0 || closes.length < period) return result;

  const k = 2 / (period + 1);
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += closes[i];
  }
  let prevEma = sum / period;
  result[period - 1] = prevEma;

  for (let i = period; i < closes.length; i++) {
    prevEma = closes[i] * k + prevEma * (1 - k);
    result[i] = prevEma;
  }
  return result;
}

function calculateWMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (period <= 0 || closes.length < period) return result;

  const denominator = (period * (period + 1)) / 2;

  for (let i = period - 1; i < closes.length; i++) {
    let weightedSum = 0;
    for (let j = 0; j < period; j++) {
      weightedSum += closes[i - period + 1 + j] * (j + 1);
    }
    result[i] = weightedSum / denominator;
  }
  return result;
}

function calculateTrueRange(candles: ClientCandle[]): number[] {
  const tr = new Array<number>(candles.length).fill(0);
  if (candles.length === 0) return tr;

  tr[0] = Math.max(0, candles[0].high - candles[0].low);
  for (let i = 1; i < candles.length; i++) {
    const hl = candles[i].high - candles[i].low;
    const hcp = Math.abs(candles[i].high - candles[i - 1].close);
    const lcp = Math.abs(candles[i].low - candles[i - 1].close);
    tr[i] = Math.max(hl, hcp, lcp);
  }
  return tr;
}

function calculateWilderATR(candles: ClientCandle[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(candles.length).fill(null);
  if (period <= 0 || candles.length < period) return result;

  const tr = calculateTrueRange(candles);
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += tr[i];
  }
  let atr = sum / period;
  result[period - 1] = atr;

  for (let i = period; i < candles.length; i++) {
    atr = (atr * (period - 1) + tr[i]) / period;
    result[i] = atr;
  }
  return result;
}

// -----------------------------------------------------------------------------
// Main Indicator Calculation Function
// -----------------------------------------------------------------------------

export interface ComputedClientIndicators {
  series: Record<string, IndicatorTimePoint[]>;
  summary: IndicatorSummaryItem[];
}

export function computeClientIndicatorSeries(
  candles: ClientCandle[],
  config: ChartWorkspaceConfig
): ComputedClientIndicators {
  const series: Record<string, IndicatorTimePoint[]> = {};
  const summary: IndicatorSummaryItem[] = [];

  if (!candles || candles.length === 0) {
    return { series, summary };
  }

  const n = candles.length;
  const times = candles.map((c) => c.time);
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const opens = candles.map((c) => c.open);
  const volumes = candles.map((c) => c.volume || 0);
  const currentPrice = closes[n - 1];

  const o = config.overlays;
  const osc = config.oscillators;

  // 1. EMA Overlays
  if (o.ema?.enabled && Array.isArray(o.ema.periods)) {
    for (const p of o.ema.periods) {
      if (p > 0) {
        const emaVals = calculateEMA(closes, p);
        const pts: IndicatorTimePoint[] = [];
        for (let i = 0; i < n; i++) {
          const val = emaVals[i];
          if (val !== null && !isNaN(val)) {
            pts.push({ time: times[i], value: Number(val.toFixed(5)) });
          }
        }
        series[`ema_${p}`] = pts;

        if (pts.length > 0) {
          const latest = pts[pts.length - 1].value as number;
          const isBull = currentPrice >= latest;
          summary.push({
            id: `ema_${p}`,
            name: `EMA ${p}`,
            value: latest.toFixed(latest < 10 ? 4 : 2),
            subValue: isBull ? 'Price Above' : 'Price Below',
            signal: isBull ? 'bullish' : 'bearish',
          });
        }
      }
    }
  }

  // 2. SMA Overlays
  if (o.sma?.enabled && Array.isArray(o.sma.periods)) {
    for (const p of o.sma.periods) {
      if (p > 0) {
        const smaVals = calculateSMA(closes, p);
        const pts: IndicatorTimePoint[] = [];
        for (let i = 0; i < n; i++) {
          const val = smaVals[i];
          if (val !== null && !isNaN(val)) {
            pts.push({ time: times[i], value: Number(val.toFixed(5)) });
          }
        }
        series[`sma_${p}`] = pts;
      }
    }
  }

  // 3. WMA Overlays
  if (o.wma?.enabled && Array.isArray(o.wma.periods)) {
    for (const p of o.wma.periods) {
      if (p > 0) {
        const wmaVals = calculateWMA(closes, p);
        const pts: IndicatorTimePoint[] = [];
        for (let i = 0; i < n; i++) {
          const val = wmaVals[i];
          if (val !== null && !isNaN(val)) {
            pts.push({ time: times[i], value: Number(val.toFixed(5)) });
          }
        }
        series[`wma_${p}`] = pts;
      }
    }
  }

  // 4. Bollinger Bands
  if (o.bollinger?.enabled) {
    const period = o.bollinger.period || 20;
    const stdDev = o.bollinger.std_dev || 2.0;
    const smaVals = calculateSMA(closes, period);
    const upperPts: IndicatorTimePoint[] = [];
    const midPts: IndicatorTimePoint[] = [];
    const lowerPts: IndicatorTimePoint[] = [];

    for (let i = period - 1; i < n; i++) {
      const mid = smaVals[i];
      if (mid !== null) {
        let sumSq = 0;
        for (let j = 0; j < period; j++) {
          const diff = closes[i - j] - mid;
          sumSq += diff * diff;
        }
        const sigma = Math.sqrt(sumSq / period);
        const up = mid + stdDev * sigma;
        const low = mid - stdDev * sigma;

        upperPts.push({ time: times[i], value: Number(up.toFixed(5)) });
        midPts.push({ time: times[i], value: Number(mid.toFixed(5)) });
        lowerPts.push({ time: times[i], value: Number(low.toFixed(5)) });
      }
    }
    series['bb_upper'] = upperPts;
    series['bb_mid'] = midPts;
    series['bb_lower'] = lowerPts;

    if (upperPts.length > 0) {
      const lastUp = upperPts[upperPts.length - 1].value as number;
      const lastLow = lowerPts[lowerPts.length - 1].value as number;
      const lastMid = midPts[midPts.length - 1].value as number;
      const bandwidth = lastMid > 0 ? (((lastUp - lastLow) / lastMid) * 100).toFixed(2) + '%' : '0%';
      const posPct = lastUp > lastLow ? (currentPrice - lastLow) / (lastUp - lastLow) : 0.5;

      summary.push({
        id: 'bollinger',
        name: `BB (${period}, ${stdDev})`,
        value: bandwidth,
        subValue: `Pos: ${(posPct * 100).toFixed(0)}%`,
        signal: posPct > 0.8 ? 'bearish' : posPct < 0.2 ? 'bullish' : 'neutral',
      });
    }
  }

  // 5. Keltner Channels
  if (o.keltner?.enabled) {
    const win = o.keltner.window || 20;
    const winAtr = o.keltner.window_atr || 10;
    const mult = o.keltner.multiplier || 1.5;

    const midEma = calculateEMA(closes, win);
    const atrVals = calculateWilderATR(candles, winAtr);

    const upperPts: IndicatorTimePoint[] = [];
    const midPts: IndicatorTimePoint[] = [];
    const lowerPts: IndicatorTimePoint[] = [];

    const startIdx = Math.max(win - 1, winAtr - 1);
    for (let i = startIdx; i < n; i++) {
      const mid = midEma[i];
      const atr = atrVals[i];
      if (mid !== null && atr !== null) {
        upperPts.push({ time: times[i], value: Number((mid + mult * atr).toFixed(5)) });
        midPts.push({ time: times[i], value: Number(mid.toFixed(5)) });
        lowerPts.push({ time: times[i], value: Number((mid - mult * atr).toFixed(5)) });
      }
    }
    series['kc_upper'] = upperPts;
    series['kc_mid'] = midPts;
    series['kc_lower'] = lowerPts;
  }

  // 6. Donchian Channels
  if (o.donchian?.enabled) {
    const win = o.donchian.window || 20;
    const upperPts: IndicatorTimePoint[] = [];
    const midPts: IndicatorTimePoint[] = [];
    const lowerPts: IndicatorTimePoint[] = [];

    for (let i = win - 1; i < n; i++) {
      let highest = -Infinity;
      let lowest = Infinity;
      for (let j = 0; j < win; j++) {
        const idx = i - j;
        if (highs[idx] > highest) highest = highs[idx];
        if (lows[idx] < lowest) lowest = lows[idx];
      }
      if (highest > -Infinity && lowest < Infinity) {
        const mid = (highest + lowest) / 2;
        upperPts.push({ time: times[i], value: Number(highest.toFixed(5)) });
        midPts.push({ time: times[i], value: Number(mid.toFixed(5)) });
        lowerPts.push({ time: times[i], value: Number(lowest.toFixed(5)) });
      }
    }
    series['dc_upper'] = upperPts;
    series['dc_mid'] = midPts;
    series['dc_lower'] = lowerPts;
  }

  // 7. VWAP
  if (o.vwap?.enabled) {
    const pts: IndicatorTimePoint[] = [];
    const rollingWin = o.vwap.window;

    if (rollingWin && rollingWin > 0) {
      for (let i = rollingWin - 1; i < n; i++) {
        let sumTPV = 0;
        let sumVol = 0;
        for (let j = 0; j < rollingWin; j++) {
          const idx = i - j;
          const tp = (highs[idx] + lows[idx] + closes[idx]) / 3;
          const vol = volumes[idx] > 0 ? volumes[idx] : 1;
          sumTPV += tp * vol;
          sumVol += vol;
        }
        if (sumVol > 0) {
          pts.push({ time: times[i], value: Number((sumTPV / sumVol).toFixed(5)) });
        }
      }
    } else {
      let cumTPV = 0;
      let cumVol = 0;
      for (let i = 0; i < n; i++) {
        const tp = (highs[i] + lows[i] + closes[i]) / 3;
        const vol = volumes[i] > 0 ? volumes[i] : 1;
        cumTPV += tp * vol;
        cumVol += vol;
        pts.push({ time: times[i], value: Number((cumTPV / cumVol).toFixed(5)) });
      }
    }
    series['vwap'] = pts;

    if (pts.length > 0) {
      const lastVwap = pts[pts.length - 1].value as number;
      const isBull = currentPrice >= lastVwap;
      summary.push({
        id: 'vwap',
        name: 'VWAP',
        value: lastVwap.toFixed(lastVwap < 10 ? 4 : 2),
        subValue: isBull ? 'Institutional Bull' : 'Institutional Bear',
        signal: isBull ? 'bullish' : 'bearish',
      });
    }
  }

  // 8. Supertrend
  if (o.supertrend?.enabled) {
    const period = o.supertrend.period || 10;
    const mult = o.supertrend.multiplier || 3.0;
    const atrVals = calculateWilderATR(candles, period);
    const pts: IndicatorTimePoint[] = [];

    let finalUpper = 0;
    let finalLower = 0;
    let trend = 1; // 1 = bull, -1 = bear

    for (let i = period - 1; i < n; i++) {
      const atr = atrVals[i];
      if (atr !== null) {
        const hl2 = (highs[i] + lows[i]) / 2;
        const basicUpper = hl2 + mult * atr;
        const basicLower = hl2 - mult * atr;

        if (i === period - 1) {
          finalUpper = basicUpper;
          finalLower = basicLower;
          trend = closes[i] >= hl2 ? 1 : -1;
        } else {
          finalUpper = basicUpper < finalUpper || closes[i - 1] > finalUpper ? basicUpper : finalUpper;
          finalLower = basicLower > finalLower || closes[i - 1] < finalLower ? basicLower : finalLower;

          if (trend === 1 && closes[i] < finalLower) {
            trend = -1;
          } else if (trend === -1 && closes[i] > finalUpper) {
            trend = 1;
          }
        }

        const superVal = trend === 1 ? finalLower : finalUpper;
        pts.push({
          time: times[i],
          value: Number(superVal.toFixed(5)),
          color: trend === 1 ? '#10B981' : '#F43F5E',
        });
      }
    }
    series['supertrend'] = pts;

    if (pts.length > 0) {
      const lastPt = pts[pts.length - 1];
      const isBull = trend === 1;
      summary.push({
        id: 'supertrend',
        name: `Supertrend (${period}, ${mult})`,
        value: (lastPt.value as number).toFixed(currentPrice < 10 ? 4 : 2),
        subValue: isBull ? 'BULL REGIME' : 'BEAR REGIME',
        signal: isBull ? 'bullish' : 'bearish',
      });
    }
  }

  // 9. Ichimoku Cloud
  if (o.ichimoku?.enabled) {
    const tenkanP = o.ichimoku.tenkan || 9;
    const kijunP = o.ichimoku.kijun || 26;
    const senkouBP = o.ichimoku.senkou_b || 52;

    const tenkanPts: IndicatorTimePoint[] = [];
    const kijunPts: IndicatorTimePoint[] = [];
    const senkouAPts: IndicatorTimePoint[] = [];
    const senkouBPts: IndicatorTimePoint[] = [];

    const getMidpoint = (startIdx: number, count: number): number => {
      let hi = -Infinity;
      let lo = Infinity;
      for (let j = 0; j < count; j++) {
        const idx = startIdx - j;
        if (highs[idx] > hi) hi = highs[idx];
        if (lows[idx] < lo) lo = lows[idx];
      }
      return (hi + lo) / 2;
    };

    for (let i = 0; i < n; i++) {
      let tenkanVal: number | null = null;
      let kijunVal: number | null = null;

      if (i >= tenkanP - 1) {
        tenkanVal = getMidpoint(i, tenkanP);
        tenkanPts.push({ time: times[i], value: Number(tenkanVal.toFixed(5)) });
      }

      if (i >= kijunP - 1) {
        kijunVal = getMidpoint(i, kijunP);
        kijunPts.push({ time: times[i], value: Number(kijunVal.toFixed(5)) });
      }

      if (tenkanVal !== null && kijunVal !== null) {
        const spanA = (tenkanVal + kijunVal) / 2;
        senkouAPts.push({ time: times[i], value: Number(spanA.toFixed(5)) });
      }

      if (i >= senkouBP - 1) {
        const spanB = getMidpoint(i, senkouBP);
        senkouBPts.push({ time: times[i], value: Number(spanB.toFixed(5)) });
      }
    }

    series['ichimoku_tenkan'] = tenkanPts;
    series['ichimoku_kijun'] = kijunPts;
    series['ichimoku_senkou_a'] = senkouAPts;
    series['ichimoku_senkou_b'] = senkouBPts;
  }

  // 10. Pivot Points
  if (o.pivot_points?.enabled && n >= 2) {
    const method = o.pivot_points.method || 'classic';
    const lastBar = candles[n - 2];
    const H = lastBar.high;
    const L = lastBar.low;
    const C = lastBar.close;

    let P = (H + L + C) / 3;
    let R1 = 0;
    let S1 = 0;
    let R2 = 0;
    let S2 = 0;

    if (method === 'classic') {
      P = (H + L + C) / 3;
      R1 = 2 * P - L;
      S1 = 2 * P - H;
      R2 = P + (H - L);
      S2 = P - (H - L);
    } else if (method === 'fibonacci') {
      P = (H + L + C) / 3;
      const range = H - L;
      R1 = P + 0.382 * range;
      S1 = P - 0.382 * range;
      R2 = P + 0.618 * range;
      S2 = P - 0.618 * range;
    } else if (method === 'camarilla') {
      P = (H + L + C) / 3;
      const range = H - L;
      R1 = C + (1.1 * range) / 12;
      S1 = C - (1.1 * range) / 12;
      R2 = C + (1.1 * range) / 6;
      S2 = C - (1.1 * range) / 6;
    } else if (method === 'woodie') {
      P = (H + L + 2 * C) / 4;
      R1 = 2 * P - L;
      S1 = 2 * P - H;
      R2 = P + (H - L);
      S2 = P - (H - L);
    }

    const t = times[n - 1];
    series['pivot_p'] = [{ time: t, value: Number(P.toFixed(5)) }];
    series['pivot_r1'] = [{ time: t, value: Number(R1.toFixed(5)) }];
    series['pivot_s1'] = [{ time: t, value: Number(S1.toFixed(5)) }];
    series['pivot_r2'] = [{ time: t, value: Number(R2.toFixed(5)) }];
    series['pivot_s2'] = [{ time: t, value: Number(S2.toFixed(5)) }];
  }

  // 11. Volume & Volume MA
  if (osc.volume?.enabled) {
    const volPts: IndicatorTimePoint[] = [];
    for (let i = 0; i < n; i++) {
      const isUp = closes[i] >= opens[i];
      volPts.push({
        time: times[i],
        value: volumes[i],
        color: isUp ? '#10B981' : '#F43F5E',
      });
    }
    series['volume'] = volPts;

    const maPeriod = osc.volume.ma_period || 20;
    const volMaVals = calculateSMA(volumes, maPeriod);
    const volMaPts: IndicatorTimePoint[] = [];
    for (let i = 0; i < n; i++) {
      const v = volMaVals[i];
      if (v !== null) {
        volMaPts.push({ time: times[i], value: Number(v.toFixed(0)) });
      }
    }
    series['volume_ma'] = volMaPts;
  }

  // 12. RSI
  if (osc.rsi?.enabled) {
    const period = osc.rsi.period || 14;
    const rsiPts: IndicatorTimePoint[] = [];

    if (n > period) {
      const gains: number[] = new Array(n).fill(0);
      const losses: number[] = new Array(n).fill(0);

      for (let i = 1; i < n; i++) {
        const diff = closes[i] - closes[i - 1];
        if (diff > 0) gains[i] = diff;
        else losses[i] = -diff;
      }

      let avgGain = 0;
      let avgLoss = 0;
      for (let i = 1; i <= period; i++) {
        avgGain += gains[i];
        avgLoss += losses[i];
      }
      avgGain /= period;
      avgLoss /= period;

      let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      let rsi = 100 - 100 / (1 + rs);
      rsiPts.push({ time: times[period], value: Number(rsi.toFixed(2)) });

      for (let i = period + 1; i < n; i++) {
        avgGain = (avgGain * (period - 1) + gains[i]) / period;
        avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
        rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        rsi = 100 - 100 / (1 + rs);
        rsiPts.push({ time: times[i], value: Number(rsi.toFixed(2)) });
      }
    }
    series['rsi'] = rsiPts;

    if (rsiPts.length > 0) {
      const lastRsi = rsiPts[rsiPts.length - 1].value as number;
      const ob = osc.rsi.overbought || 70;
      const os = osc.rsi.oversold || 30;
      const signal = lastRsi >= ob ? 'bearish' : lastRsi <= os ? 'bullish' : 'neutral';
      summary.push({
        id: 'rsi',
        name: `RSI (${period})`,
        value: lastRsi.toFixed(1),
        subValue: lastRsi >= ob ? 'Overbought' : lastRsi <= os ? 'Oversold' : 'Neutral Momentum',
        signal,
      });
    }
  }

  // 13. MACD
  if (osc.macd?.enabled) {
    const fast = osc.macd.fast || 12;
    const slow = osc.macd.slow || 26;
    const sigP = osc.macd.signal || 9;

    const fastEma = calculateEMA(closes, fast);
    const slowEma = calculateEMA(closes, slow);

    const macdLineVals: (number | null)[] = new Array(n).fill(null);
    const macdDiffs: number[] = [];
    const validIndices: number[] = [];

    for (let i = slow - 1; i < n; i++) {
      const f = fastEma[i];
      const s = slowEma[i];
      if (f !== null && s !== null) {
        const diff = f - s;
        macdLineVals[i] = diff;
        macdDiffs.push(diff);
        validIndices.push(i);
      }
    }

    const signalVals = calculateEMA(macdDiffs, sigP);

    const linePts: IndicatorTimePoint[] = [];
    const sigPts: IndicatorTimePoint[] = [];
    const histPts: IndicatorTimePoint[] = [];

    for (let k = 0; k < validIndices.length; k++) {
      const origIdx = validIndices[k];
      const mVal = macdDiffs[k];
      const sVal = signalVals[k];

      linePts.push({ time: times[origIdx], value: Number(mVal.toFixed(5)) });
      if (sVal !== null) {
        sigPts.push({ time: times[origIdx], value: Number(sVal.toFixed(5)) });
        const hist = mVal - sVal;
        histPts.push({
          time: times[origIdx],
          value: Number(hist.toFixed(5)),
          color: hist >= 0 ? '#10B981' : '#F43F5E',
        });
      }
    }

    series['macd_line'] = linePts;
    series['macd_signal'] = sigPts;
    series['macd_hist'] = histPts;

    if (histPts.length > 0) {
      const lastHist = histPts[histPts.length - 1].value as number;
      summary.push({
        id: 'macd',
        name: `MACD (${fast}, ${slow}, ${sigP})`,
        value: lastHist >= 0 ? `+${lastHist.toFixed(4)}` : lastHist.toFixed(4),
        subValue: lastHist >= 0 ? 'Bullish Acceleration' : 'Bearish Pressure',
        signal: lastHist >= 0 ? 'bullish' : 'bearish',
      });
    }
  }

  // 14. Stochastic Oscillator
  if (osc.stochastic?.enabled) {
    const kPeriod = osc.stochastic.k_period || 14;
    const dPeriod = osc.stochastic.d_period || 3;

    const kRawVals: (number | null)[] = new Array(n).fill(null);
    const kArray: number[] = [];
    const kIndices: number[] = [];

    for (let i = kPeriod - 1; i < n; i++) {
      let lowest = Infinity;
      let highest = -Infinity;
      for (let j = 0; j < kPeriod; j++) {
        const idx = i - j;
        if (lows[idx] < lowest) lowest = lows[idx];
        if (highs[idx] > highest) highest = highs[idx];
      }
      const denom = highest - lowest;
      const k = denom > 0 ? ((closes[i] - lowest) / denom) * 100 : 50;
      kRawVals[i] = k;
      kArray.push(k);
      kIndices.push(i);
    }

    const dVals = calculateSMA(kArray, dPeriod);
    const kPts: IndicatorTimePoint[] = [];
    const dPts: IndicatorTimePoint[] = [];

    for (let idx = 0; idx < kIndices.length; idx++) {
      const origI = kIndices[idx];
      const kVal = kArray[idx];
      const dVal = dVals[idx];

      kPts.push({ time: times[origI], value: Number(kVal.toFixed(2)) });
      if (dVal !== null) {
        dPts.push({ time: times[origI], value: Number(dVal.toFixed(2)) });
      }
    }

    series['stoch_k'] = kPts;
    series['stoch_d'] = dPts;
  }

  // 15. ADX / +DI / -DI
  if (osc.adx?.enabled) {
    const period = osc.adx.period || 14;
    if (n > period * 2) {
      const tr = calculateTrueRange(candles);
      const plusDM = new Array(n).fill(0);
      const minusDM = new Array(n).fill(0);

      for (let i = 1; i < n; i++) {
        const upMove = highs[i] - highs[i - 1];
        const downMove = lows[i - 1] - lows[i];
        if (upMove > downMove && upMove > 0) plusDM[i] = upMove;
        if (downMove > upMove && downMove > 0) minusDM[i] = downMove;
      }

      let smoothTR = 0;
      let smoothPlusDM = 0;
      let smoothMinusDM = 0;

      for (let i = 1; i <= period; i++) {
        smoothTR += tr[i];
        smoothPlusDM += plusDM[i];
        smoothMinusDM += minusDM[i];
      }

      const dxArray: number[] = [];
      const dxTimes: number[] = [];
      const plusDiPts: IndicatorTimePoint[] = [];
      const minusDiPts: IndicatorTimePoint[] = [];

      for (let i = period + 1; i < n; i++) {
        smoothTR = smoothTR - smoothTR / period + tr[i];
        smoothPlusDM = smoothPlusDM - smoothPlusDM / period + plusDM[i];
        smoothMinusDM = smoothMinusDM - smoothMinusDM / period + minusDM[i];

        const plusDI = smoothTR > 0 ? (smoothPlusDM / smoothTR) * 100 : 0;
        const minusDI = smoothTR > 0 ? (smoothMinusDM / smoothTR) * 100 : 0;
        const diSum = plusDI + minusDI;
        const dx = diSum > 0 ? (Math.abs(plusDI - minusDI) / diSum) * 100 : 0;

        plusDiPts.push({ time: times[i], value: Number(plusDI.toFixed(2)) });
        minusDiPts.push({ time: times[i], value: Number(minusDI.toFixed(2)) });
        dxArray.push(dx);
        dxTimes.push(times[i]);
      }

      const adxVals = calculateSMA(dxArray, period);
      const adxPts: IndicatorTimePoint[] = [];

      for (let i = 0; i < dxTimes.length; i++) {
        const a = adxVals[i];
        if (a !== null) {
          adxPts.push({ time: dxTimes[i], value: Number(a.toFixed(2)) });
        }
      }

      series['adx'] = adxPts;
      series['plus_di'] = plusDiPts;
      series['minus_di'] = minusDiPts;

      if (adxPts.length > 0) {
        const lastAdx = adxPts[adxPts.length - 1].value as number;
        summary.push({
          id: 'adx',
          name: `ADX (${period})`,
          value: lastAdx.toFixed(1),
          subValue: lastAdx >= 25 ? 'Strong Trend' : 'Range / Chop',
          signal: lastAdx >= 25 ? 'bullish' : 'neutral',
        });
      }
    }
  }

  // 16. ATR
  if (osc.atr?.enabled) {
    const period = osc.atr.period || 14;
    const atrVals = calculateWilderATR(candles, period);
    const atrPts: IndicatorTimePoint[] = [];

    for (let i = 0; i < n; i++) {
      const v = atrVals[i];
      if (v !== null) {
        atrPts.push({ time: times[i], value: Number(v.toFixed(5)) });
      }
    }
    series['atr'] = atrPts;

    if (atrPts.length > 0) {
      const lastAtr = atrPts[atrPts.length - 1].value as number;
      summary.push({
        id: 'atr',
        name: `ATR (${period})`,
        value: lastAtr.toFixed(currentPrice < 10 ? 4 : 2),
        subValue: 'Volatility Budget',
        signal: 'neutral',
      });
    }
  }

  // 17. CVD / Volatility
  if (osc.cvd_volatility?.enabled) {
    const mode = osc.cvd_volatility.mode || 'cvd';
    const win = osc.cvd_volatility.window || 20;

    if (mode === 'cvd') {
      const cvdPts: IndicatorTimePoint[] = [];
      let cumDelta = 0;
      for (let i = 0; i < n; i++) {
        const range = highs[i] - lows[i];
        const body = closes[i] - opens[i];
        const vol = volumes[i] > 0 ? volumes[i] : 1;
        const delta = range > 0 ? vol * (body / range) : 0;
        cumDelta += delta;
        cvdPts.push({
          time: times[i],
          value: Number(cumDelta.toFixed(0)),
          color: delta >= 0 ? '#10B981' : '#F43F5E',
        });
      }
      series['cvd'] = cvdPts;
    } else if (mode === 'yz_vol') {
      // Yang-Zhang Volatility
      const yzPts: IndicatorTimePoint[] = [];
      if (n > win) {
        for (let i = win; i < n; i++) {
          let sumOvernight = 0;
          let sumOpenClose = 0;
          let sumRogersSatchell = 0;
          for (let j = 0; j < win; j++) {
            const idx = i - j;
            const logCloseOpen = Math.log(closes[idx] / opens[idx]);
            const logOpenClosePrev = Math.log(opens[idx] / closes[idx - 1]);
            const u = Math.log(highs[idx] / opens[idx]);
            const d = Math.log(lows[idx] / opens[idx]);
            const c = Math.log(closes[idx] / opens[idx]);

            sumOvernight += logOpenClosePrev * logOpenClosePrev;
            sumOpenClose += logCloseOpen * logCloseOpen;
            sumRogersSatchell += u * (u - c) + d * (d - c);
          }
          const k = 0.34 / (1.34 + (win + 1) / (win - 1));
          const sigmaSq =
            (sumOvernight / (win - 1)) +
            k * (sumOpenClose / (win - 1)) +
            (1 - k) * (sumRogersSatchell / win);
          const yzAnnualized = Math.sqrt(Math.max(0, sigmaSq)) * Math.sqrt(252) * 100;
          yzPts.push({ time: times[i], value: Number(yzAnnualized.toFixed(2)) });
        }
      }
      series['yz_vol'] = yzPts;
    } else if (mode === 'ac1') {
      // First order autocorrelation of returns
      const ac1Pts: IndicatorTimePoint[] = [];
      if (n > win + 1) {
        const returns: number[] = new Array(n).fill(0);
        for (let i = 1; i < n; i++) {
          returns[i] = closes[i - 1] > 0 ? (closes[i] - closes[i - 1]) / closes[i - 1] : 0;
        }

        for (let i = win + 1; i < n; i++) {
          let sumX = 0;
          let sumY = 0;
          for (let j = 0; j < win; j++) {
            sumX += returns[i - j];
            sumY += returns[i - j - 1];
          }
          const meanX = sumX / win;
          const meanY = sumY / win;

          let cov = 0;
          let varX = 0;
          let varY = 0;
          for (let j = 0; j < win; j++) {
            const dx = returns[i - j] - meanX;
            const dy = returns[i - j - 1] - meanY;
            cov += dx * dy;
            varX += dx * dx;
            varY += dy * dy;
          }
          const stdX = Math.sqrt(varX);
          const stdY = Math.sqrt(varY);
          const ac1 = stdX * stdY > 0 ? cov / (stdX * stdY) : 0;
          ac1Pts.push({ time: times[i], value: Number(ac1.toFixed(3)) });
        }
      }
      series['ac1'] = ac1Pts;
    }
  }

  return { series, summary };
}

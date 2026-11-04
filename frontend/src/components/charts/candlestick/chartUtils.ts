// ==============================================================================
// File: src/components/charts/candlestick/chartUtils.ts
// Description: Pure formatting, types, and visible volume profile calculation
// utilities for CandlestickChart.
// ==============================================================================

import type { ClientCandle } from '../../../lib/chartIndicatorsClientMath';
import type { ChartPresetId } from '../../../types/api';

export interface HudItem {
  name: string;
  value: string | number;
  color?: string;
}

export interface HudData {
  timeStr: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  changePct?: number;
  indicators: HudItem[];
}

export const POPULAR_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD', 'BTCUSD'];
export const TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'];

export const PRESET_BUTTONS: Array<{ id: ChartPresetId; label: string }> = [
  { id: 'smc_institutional', label: 'SMC Institutional' },
  { id: 'trend_momentum', label: 'Trend + Momentum' },
  { id: 'volatility_reversion', label: 'Volatility & Reversion' },
  { id: 'quant_orderflow', label: 'Quant & Orderflow' },
];

export function formatPrice(p: number | undefined | null, sym: string): string {
  if (typeof p !== 'number' || isNaN(p)) return '—';
  if (sym.includes('JPY')) return p.toFixed(3);
  if (sym.includes('XAU')) return p.toFixed(2);
  if (sym.includes('BTC')) return p.toFixed(1);
  if (p > 1000) return p.toFixed(2);
  return p.toFixed(5);
}

export function computeVisibleVolumeProfile(candles: ClientCandle[]): { poc: number; vah: number; val: number } | null {
  if (!candles || candles.length < 5) return null;
  let minLow = Infinity;
  let maxHigh = -Infinity;
  for (const c of candles) {
    if (c.low < minLow) minLow = c.low;
    if (c.high > maxHigh) maxHigh = c.high;
  }
  if (minLow >= maxHigh) return null;
  const numBuckets = 30;
  const bucketSize = (maxHigh - minLow) / numBuckets;
  const bucketVolumes = new Float64Array(numBuckets);
  let totalVol = 0;
  for (const c of candles) {
    const vol = c.volume && c.volume > 0 ? c.volume : 1;
    totalVol += vol;
    const bucketIdx = Math.min(numBuckets - 1, Math.max(0, Math.floor((c.close - minLow) / bucketSize)));
    bucketVolumes[bucketIdx] += vol;
  }
  let maxVol = -1;
  let pocIdx = 0;
  for (let i = 0; i < numBuckets; i++) {
    if (bucketVolumes[i] > maxVol) {
      maxVol = bucketVolumes[i];
      pocIdx = i;
    }
  }
  const poc = minLow + (pocIdx + 0.5) * bucketSize;
  const targetAreaVol = totalVol * 0.7;
  let currentAreaVol = bucketVolumes[pocIdx];
  let upIdx = pocIdx;
  let downIdx = pocIdx;
  while (currentAreaVol < targetAreaVol && (upIdx < numBuckets - 1 || downIdx > 0)) {
    const nextUpVol = upIdx < numBuckets - 1 ? bucketVolumes[upIdx + 1] : -1;
    const nextDownVol = downIdx > 0 ? bucketVolumes[downIdx - 1] : -1;
    if (nextUpVol >= nextDownVol) {
      upIdx++;
      currentAreaVol += bucketVolumes[upIdx];
    } else {
      downIdx--;
      currentAreaVol += bucketVolumes[downIdx];
    }
  }
  const vah = minLow + (upIdx + 1) * bucketSize;
  const val = minLow + downIdx * bucketSize;
  return { poc, vah, val };
}

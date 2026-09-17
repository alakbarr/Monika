import { format, formatDistanceToNow, parseISO } from 'date-fns';

export const fmt = {
  // Currency
  usd: (val: number | null | undefined, showSign = false) => {
    if (val === null || val === undefined) return '—';
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
    return showSign && val > 0 ? `+${formatted}` : formatted;
  },

  // Percentage
  pct: (val: number | null | undefined, showSign = false, decimals = 2) => {
    if (val === null || val === undefined) return '—';
    const sign = showSign && val > 0 ? '+' : '';
    return `${sign}${val.toFixed(decimals)}%`;
  },

  // Price (auto-decimals based on magnitude)
  price: (val: number | null | undefined, symbol?: string) => {
    if (val === null || val === undefined) return '—';
    if (symbol?.includes('JPY') || val > 100) return val.toFixed(2);
    if (val > 1) return val.toFixed(4);
    return val.toFixed(5);
  },

  // Large numbers (K, M, B)
  compact: (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
    if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
    if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
    return val.toFixed(0);
  },

  // Lots
  lots: (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    return `${val.toFixed(2)}L`;
  },

  // Date/time
  time: (iso: string | null | undefined) => {
    if (!iso) return '—';
    return format(parseISO(iso), 'HH:mm:ss');
  },

  datetime: (iso: string | null | undefined) => {
    if (!iso) return '—';
    return format(parseISO(iso), 'dd MMM HH:mm');
  },

  ago: (iso: string | null | undefined) => {
    if (!iso) return '—';
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  },

  // R-ratio
  r: (val: number | null | undefined) => {
    if (val === null || val === undefined) return '—';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(2)}R`;
  },

  // Duration hours
  hours: (h: number | null | undefined) => {
    if (h === null || h === undefined) return '—';
    if (h < 1) return `${Math.round(h * 60)}m`;
    if (h < 24) return `${h.toFixed(1)}h`;
    return `${(h / 24).toFixed(1)}d`;
  },
};

// Color helpers
export function profitColor(val: number | null | undefined): string {
  if (!val) return '';
  return val > 0 ? 'text-profit' : val < 0 ? 'text-loss' : 'text-secondary';
}

export function directionColor(direction: string): string {
  return direction === 'buy' ? 'text-profit' : 'text-loss';
}

export function assessmentColor(assessment: string): string {
  switch (assessment) {
    case 'STRONG_PREDICTOR': return 'var(--color-profit)';
    case 'MODERATE': return 'var(--color-primary)';
    case 'WEAK_PREDICTOR': return 'var(--color-warn)';
    case 'NEGATIVE_PREDICTOR': return 'var(--color-loss)';
    default: return 'var(--color-text-secondary)';
  }
}

export function vixSentiment(vix: number): { label: string; color: string } {
  if (vix < 15) return { label: 'Low', color: 'var(--color-profit)' };
  if (vix < 20) return { label: 'Moderate', color: 'var(--color-primary)' };
  if (vix < 30) return { label: 'Elevated', color: 'var(--color-warn)' };
  return { label: 'Extreme', color: 'var(--color-loss)' };
}

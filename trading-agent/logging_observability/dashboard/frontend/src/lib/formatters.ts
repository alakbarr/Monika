import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { useDashboardStore } from '../store/dashboardStore';

export const fmt = {
  // Currency
  usd: (val: number | null | undefined, showSign = false) => {
    if (val === null || val === undefined) return '—';
    const formatted = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Math.abs(val));
    if (Math.abs(val) < 0.005) return '$0.00';
    if (val < 0) return `−${formatted}`;
    return showSign ? `+${formatted}` : formatted;
  },

  // Percentage
  pct: (val: number | null | undefined, showSign = false, decimals = 2) => {
    if (val === null || val === undefined) return '—';
    if (Math.abs(val) < 0.005) return `${(0).toFixed(decimals)}%`;
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

  // Date/time with dynamic UTC / LOCAL selection
  time: (iso: string | null | undefined) => {
    if (!iso) return '—';
    try {
      const d = parseISO(iso);
      if (isNaN(d.getTime())) return '—';
      const tz = useDashboardStore.getState().timeZoneDisplay;
      if (tz === 'LOCAL') {
        return `${format(d, 'HH:mm:ss')} LOC`;
      }
      return `${d.toISOString().slice(11, 19)} UTC`;
    } catch {
      return '—';
    }
  },

  // Institutional UTC Formatter (Decision D-02: YYYY-MM-DD HH:mm:ss UTC or HH:mm:ss UTC)
  utc: (iso: string | number | Date | null | undefined, includeDate = true) => {
    if (!iso) return '—';
    try {
      const d = typeof iso === 'string' ? parseISO(iso) : new Date(iso);
      if (isNaN(d.getTime())) return '—';
      const year = d.getUTCFullYear();
      const month = String(d.getUTCMonth() + 1).padStart(2, '0');
      const day = String(d.getUTCDate()).padStart(2, '0');
      const time = d.toISOString().slice(11, 19);
      return includeDate ? `${year}-${month}-${day} ${time} UTC` : `${time} UTC`;
    } catch {
      return '—';
    }
  },

  // Local Time Tooltip for title attribute (Decision D-02)
  localTooltip: (iso: string | number | Date | null | undefined) => {
    if (!iso) return '';
    try {
      const d = typeof iso === 'string' ? parseISO(iso) : new Date(iso);
      if (isNaN(d.getTime())) return '';
      return `${d.toLocaleString()} (Local)`;
    } catch {
      return '';
    }
  },

  datetime: (iso: string | null | undefined) => {
    if (!iso) return '—';
    try {
      const d = parseISO(iso);
      if (isNaN(d.getTime())) return '—';
      const tz = useDashboardStore.getState().timeZoneDisplay;
      if (tz === 'LOCAL') {
        return `${format(d, 'dd MMM HH:mm')} LOC`;
      }
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const day = String(d.getUTCDate()).padStart(2, '0');
      const mon = months[d.getUTCMonth()];
      const timeStr = d.toISOString().slice(11, 16);
      return `${day} ${mon} ${timeStr} UTC`;
    } catch {
      return '—';
    }
  },

  ago: (iso: string | null | undefined) => {
    if (!iso) return '—';
    try {
      const d = parseISO(iso);
      if (isNaN(d.getTime())) return '—';
      return formatDistanceToNow(d, { addSuffix: true });
    } catch {
      return '—';
    }
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

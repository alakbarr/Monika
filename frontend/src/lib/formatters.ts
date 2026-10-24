import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { useDashboardStore } from '../store/dashboardStore';

function safeNum(val: unknown): number | null {
  if (val === null || val === undefined || val === '') return null;
  const n = typeof val === 'number' ? val : Number(val);
  return Number.isFinite(n) ? n : null;
}

export const fmt = {
  // Currency
  usd: (raw: unknown, showSign = false) => {
    const val = safeNum(raw);
    if (val === null) return '—';
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
  pct: (raw: unknown, showSign = false, decimals = 2) => {
    const val = safeNum(raw);
    if (val === null) return '—';
    if (Math.abs(val) < 0.005) return `${(0).toFixed(decimals)}%`;
    const sign = showSign && val > 0 ? '+' : '';
    return `${sign}${val.toFixed(decimals)}%`;
  },

  // Price (auto-decimals based on magnitude)
  price: (raw: unknown, symbol?: string) => {
    const val = safeNum(raw);
    if (val === null) return '—';
    if (symbol?.includes('JPY') || val > 100) return val.toFixed(2);
    if (val > 1) return val.toFixed(4);
    return val.toFixed(5);
  },

  // Large numbers (K, M, B) supporting negative values
  compact: (raw: unknown) => {
    const val = safeNum(raw);
    if (val === null) return '—';
    const absVal = Math.abs(val);
    const sign = val < 0 ? '−' : '';
    if (absVal >= 1_000_000_000) return `${sign}${(absVal / 1_000_000_000).toFixed(1)}B`;
    if (absVal >= 1_000_000) return `${sign}${(absVal / 1_000_000).toFixed(1)}M`;
    if (absVal >= 1_000) return `${sign}${(absVal / 1_000).toFixed(1)}K`;
    return `${sign}${absVal.toFixed(0)}`;
  },

  // Lots
  lots: (raw: unknown) => {
    const val = safeNum(raw);
    if (val === null) return '—';
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
        return `${format(d, 'yyyy-MM-dd HH:mm')} LOC`;
      }
      return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
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

  relativeTime: (iso: string | null | undefined) => {
    if (!iso) return '—';
    try {
      const d = parseISO(iso);
      if (isNaN(d.getTime())) return '—';
      const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
      if (diffSec < 60) return `${diffSec}s ago`;
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
      return `${Math.floor(diffSec / 86400)}d ago`;
    } catch {
      return '—';
    }
  },

  shortDate: (iso: string | null | undefined) => {
    if (!iso) return '—';
    try {
      const d = parseISO(iso);
      if (isNaN(d.getTime())) return '—';
      return format(d, 'MMM dd');
    } catch {
      return '—';
    }
  },

  r: (raw: unknown) => {
    const val = safeNum(raw);
    if (val === null) return '—';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(2)}R`;
  },

  hours: (raw: unknown) => {
    const h = safeNum(raw);
    if (h === null) return '—';
    if (h < 1) return `${Math.round(h * 60)}m`;
    if (h < 24) return `${h.toFixed(1)}h`;
    return `${(h / 24).toFixed(1)}d`;
  },
};

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

export function vixSentiment(vix: number | null | undefined): { label: string; color: string } {
  const v = safeNum(vix);
  if (v === null) return { label: 'Unknown', color: 'var(--color-ink-soft)' };
  if (v < 15) return { label: 'Low', color: 'var(--color-profit)' };
  if (v < 20) return { label: 'Moderate', color: 'var(--color-primary)' };
  if (v < 30) return { label: 'Elevated', color: 'var(--color-warn)' };
  return { label: 'Extreme', color: 'var(--color-loss)' };
}

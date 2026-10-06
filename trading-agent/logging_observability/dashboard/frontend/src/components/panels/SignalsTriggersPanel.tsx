import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { TypewriterButton } from '../ui/TypewriterButton';
import { api } from '../../lib/api';
import type { MT5SignalItem, TradeTriggerItem } from '../../types/api';
import {
  Radio,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  SlidersHorizontal,
  Timer,
} from 'lucide-react';
import { DecisionDossierModal } from './DecisionDossierModal';

const formatLatency = (created?: string | null, executed?: string | null): string => {
  if (!created || !executed) return '—';
  const diff = new Date(executed).getTime() - new Date(created).getTime();
  if (diff < 0) return '—';
  if (diff < 1000) return `${diff}ms`;
  return `${(diff / 1000).toFixed(2)}s`;
};

const formatTimeAgo = (isoString?: string | null): string => {
  if (!isoString) return '—';
  const diffSec = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diffSec < 0) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
};

interface ParsedConditionSummary {
  symbol?: string;
  badgeLabel: string;
  badgeColor: string;
  badgeBg: string;
  badgeBorder: string;
  headline: string;
  subDetail?: string;
  fireAtFormatted?: string;
  rawJson: string;
}

const resolveStrategyName = (rawSlug?: string | null): string => {
  if (!rawSlug) return 'System Default';
  const slug = rawSlug.trim().toLowerCase();
  const knownMap: Record<string, string> = {
    xti_pairs_readiness: 'XTI Pairs Readiness',
    smc_fvg: 'SMC Fair Value Gap',
    tri_convergent_alpha: 'Tri-Convergent Alpha',
    session_breakout: 'Session Breakout',
    macro_trend: 'Macro Trend',
    mean_reversion: 'Mean Reversion',
    momentum: 'Momentum Factor',
  };
  if (knownMap[slug]) return knownMap[slug];

  return slug
    .split('_')
    .map((w) => {
      const up = w.toUpperCase();
      if (['SMC', 'FVG', 'XTI', 'XBR', 'ADR', 'POC', 'SL', 'TP', 'RSI', 'EMA', 'ATR', 'MACD', 'NFP'].includes(up)) {
        return up;
      }
      return w.charAt(0).toUpperCase() + w.slice(1);
    })
    .join(' ');
};

const formatDurationMinutes = (minutes: number): string => {
  if (minutes < 60) return `${minutes}m`;
  const hours = minutes / 60;
  if (hours < 24) {
    const rem = minutes % 60;
    return rem === 0 ? `${hours}h` : `${Math.floor(hours)}h ${rem}m`;
  }
  const days = (minutes / 1440).toFixed(1).replace(/\.0$/, '');
  return `${minutes.toLocaleString()}m (~${days}d)`;
};

const formatUtcSchedule = (isoString?: string | null): string | undefined => {
  if (!isoString) return undefined;
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return undefined;
    const day = String(d.getUTCDate()).padStart(2, '0');
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[d.getUTCMonth()];
    const hours = String(d.getUTCHours()).padStart(2, '0');
    const mins = String(d.getUTCMinutes()).padStart(2, '0');
    return `${day} ${month}, ${hours}:${mins} UTC`;
  } catch {
    return undefined;
  }
};

const parseTriggerCondition = (
  triggerType: string,
  condition: any
): ParsedConditionSummary => {
  const rawJson =
    typeof condition === 'object' && condition !== null
      ? JSON.stringify(condition, null, 2)
      : String(condition || '—');

  let condObj: Record<string, any> = {};
  if (typeof condition === 'object' && condition !== null) {
    condObj = condition;
  } else if (typeof condition === 'string') {
    try {
      condObj = JSON.parse(condition);
    } catch {
      condObj = { detail: condition };
    }
  }

  const type = (triggerType || condObj.type || '').toLowerCase();
  const symbol = condObj.symbol ? String(condObj.symbol).toUpperCase() : undefined;
  const fireAtFormatted = formatUtcSchedule(condObj.fire_at);

  // 1. Force Close / Max Hold Stop
  if (type === 'force_close' || (typeof condObj.reason === 'string' && condObj.reason.includes('max_hold'))) {
    const reasonStr = String(condObj.reason || '');
    const match = reasonStr.match(/^([a-z0-9_]+)\s+max_hold_minutes=(\d+)/i);
    const strategySlug = match ? match[1] : reasonStr.split(' ')[0];
    const holdMins = match ? parseInt(match[2], 10) : undefined;
    const strategyName = resolveStrategyName(strategySlug);
    const holdFormatted = holdMins ? formatDurationMinutes(holdMins) : '';

    return {
      symbol,
      badgeLabel: 'Time Stop',
      badgeColor: '#FAF7F2',
      badgeBg: 'var(--color-win-coral)',
      badgeBorder: 'var(--color-rule)',
      headline: holdFormatted ? `Max Hold Limit Reached (${holdFormatted})` : 'Max Hold Limit Reached',
      subDetail: `↳ Strategy: ${strategyName}${reasonStr.includes('force_session_close=True') ? ' • Session Force Close' : ''}`,
      fireAtFormatted,
      rawJson,
    };
  }

  // 2. Cancel Pending / TTL Expiry
  if (type === 'cancel_pending' || (typeof condObj.reason === 'string' && condObj.reason.includes('ttl_minutes'))) {
    const reasonStr = String(condObj.reason || '');
    const match = reasonStr.match(/^([a-z0-9_]+)\s+ttl_minutes=(\d+)/i);
    const strategySlug = match ? match[1] : reasonStr.split(' ')[0];
    const ttlMins = match ? parseInt(match[2], 10) : undefined;
    const strategyName = resolveStrategyName(strategySlug);
    const ttlFormatted = ttlMins ? formatDurationMinutes(ttlMins) : '';

    return {
      symbol,
      badgeLabel: 'TTL Expired',
      badgeColor: '#1C1917',
      badgeBg: 'var(--color-win-yellow)',
      badgeBorder: 'var(--color-rule)',
      headline: ttlFormatted ? `Order Validity Expired (TTL: ${ttlFormatted})` : 'Order Validity Expired',
      subDetail: `↳ Strategy: ${strategyName}`,
      fireAtFormatted,
      rawJson,
    };
  }

  // 3. Price Level Trigger
  if (type === 'price_level' || (condObj.price !== undefined && condObj.price !== null)) {
    const priceVal = typeof condObj.price === 'number' ? condObj.price : parseFloat(condObj.price);
    const priceStr = !isNaN(priceVal) ? priceVal.toFixed(5).replace(/(\.\d\d\d)0+$/, '$1') : '';
    const dir = (condObj.direction || '').toLowerCase();
    const dirLabel = dir.includes('above') ? 'Crosses Above' : dir.includes('below') ? 'Crosses Below' : 'Reaches';
    const detail = condObj.detail ? String(condObj.detail) : '';

    return {
      symbol,
      badgeLabel: 'Price Level',
      badgeColor: 'cyan',
      badgeBg: 'color-mix(in srgb, var(--color-surface) 70%, cyan)',
      badgeBorder: 'color-mix(in srgb, cyan 40%, var(--color-border))',
      headline: priceStr ? `Price ${dirLabel} ${priceStr}` : 'Price Level Milestone',
      subDetail: detail ? `↳ ${detail}` : undefined,
      fireAtFormatted,
      rawJson,
    };
  }

  // 4. Indicator Trigger
  if (type === 'indicator') {
    const detail = condObj.detail ? String(condObj.detail) : 'Wait for indicator confirmation';
    return {
      symbol,
      badgeLabel: 'Indicator',
      badgeColor: 'var(--color-ink-soft)',
      badgeBg: 'var(--color-paper-raised)',
      badgeBorder: 'var(--color-rule)',
      headline: 'Structural Indicator Signal',
      subDetail: `↳ ${detail}`,
      fireAtFormatted,
      rawJson,
    };
  }

  // 5. Time Trigger
  if (type === 'time') {
    const detail = condObj.detail ? String(condObj.detail) : 'Scheduled re-evaluation';
    return {
      symbol,
      badgeLabel: 'Time Reval',
      badgeColor: '#1C1917',
      badgeBg: 'var(--color-win-yellow)',
      badgeBorder: 'var(--color-rule)',
      headline: 'Scheduled Thesis Re-evaluation',
      subDetail: `↳ ${detail}`,
      fireAtFormatted,
      rawJson,
    };
  }

  // 6. News Trigger
  if (type === 'news') {
    const detail = condObj.detail ? String(condObj.detail) : 'Macro event catalyst';
    return {
      symbol,
      badgeLabel: 'Macro Catalyst',
      badgeColor: '#1C1917',
      badgeBg: 'var(--color-win-green)',
      badgeBorder: 'var(--color-rule)',
      headline: 'Macro Event / News Re-evaluation',
      subDetail: `↳ ${detail}`,
      fireAtFormatted,
      rawJson,
    };
  }

  // Fallback
  const fallbackDetail = condObj.detail || condObj.reason || rawJson;
  return {
    symbol,
    badgeLabel: triggerType || 'Trigger',
    badgeColor: 'var(--color-ink-soft)',
    badgeBg: 'var(--color-paper-raised)',
    badgeBorder: 'var(--color-rule)',
    headline: String(fallbackDetail).slice(0, 50),
    subDetail: String(fallbackDetail).length > 50 ? `↳ ${String(fallbackDetail).slice(50, 120)}...` : undefined,
    fireAtFormatted,
    rawJson,
  };
};

export const SignalsTriggersPanel: React.FC = () => {
  const [panelTab, setPanelTab] = useState<'signals' | 'orders'>('signals');
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [signals, setSignals] = useState<MT5SignalItem[]>([]);
  const [triggers, setTriggers] = useState<TradeTriggerItem[]>([]);
  const [orders, setOrders] = useState<import('../../types/api').OrderLogItem[]>([]);
  const [signalsMeta, setSignalsMeta] = useState<{ total: number; executed: number }>({ total: 0, executed: 0 });
  const [triggersMeta, setTriggersMeta] = useState<{ total: number; fired: number; pending: number }>({ total: 0, fired: 0, pending: 0 });
  const [triggerStatusFilter, setTriggerStatusFilter] = useState<string>('all');
  const [signalStatusFilter, setSignalStatusFilter] = useState<string>('all');
  const [orderActionFilter, setOrderActionFilter] = useState<string>('all');
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [approveMsg, setApproveMsg] = useState<string | null>(null);
  const [dossierTarget, setDossierTarget] = useState<{ id?: number | string; symbol?: string; ticket?: number } | null>(null);

  const handleApproveTrigger = async (id: number) => {
    setApprovingId(id);
    setApproveMsg(null);
    try {
      await api.approveTrade(id);
      setApproveMsg(`Trigger #${id} approved successfully for MT5 order execution.`);
      await fetchData(true);
    } catch (err: any) {
      setApproveMsg(`Failed to approve trigger #${id}: ${err.message}`);
    } finally {
      setApprovingId(null);
    }
  };

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const [signalsRes, triggersRes, ordersRes] = await Promise.allSettled([
        api.mt5Signals(100),
        api.triggers(undefined, 100),
        api.orders(100),
      ]);

      if (signalsRes.status === 'fulfilled') {
        setSignals(signalsRes.value.items || []);
        const val = signalsRes.value as any;
        setSignalsMeta({
          total: val.total || (signalsRes.value.items || []).length,
          executed: val.executed_count || val.total || (signalsRes.value.items || []).filter((s: any) => s.status?.toLowerCase() === 'executed').length,
        });
      }
      if (triggersRes.status === 'fulfilled') {
        setTriggers(triggersRes.value.items || []);
        const val = triggersRes.value as any;
        setTriggersMeta({
          total: val.total || (triggersRes.value.items || []).length,
          fired: val.fired_count || (triggersRes.value.items || []).filter((t: any) => t.status?.toLowerCase() === 'fired').length,
          pending: val.pending_count || (triggersRes.value.items || []).filter((t: any) => t.status?.toLowerCase() === 'pending').length,
        });
      }
      if (ordersRes.status === 'fulfilled') {
        setOrders(ordersRes.value || []);
      }
    } catch (err) {
      console.error('Failed to load signals & triggers data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Derived stats
  const totalSignals = signalsMeta.total || signals.length;
  const executedSignals = signalsMeta.executed || signals.filter((s) => s.status?.toLowerCase() === 'executed').length;
  const fillRatePct = totalSignals > 0 ? ((executedSignals / totalSignals) * 100).toFixed(1) : '100.0';

  const pendingTriggers = triggersMeta.pending || triggers.filter((t) => t.status?.toLowerCase() === 'pending').length;
  const firedTriggers = triggersMeta.fired || triggers.filter((t) => t.status?.toLowerCase() === 'fired').length;

  // Average execution latency for executed signals
  const avgLatencyText = useMemo(() => {
    const latencies: number[] = [];
    for (const s of signals) {
      if (s.status?.toLowerCase() === 'executed' && s.created_at && s.executed_at) {
        const diff = new Date(s.executed_at).getTime() - new Date(s.created_at).getTime();
        if (diff >= 0 && diff < 300_000) {
          latencies.push(diff);
        }
      }
    }
    if (latencies.length === 0) return '—';
    const avg = latencies.reduce((a, b) => a + b, 0) / latencies.length;
    return avg < 1000 ? `${Math.round(avg)} ms` : `${(avg / 1000).toFixed(2)} s`;
  }, [signals]);

  const filteredTriggers = triggers.filter((t) => {
    if (triggerStatusFilter === 'all') return true;
    return t.status?.toLowerCase() === triggerStatusFilter.toLowerCase();
  });

  const filteredSignals = signals.filter((s) => {
    if (signalStatusFilter === 'all') return true;
    const st = s.status?.toLowerCase();
    if (signalStatusFilter === 'failed' || signalStatusFilter === 'rejected') {
      return st === 'failed' || st === 'rejected';
    }
    return st === signalStatusFilter.toLowerCase();
  });

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}><Skeleton height="90px" /></Card>
          ))}
        </div>
        <Card><Skeleton height="320px" /></Card>
        <Card><Skeleton height="320px" /></Card>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '2px',
              border: '1px solid var(--color-border)',
              background: 'var(--color-surface-card)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--color-ink)',
            }}
          >
            <Radio size={18} />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              MT5 Signals & Conditional Triggers
            </h2>
            <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '2px', fontFamily: 'var(--font-precision)' }}>
              Telegraph execution routing, fill rates, latency metrics, and real-time triggers
            </div>
          </div>
        </div>

        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="typewriter-btn"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 14px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: '2px',
            color: 'var(--color-ink)',
            fontSize: '11px',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            cursor: refreshing ? 'not-allowed' : 'pointer',
            fontFamily: 'var(--font-precision)',
          }}
        >
          <RefreshCw size={12} className={refreshing ? 'spin-anim' : ''} />
          {refreshing ? 'REFRESHING...' : 'REFRESH'}
        </button>
      </div>

      {/* Sub-tab Navigation */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '2px solid var(--color-rule)', paddingBottom: '8px' }}>
        <TypewriterButton
          size="sm"
          variant={panelTab === 'signals' ? 'primary' : 'secondary'}
          onClick={() => setPanelTab('signals')}
        >
          <Radio size={12} /> [ SIGNALS & TRIGGERS ({signals.length + triggers.length}) ]
        </TypewriterButton>
        <TypewriterButton
          size="sm"
          variant={panelTab === 'orders' ? 'primary' : 'secondary'}
          onClick={() => setPanelTab('orders')}
        >
          <CheckCircle2 size={12} /> [ ORDER AUDIT TRAIL ({orders.length}) ]
        </TypewriterButton>
      </div>

      {panelTab === 'orders' ? (
        /* Orders Audit Trail Card */
        <Card
          header={
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>[ ORDER LOG AUDIT TRAIL ({orders.length}) ]</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>ACTION:</span>
                <select
                  value={orderActionFilter}
                  onChange={(e) => setOrderActionFilter(e.target.value)}
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink)',
                    padding: '2px 8px',
                    fontSize: '11px',
                    borderRadius: '2px',
                  }}
                >
                  <option value="all">All Actions</option>
                  <option value="place">Place</option>
                  <option value="modify">Modify</option>
                  <option value="close">Close</option>
                </select>
              </div>
            </div>
          }
        >
          <div style={{ overflowX: 'auto', maxHeight: '520px', overflowY: 'auto' }}>
            <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                  <th>ID</th>
                  <th>ACTION</th>
                  <th>SYMBOL</th>
                  <th>REQUESTED / APPROVED</th>
                  <th>PARAMS</th>
                  <th>RESULT</th>
                  <th style={{ textAlign: 'right' }}>TIMESTAMP</th>
                </tr>
              </thead>
              <tbody>
                {orders
                  .filter((o) => orderActionFilter === 'all' || o.action?.toLowerCase() === orderActionFilter.toLowerCase())
                  .map((o) => (
                    <tr key={o.id} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                      <td style={{ color: 'var(--color-ink-muted)' }}>#{o.id}</td>
                      <td>
                        <Badge variant={o.action === 'place' ? 'active' : o.action === 'close' ? 'warn' : 'neutral'}>
                          {o.action?.toUpperCase() ?? 'N/A'}
                        </Badge>
                      </td>
                      <td style={{ fontWeight: 700 }}>{o.symbol}</td>
                      <td style={{ fontSize: '11px' }}>
                        <div>By: {o.requested_by || 'system'}</div>
                        {o.approved_by && <div style={{ color: 'var(--color-brass)' }}>Appr: {o.approved_by}</div>}
                      </td>
                      <td style={{ maxWidth: '200px', fontSize: '11px', fontFamily: 'monospace' }}>
                        {typeof o.params === 'object' ? JSON.stringify(o.params) : String(o.params || '—')}
                      </td>
                      <td style={{ maxWidth: '240px', fontSize: '11px', fontFamily: 'monospace' }}>
                        {typeof o.result === 'object' ? JSON.stringify(o.result) : String(o.result || '—')}
                      </td>
                      <td style={{ textAlign: 'right', fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        {o.timestamp ? new Date(o.timestamp).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <>
        {/* KPI Cards */}
        <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Signal Fill Rate
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: Number(fillRatePct) >= 80 ? 'var(--color-profit)' : 'var(--color-warning)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {fillRatePct}%
              </div>
            </div>
            <div style={{ color: 'var(--color-profit)' }}>
              <CheckCircle2 size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            {executedSignals} of {totalSignals} signals filled in MT5
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Avg Fill Latency
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {avgLatencyText}
              </div>
            </div>
            <div style={{ color: 'var(--color-brass)' }}>
              <Timer size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Time from signal creation to broker execution
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Active Pending Triggers
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-warning)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {pendingTriggers}
              </div>
            </div>
            <div style={{ color: 'var(--color-warning)' }}>
              <Clock size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Awaiting conditional price or macro triggers
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Fired Triggers
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-profit)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {firedTriggers}
              </div>
            </div>
            <div style={{ color: 'var(--color-profit)' }}>
              <Zap size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Successfully converted to execution
          </div>
        </Card>
      </div>

      {/* Conditional Trade Triggers Section */}
      <Card
        className="ledger-card"
        header={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={16} color="var(--color-brass)" />
              <span style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '12px' }}>Conditional Trade Triggers</span>
              <Badge variant="neutral">{filteredTriggers.length} items</Badge>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <SlidersHorizontal size={13} color="var(--color-ink-muted)" />
              <select
                value={triggerStatusFilter}
                onChange={(e) => setTriggerStatusFilter(e.target.value)}
                style={{
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  height: '26px',
                  boxSizing: 'border-box',
                  padding: '0 8px',
                  fontSize: '11px',
                  outline: 'none',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-precision)',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                <option value="all">All Triggers</option>
                <option value="pending">Pending Only</option>
                <option value="fired">Fired Only</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>
        }
      >
        {approveMsg && (
          <div
            style={{
              padding: '8px 14px',
              background: 'var(--color-paper)',
              borderBottom: '1.5px solid var(--color-rule)',
              fontSize: '11px',
              color: 'var(--color-ink)',
              fontFamily: 'var(--font-precision)',
            }}
          >
            ℹ {approveMsg}
          </div>
        )}
        <div style={{ overflowX: 'auto' }}>
          <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr>
                <th>ID / Type</th>
                <th>Analysis ID</th>
                <th>Condition Summary</th>
                <th>Created / Age</th>
                <th>Fired At</th>
                <th style={{ textAlign: 'right' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredTriggers.length > 0 ? (
                filteredTriggers.map((t) => {
                  const condSummary = parseTriggerCondition(t.trigger_type, t.condition);
                  const statusLower = t.status?.toLowerCase();
                  const isPending = statusLower === 'pending';

                  return (
                    <tr key={t.id}>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--color-ink)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {isPending && (
                            <span
                              style={{
                                width: '6px',
                                height: '6px',
                                borderRadius: '1px',
                                background: 'var(--color-warning)',
                                display: 'inline-block',
                              }}
                            />
                          )}
                          #{t.id} • {t.trigger_type}
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>{t.asset_analysis_id ? `#${t.asset_analysis_id}` : '—'}</span>
                          {t.asset_analysis_id ? (
                            <button
                              type="button"
                              onClick={() => setDossierTarget({ id: t.asset_analysis_id ?? undefined })}
                              style={{
                                padding: '1px 5px',
                                fontSize: '10px',
                                fontFamily: 'var(--font-precision)',
                                fontWeight: 'bold',
                                background: 'color-mix(in srgb, var(--color-surface) 70%, cyan)',
                                color: 'cyan',
                                border: '1px solid color-mix(in srgb, cyan 40%, var(--color-border))',
                                borderRadius: '2px',
                                cursor: 'pointer',
                              }}
                              title="Inspect Decision Dossier"
                            >
                              🔍 DOSSIER
                            </button>
                          ) : null}
                        </div>
                      </td>
                      <td style={{ maxWidth: '420px', minWidth: '240px' }}>
                        <div
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '3px',
                            cursor: 'help',
                          }}
                          title={condSummary.rawJson}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'nowrap' }}>
                            {condSummary.symbol && (
                              <span
                                style={{
                                  fontSize: '10px',
                                  fontFamily: 'var(--font-precision)',
                                  fontWeight: 'bold',
                                  padding: '1px 5px',
                                  borderRadius: '2px',
                                  background: 'var(--color-paper-raised)',
                                  color: 'var(--color-ink)',
                                  border: '1px solid var(--color-rule)',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {condSummary.symbol}
                              </span>
                            )}
                            <span
                              style={{
                                fontSize: '9px',
                                fontFamily: 'var(--font-precision)',
                                fontWeight: 'bold',
                                letterSpacing: '0.04em',
                                textTransform: 'uppercase',
                                padding: '1px 5px',
                                borderRadius: '2px',
                                background: condSummary.badgeBg,
                                color: condSummary.badgeColor,
                                border: `1px solid ${condSummary.badgeBorder}`,
                                whiteSpace: 'nowrap',
                                lineHeight: '1.2',
                              }}
                            >
                              {condSummary.badgeLabel}
                            </span>
                            <span
                              style={{
                                fontSize: '11px',
                                fontWeight: 600,
                                color: 'var(--color-ink)',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              {condSummary.headline}
                            </span>
                          </div>

                          {condSummary.subDetail && (
                            <div
                              style={{
                                fontSize: '10px',
                                color: 'var(--color-ink-muted)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {condSummary.subDetail}
                              </span>
                              {condSummary.fireAtFormatted && (
                                <span style={{ color: 'var(--color-warning)', fontWeight: 500, flexShrink: 0 }}>
                                  • Fires: {condSummary.fireAtFormatted}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)', fontSize: '11px' }}>
                        <div>{t.created_at ? new Date(t.created_at).toLocaleString() : '—'}</div>
                        <div style={{ fontSize: '10px', color: isPending ? 'var(--color-warning)' : 'var(--color-ink-muted)', marginTop: '2px' }}>
                          {formatTimeAgo(t.created_at)}
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)', fontSize: '11px' }}>
                        {t.fired_at ? new Date(t.fired_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', justifyContent: 'flex-end' }}>
                          <Badge
                            variant={
                              statusLower === 'fired'
                                ? 'profit'
                                : statusLower === 'pending'
                                  ? 'warn'
                                  : 'neutral'
                            }
                          >
                            {t.status}
                          </Badge>
                          {isPending && (
                            <button
                              type="button"
                              disabled={approvingId === t.id}
                              onClick={() => handleApproveTrigger(t.id)}
                              style={{
                                padding: '2px 8px',
                                fontSize: '11px',
                                fontFamily: 'var(--font-precision)',
                                fontWeight: 'bold',
                                background: 'var(--color-profit-dim, rgba(22, 163, 74, 0.15))',
                                color: 'var(--color-ledger-green, #16a34a)',
                                border: '1px solid var(--color-ledger-green, #16a34a)',
                                borderRadius: '2px',
                                cursor: approvingId === t.id ? 'wait' : 'pointer',
                              }}
                              title="Approve this pending trigger for execution in MT5"
                            >
                              {approvingId === t.id ? '...' : 'APPROVE'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: 'var(--color-ink-muted)' }}>
                    No triggers found matching criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* MT5 Signals History Section */}
      <Card
        className="ledger-card"
        header={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Radio size={16} color="var(--color-brass)" />
              <span style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '12px' }}>MT5 Broker Signals & Execution History</span>
              <Badge variant="neutral">{filteredSignals.length} signals</Badge>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <SlidersHorizontal size={13} color="var(--color-ink-muted)" />
              <select
                value={signalStatusFilter}
                onChange={(e) => setSignalStatusFilter(e.target.value)}
                style={{
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  height: '26px',
                  boxSizing: 'border-box',
                  padding: '0 8px',
                  fontSize: '11px',
                  outline: 'none',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-precision)',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                <option value="all">All Statuses</option>
                <option value="executed">Executed</option>
                <option value="pending">Pending</option>
                <option value="failed">Failed / Rejected</option>
              </select>
            </div>
          </div>
        }
      >
        <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
          <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                <th>Signal ID</th>
                <th>Symbol / Action</th>
                <th>MT5 Ticket</th>
                <th>Created</th>
                <th>Executed</th>
                <th>Fill Latency</th>
                <th>Notes / Error</th>
                <th style={{ textAlign: 'right' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSignals.length > 0 ? (
                filteredSignals.map((s) => {
                  const isBuy = s.action?.toLowerCase() === 'buy';
                  const statusLower = s.status?.toLowerCase();
                  const latency = formatLatency(s.created_at, s.executed_at);

                  return (
                    <tr key={s.id}>
                      <td style={{ color: 'var(--color-ink-muted)' }}>
                        #{s.id}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 700, color: 'var(--color-ink)' }}>{s.symbol}</span>
                          <Badge variant={isBuy ? 'buy' : 'sell'} size="sm">
                            {isBuy ? <ArrowUpRight size={10} style={{ marginRight: 2 }} /> : <ArrowDownRight size={10} style={{ marginRight: 2 }} />}
                            {s.action?.toUpperCase() ?? 'N/A'}
                          </Badge>
                          <button
                            type="button"
                            onClick={() => setDossierTarget({ id: (s as any).asset_analysis_id || undefined, symbol: s.symbol, ticket: s.mt5_ticket || undefined })}
                            style={{
                              padding: '1px 5px',
                              fontSize: '10px',
                              fontFamily: 'var(--font-precision)',
                              fontWeight: 'bold',
                              background: 'color-mix(in srgb, var(--color-surface) 70%, cyan)',
                              color: 'cyan',
                              border: '1px solid color-mix(in srgb, cyan 40%, var(--color-border))',
                              borderRadius: '2px',
                              cursor: 'pointer',
                              marginLeft: '2px',
                            }}
                            title="Inspect Decision Dossier for this signal"
                          >
                            🔍 DOSSIER
                          </button>
                        </div>
                      </td>
                      <td>
                        {s.mt5_ticket ? (
                          <span style={{ color: 'var(--color-brass)', fontWeight: 600 }}>#{s.mt5_ticket}</span>
                        ) : (
                          <span style={{ color: 'var(--color-ink-muted)' }}>—</span>
                        )}
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)', fontSize: '11px' }}>
                        {s.created_at ? new Date(s.created_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)', fontSize: '11px' }}>
                        {s.executed_at ? new Date(s.executed_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ fontSize: '11px', color: latency !== '—' ? 'var(--color-ink)' : 'var(--color-ink-muted)' }}>
                        {latency}
                      </td>
                      <td style={{ maxWidth: '240px' }}>
                        {s.error_message ? (
                          <div style={{ color: 'var(--color-loss)', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <AlertTriangle size={12} />
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {s.error_message}
                            </span>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--color-ink-muted)', fontSize: '11px' }}>—</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Badge
                          variant={
                            statusLower === 'executed'
                              ? 'profit'
                              : statusLower === 'pending'
                                ? 'warn'
                                : 'loss'
                          }
                        >
                          {s.status}
                        </Badge>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} style={{ padding: '24px', textAlign: 'center', color: 'var(--color-ink-muted)' }}>
                    No signals found matching criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
      </>
      )}

      {/* Decision Dossier Modal */}
      <DecisionDossierModal
        isOpen={Boolean(dossierTarget)}
        onClose={() => setDossierTarget(null)}
        analysisId={dossierTarget?.id}
        symbol={dossierTarget?.symbol}
        ticket={dossierTarget?.ticket}
      />
    </div>
  );
};

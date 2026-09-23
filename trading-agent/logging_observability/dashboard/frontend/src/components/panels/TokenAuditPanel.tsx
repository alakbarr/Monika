import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { api } from '../../lib/api';
import type {
  TokenSummary,
  TokenRoleItem,
  TokenSubsystemItem,
  TokenSymbolItem,
  TokenRecentLog,
} from '../../types/api';
import {
  Layers,
  DollarSign,
  Zap,
  Clock,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  History,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { TokenCharts } from './tokens/TokenCharts';
import { TokenRoleTable } from './tokens/TokenRoleTable';

export const TokenAuditPanel: React.FC = () => {
  const [hours, setHours] = useState<number>(24);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [summary, setSummary] = useState<TokenSummary | null>(null);
  const [roles, setRoles] = useState<TokenRoleItem[]>([]);
  const [subsystems, setSubsystems] = useState<TokenSubsystemItem[]>([]);
  const [symbols, setSymbols] = useState<TokenSymbolItem[]>([]);
  const [recentLogs, setRecentLogs] = useState<TokenRecentLog[]>([]);
  const [contextTracker, setContextTracker] = useState<Record<string, any> | null>(null);
  const [turnCost, setTurnCost] = useState<import('../../types/api').TokenTurnCostMetrics | null>(null);
  const [roleSearch, setRoleSearch] = useState<string>('');
  const [subsystemFilter, setSubsystemFilter] = useState<string>('all');

  // Sorting state for Symbols table
  const [symSortKey, setSymSortKey] = useState<keyof TokenSymbolItem>('sum_cost_usd');
  const [symSortAsc, setSymSortAsc] = useState<boolean>(false);

  // Sorting state for Roles table
  const [roleSortKey, setRoleSortKey] = useState<keyof TokenRoleItem>('sum_total');
  const [roleSortAsc, setRoleSortAsc] = useState<boolean>(false);

  const budgetTier = useMemo<'NORMAL' | 'COMPRESSED' | 'DEGRADED'>(() => {
    const util = contextTracker?.utilization_pct || 0;
    const errors = summary?.error_count || 0;
    if (util > 80 || errors > 5) return 'DEGRADED';
    if (util > 60 || (summary?.cache_hit_rate_pct || 100) < 40) return 'COMPRESSED';
    return 'NORMAL';
  }, [contextTracker, summary]);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const [sumRes, rolesRes, subsRes, symsRes, logsRes, ctxRes, turnRes] = await Promise.allSettled([
        api.tokensSummary(hours),
        api.tokensRoles(hours),
        api.tokensSubsystems(hours),
        api.tokensSymbols(hours),
        api.tokensRecent(50),
        api.tokenContextTracker(),
        api.tokenPerTurnCost(hours),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value);
      if (rolesRes.status === 'fulfilled') setRoles(rolesRes.value.items || []);
      if (subsRes.status === 'fulfilled') setSubsystems(subsRes.value.items || []);
      if (symsRes.status === 'fulfilled') setSymbols(symsRes.value.items || []);
      if (logsRes.status === 'fulfilled') setRecentLogs(logsRes.value.items || []);
      if (ctxRes.status === 'fulfilled') setContextTracker(ctxRes.value);
      if (turnRes.status === 'fulfilled') setTurnCost(turnRes.value);
    } catch (err) {
      console.error('Failed to load token audit data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggleSymSort = (key: keyof TokenSymbolItem) => {
    if (symSortKey === key) {
      setSymSortAsc((prev) => !prev);
    } else {
      setSymSortKey(key);
      setSymSortAsc(false);
    }
  };

  const toggleRoleSort = (key: keyof TokenRoleItem) => {
    if (roleSortKey === key) {
      setRoleSortAsc((prev) => !prev);
    } else {
      setRoleSortKey(key);
      setRoleSortAsc(false);
    }
  };

  const maxRoleTokens = useMemo(() => {
    return Math.max(...roles.map((r) => r.sum_total), 1);
  }, [roles]);

  const maxSymTokens = useMemo(() => {
    return Math.max(...symbols.map((s) => s.sum_total), 1);
  }, [symbols]);

  const availableSubsystems = useMemo(() => {
    const subs = new Set(roles.map((r) => r.subsystem));
    return Array.from(subs).sort();
  }, [roles]);

  const filteredAndSortedRoles = useMemo(() => {
    return roles
      .filter((r) => {
        const matchesSub = subsystemFilter === 'all' || r.subsystem === subsystemFilter;
        const matchesSearch =
          !roleSearch ||
          r.task_role.toLowerCase().includes(roleSearch.toLowerCase()) ||
          r.subsystem.toLowerCase().includes(roleSearch.toLowerCase());
        return matchesSub && matchesSearch;
      })
      .sort((a, b) => {
        const vA = a[roleSortKey];
        const vB = b[roleSortKey];
        if (typeof vA === 'string' && typeof vB === 'string') {
          return roleSortAsc ? vA.localeCompare(vB) : vB.localeCompare(vA);
        }
        return roleSortAsc ? Number(vA) - Number(vB) : Number(vB) - Number(vA);
      });
  }, [roles, subsystemFilter, roleSearch, roleSortKey, roleSortAsc]);

  const sortedSymbols = useMemo(() => {
    return [...symbols].sort((a, b) => {
      const vA = a[symSortKey];
      const vB = b[symSortKey];
      if (typeof vA === 'string' && typeof vB === 'string') {
        return symSortAsc ? vA.localeCompare(vB) : vB.localeCompare(vA);
      }
      return symSortAsc ? Number(vA) - Number(vB) : Number(vB) - Number(vA);
    });
  }, [symbols, symSortKey, symSortAsc]);

  const renderSortIcon = (current: string, key: string, asc: boolean) => {
    if (current !== key) return <ArrowUpDown size={11} style={{ opacity: 0.3, marginLeft: 4 }} />;
    return asc ? (
      <ArrowUp size={11} style={{ marginLeft: 4, color: 'var(--color-brass)' }} />
    ) : (
      <ArrowDown size={11} style={{ marginLeft: 4, color: 'var(--color-brass)' }} />
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <Skeleton height={100} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <Skeleton height={90} />
          <Skeleton height={90} />
          <Skeleton height={90} />
          <Skeleton height={90} />
        </div>
        <Skeleton height={300} />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header & Filter Bar */}
      <div
        className="ledger-card"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 20px',
          background: 'var(--color-surface-card)',
          borderRadius: '2px',
          border: '1px solid var(--color-border)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Token Consumption & Cost Ledger
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--color-ink-muted)', margin: '4px 0 0 0', fontFamily: 'var(--font-precision)' }}>
            Granular per-role audit tracking across 30+ agent tasks, prompt cache savings, and estimated USD expenditure.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Time range selector */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            height: '28px',
            boxSizing: 'border-box',
            background: 'var(--color-surface)',
            padding: '2px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--color-rule)',
          }}>
            {[
              { label: '6H', val: 6 },
              { label: '24H', val: 24 },
              { label: '7D', val: 168 },
              { label: '30D', val: 720 },
            ].map((t) => (
              <button
                key={t.val}
                onClick={() => setHours(t.val)}
                className="typewriter-btn"
                style={{
                  height: '100%',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 10px',
                  background: hours === t.val ? 'var(--color-brass)' : 'transparent',
                  color: hours === t.val ? 'var(--color-paper-dark)' : 'var(--color-ink)',
                  border: 'none',
                  borderRadius: '1px',
                  fontSize: '11px',
                  fontWeight: hours === t.val ? 700 : 500,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-precision)',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="typewriter-btn"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              height: '28px',
              boxSizing: 'border-box',
              padding: '0 12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-ink)',
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              cursor: refreshing ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'REFRESHING...' : 'REFRESH'}
          </button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Est. Total Cost ({hours}h)
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-brass)', marginTop: '4px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>
                ${(summary?.total_cost_usd || 0).toFixed(4)}
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-brass)' }}>
              <DollarSign size={18} />
            </div>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            {summary?.total_calls?.toLocaleString() || 0} total LLM calls
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Prompt Cache Hit Rate
              </div>
              <div
                style={{
                  fontSize: '24px',
                  fontWeight: 700,
                  color: (summary?.cache_hit_rate_pct || 0) >= 70 ? 'var(--color-profit)' : 'var(--color-brass)',
                  marginTop: '4px',
                  fontFamily: 'var(--font-precision)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {(summary?.cache_hit_rate_pct || 0).toFixed(1)}%
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-profit)' }}>
              <Zap size={18} />
            </div>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            {(summary?.cached_tokens || 0).toLocaleString()} cached tokens
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Total Tokens ({hours}h)
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '4px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>
                {(summary?.total_tokens || 0).toLocaleString()}
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink-muted)' }}>
              <Layers size={18} />
            </div>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Thinking: {(summary?.thinking_tokens || 0).toLocaleString()} ({(summary?.thinking_pct_of_output || 0).toFixed(1)}% output)
          </div>
        </Card>

        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Avg Latency & Health
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '4px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>
                {(summary?.avg_latency_ms || 0).toFixed(0)} ms
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-brass)' }}>
              <Clock size={18} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', fontSize: '12px', marginTop: '8px', alignItems: 'center', fontFamily: 'var(--font-precision)' }}>
            <span style={{ color: 'var(--color-profit)' }}>✓ {summary?.success_count || 0}</span>
            <span style={{ color: 'var(--color-brass)' }}>⤾ {summary?.fallback_count || 0} fb</span>
            {(summary?.error_count || 0) > 0 && (
              <span style={{ color: 'var(--color-loss)' }}>✗ {summary?.error_count} err</span>
            )}
          </div>
        </Card>

        {/* Context Headroom Gauge Card */}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Context Window Headroom
              </div>
              <div
                style={{
                  fontSize: '24px',
                  fontWeight: 700,
                  color: (contextTracker?.utilization_pct || 0) > 80 ? 'var(--color-loss)' : 'var(--color-profit)',
                  marginTop: '4px',
                  fontFamily: 'var(--font-precision)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {contextTracker?.utilization_pct !== undefined ? `${contextTracker.utilization_pct}%` : '—'}
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-profit)' }}>
              <Layers size={18} />
            </div>
          </div>
          <div style={{ marginTop: '8px' }}>
            <div style={{ height: '6px', width: '100%', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, contextTracker?.utilization_pct || 0)}%`,
                  height: '100%',
                  background: (contextTracker?.utilization_pct || 0) > 80 ? 'var(--color-loss)' : 'var(--color-profit)',
                }}
              />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
              {contextTracker?.used_tokens?.toLocaleString() || 0} / {contextTracker?.max_context_window?.toLocaleString() || 200000} tok ({contextTracker?.model || 'active'})
            </div>
          </div>
        </Card>

        {/* Avg Turn Cost Stat Card */}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                Avg Turn Cost ({hours}h)
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '4px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>
                ${(turnCost?.avg_cost_per_turn_usd || 0).toFixed(4)}
              </div>
            </div>
            <div style={{ padding: '6px', borderRadius: '2px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-brass)' }}>
              <DollarSign size={18} />
            </div>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            {turnCost?.total_turns?.toLocaleString() || 0} turns across {turnCost?.cycle_count || 0} cycles
          </div>
        </Card>
      </div>

      {/* Subsystem Budget Quotas & Degradation Tier */}
      <div
        className="ledger-card"
        style={{
          padding: '16px 20px',
          background: 'var(--color-surface-card)',
          borderRadius: '2px',
          border: '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 'bold', textTransform: 'uppercase', fontFamily: 'var(--font-precision)' }}>
              Subsystem Quota Budgets & Dynamic Degradation
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '2px' }}>
              Enforced token allocation thresholds across agent execution stages.
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-muted)' }}>DEGRADATION TIER:</span>
            <Badge variant={budgetTier === 'NORMAL' ? 'profit' : budgetTier === 'COMPRESSED' ? 'warn' : 'loss'}>
              {budgetTier}
            </Badge>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
          {[
            { name: 'Stage 1 Macro', targetPct: 20, key: 'stage1' },
            { name: 'Stage 2 Asset Analysis', targetPct: 45, key: 'stage2' },
            { name: 'Debate Arbitration', targetPct: 15, key: 'debate' },
            { name: 'Schedulers & Guardians', targetPct: 10, key: 'scheduler' },
            { name: 'Reserve / Buffer', targetPct: 10, key: 'reserve' },
          ].map((quota) => {
            const subMatch = subsystems.find((s) => s.subsystem.toLowerCase().includes(quota.key));
            const actualPct = subMatch ? subMatch.pct_tokens : 0;
            const isOver = actualPct > quota.targetPct;
            return (
              <div
                key={quota.key}
                style={{
                  padding: '10px 12px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 'bold' }}>
                  <span>{quota.name}</span>
                  <span style={{ color: isOver ? 'var(--color-loss)' : 'var(--color-profit)' }}>
                    {actualPct}% / {quota.targetPct}%
                  </span>
                </div>
                <div
                  style={{
                    height: '5px',
                    width: '100%',
                    background: 'var(--color-paper-dark)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                    marginTop: '8px',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(100, (actualPct / quota.targetPct) * 100)}%`,
                      background: isOver ? 'var(--color-loss)' : 'var(--color-brass)',
                    }}
                  />
                </div>
                <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', marginTop: '4px' }}>
                  {isOver ? `⚠ Exceeds budget by +${(actualPct - quota.targetPct).toFixed(1)}%` : `✓ Within ${quota.targetPct}% quota limit`}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Subsystem & Symbol Attribution */}
      <TokenCharts
        subsystems={subsystems}
        sortedSymbols={sortedSymbols}
        maxSymTokens={maxSymTokens}
        symSortKey={symSortKey}
        symSortAsc={symSortAsc}
        toggleSymSort={toggleSymSort}
        renderSortIcon={renderSortIcon}
      />

      {/* Task Roles Breakdown (Sortable & Visual Horizontal Bar) */}
      <TokenRoleTable
        filteredAndSortedRoles={filteredAndSortedRoles}
        maxRoleTokens={maxRoleTokens}
        roleSortKey={roleSortKey}
        roleSortAsc={roleSortAsc}
        toggleRoleSort={toggleRoleSort}
        roleSearch={roleSearch}
        setRoleSearch={setRoleSearch}
        subsystemFilter={subsystemFilter}
        setSubsystemFilter={setSubsystemFilter}
        availableSubsystems={availableSubsystems}
        renderSortIcon={renderSortIcon}
      />

      {/* Recent Token Events Timeline Feed */}
      <Card
        className="ledger-card"
        header={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <History size={16} color="var(--color-ink)" />
            <span style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '12px' }}>Recent Token Audit Stream</span>
            <Badge variant="neutral">{recentLogs.length} events</Badge>
          </div>
        }
      >
        <div style={{ overflowX: 'auto', maxHeight: '420px', overflowY: 'auto' }}>
          <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                <th>Time</th>
                <th>Role / Model</th>
                <th>Symbol</th>
                <th>Tokens (In / Out / Cache)</th>
                <th>Latency</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Cost</th>
              </tr>
            </thead>
            <tbody>
              {recentLogs.length > 0 ? (
                recentLogs.map((log) => (
                  <tr key={log.id}>
                    <td style={{ color: 'var(--color-ink-muted)', whiteSpace: 'nowrap' }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '—'}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--color-ink)' }}>
                        {log.task_role || log.task_name || 'unknown'}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)' }}>
                        {log.provider} • {log.model_name}
                      </div>
                    </td>
                    <td style={{ color: 'var(--color-ink)', fontWeight: 600 }}>
                      {log.symbol || '—'}
                    </td>
                    <td>
                      <span>{log.input_tokens.toLocaleString()}</span> /{' '}
                      <span style={{ color: 'var(--color-ink)' }}>{log.output_tokens.toLocaleString()}</span>
                      {log.cached_tokens > 0 && (
                        <span style={{ color: 'var(--color-profit)', marginLeft: '4px' }}>
                          (⚡{log.cached_tokens.toLocaleString()})
                        </span>
                      )}
                    </td>
                    <td style={{ color: 'var(--color-ink-muted)' }}>
                      {(log.execution_time_ms ?? 0).toFixed(0)} ms
                    </td>
                    <td>
                      {log.status === 'success' ? (
                        <Badge variant="profit" size="sm">
                          <CheckCircle2 size={10} style={{ marginRight: 3 }} /> OK
                        </Badge>
                      ) : (
                        <Badge variant="loss" size="sm">
                          <AlertTriangle size={10} style={{ marginRight: 3 }} /> {log.status || 'OK'}
                        </Badge>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--color-brass)', fontWeight: 600 }}>
                      ${(log.cost_estimate ?? 0).toFixed(5)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: 'var(--color-ink-muted)' }}>
                    No recent token events found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

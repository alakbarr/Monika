import React, { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { BookOpen, Zap, Clock, ChevronRight, GitBranch } from 'lucide-react';
import { api } from '../../lib/api';

interface PlaybookNode {
  name: string;
  type?: string;
  status?: string;
  rule_text?: string;
  win_rate?: number;
  times_triggered?: number;
  children?: PlaybookNode[];
}

interface PromptCacheCycle {
  cycle_id: string;
  hit_rate_pct: number;
  cached_tokens: number;
  input_tokens: number;
  cache_creation_tokens: number;
  output_tokens: number;
}

interface PromptCacheData {
  overall_hit_rate_pct: number;
  total_cached_tokens: number;
  total_input_tokens: number;
  total_cache_creation_tokens: number;
  cycles: PromptCacheCycle[];
}

interface ToolStat {
  tool_name: string;
  call_count: number;
  avg_ms: number;
  p50_ms: number;
  p90_ms: number;
  p99_ms: number;
  buckets: Record<string, number>;
}

export const ObservabilityPanel: React.FC = () => {
  const [playbookTree, setPlaybookTree] = useState<PlaybookNode | null>(null);
  const [cacheMetrics, setCacheMetrics] = useState<PromptCacheData | null>(null);
  const [toolLatencies, setToolLatencies] = useState<ToolStat[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [treeRes, cacheRes, toolsRes] = await Promise.all([
          api.playbookTree().catch(() => null),
          api.promptCacheMetrics(10).catch(() => null),
          api.toolLatencies().catch(() => null),
        ]);
        if (treeRes) setPlaybookTree(treeRes);
        if (cacheRes) setCacheMetrics(cacheRes);
        if (toolsRes?.tools) setToolLatencies(toolsRes.tools);
      } catch (err) {
        console.error('Failed to load observability data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <Card><Skeleton height="200px" /></Card>
        <Card><Skeleton height="200px" /></Card>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 1. Prompt Cache Invariance & Hit Rate Metrics */}
      <Card header={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Zap size={18} color="var(--color-profit)" />
          <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body-md)', fontFamily: 'var(--font-precision)' }}>
            [ PROMPT CACHE EFFICIENCY & HIT RATE LEDGER ]
          </span>
        </div>
      }>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '12px',
            background: 'var(--color-surface)',
            padding: '16px',
            borderRadius: '2px',
            border: '1px solid var(--color-rule)',
          }}>
            <div>
              <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Overall Cache Hit Rate</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: (cacheMetrics?.overall_hit_rate_pct || 0) >= 80 ? 'var(--color-profit)' : 'var(--color-ink)' }}>
                {cacheMetrics?.overall_hit_rate_pct?.toFixed(1) || 0}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Total Cached Tokens</div>
              <div style={{ fontSize: '20px', fontWeight: '600', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>
                {cacheMetrics?.total_cached_tokens?.toLocaleString() || 0}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 'var(--text-caption)', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>Total Input Tokens</div>
              <div style={{ fontSize: '20px', fontWeight: '600', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>
                {cacheMetrics?.total_input_tokens?.toLocaleString() || 0}
              </div>
            </div>
          </div>

          {/* Cycle Breakdown */}
          {cacheMetrics?.cycles && cacheMetrics.cycles.length > 0 && (
            <div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                [ RECENT CYCLE HIT RATE TREND ]
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {cacheMetrics.cycles.slice(0, 5).map(c => (
                  <div key={c.cycle_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                    <span style={{ fontFamily: 'var(--font-precision)', fontSize: '12px', color: 'var(--color-ink)' }}>{c.cycle_id}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '120px', height: '6px', background: 'var(--color-surface-card)', border: '1px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, c.hit_rate_pct)}%`, height: '100%', background: c.hit_rate_pct >= 80 ? 'var(--color-profit)' : 'var(--color-brass)' }} />
                      </div>
                      <span style={{ width: '45px', textAlign: 'right', fontWeight: '600', fontSize: '12px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums', color: 'var(--color-ink)' }}>{c.hit_rate_pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* 2. Micro-Playbook Derivation Tree */}
      <Card header={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <GitBranch size={18} color="var(--color-brass)" />
          <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body-md)', fontFamily: 'var(--font-precision)' }}>
            [ AUTONOMOUS MICRO-PLAYBOOK LINEAGE TREE ]
          </span>
        </div>
      }>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {playbookTree?.children && playbookTree.children.length > 0 ? (
            playbookTree.children.map(group => (
              <div key={group.name} style={{ border: '1px solid var(--color-rule)', borderRadius: '2px', padding: '14px', background: 'var(--color-surface)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold', fontSize: '13px', marginBottom: '10px', color: 'var(--color-brass)', fontFamily: 'var(--font-precision)' }}>
                  <BookOpen size={16} />
                  <span>{group.name}</span>
                  <Badge variant="neutral">{group.children?.length || 0} PLAYBOOKS</Badge>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingLeft: '16px' }}>
                  {group.children?.map((p, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', background: 'var(--color-surface-card)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '13px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ChevronRight size={14} color="var(--color-ink-muted)" />
                        <span style={{ fontWeight: '500', color: 'var(--color-ink)' }}>{p.name}</span>
                        {p.win_rate !== undefined && p.win_rate > 0 && (
                          <span style={{ color: 'var(--color-profit)', fontSize: '12px', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>({p.win_rate.toFixed(0)}% WR)</span>
                        )}
                      </div>
                      <Badge variant={p.status === 'active' || p.status === 'golden' ? 'profit' : p.status === 'stale' ? 'warn' : 'neutral'}>
                        {p.status?.toUpperCase() || 'ACTIVE'}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div style={{ color: 'var(--color-ink-muted)', fontSize: '13px', textAlign: 'center', padding: '24px', fontFamily: 'var(--font-precision)' }}>
              No active or compiled micro-playbooks found.
            </div>
          )}
        </div>
      </Card>

      {/* 3. Tool Execution Latency Distribution Histogram */}
      <Card header={
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Clock size={18} color="var(--color-brass)" />
          <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body-md)', fontFamily: 'var(--font-precision)' }}>
            [ TOOL HANDLER EXECUTION LATENCY DISTRIBUTION ]
          </span>
        </div>
      }>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {toolLatencies.length > 0 ? (
            toolLatencies.map(tool => (
              <div key={tool.tool_name} style={{ borderBottom: '1px solid var(--color-rule)', paddingBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontFamily: 'var(--font-precision)', fontSize: '13px', fontWeight: 'bold', color: 'var(--color-ink)' }}>{tool.tool_name}</span>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)', fontVariantNumeric: 'tabular-nums' }}>
                    <span>calls: <b>{tool.call_count}</b></span>
                    <span>avg: <b>{tool.avg_ms}ms</b></span>
                    <span>p90: <b>{tool.p90_ms}ms</b></span>
                  </div>
                </div>
                {/* Histogram distribution bar */}
                <div style={{ display: 'flex', height: '8px', borderRadius: '2px', overflow: 'hidden', gap: '1px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)' }}>
                  {Object.entries(tool.buckets || {}).map(([bucket, count]) => {
                    const pct = tool.call_count > 0 ? (count / tool.call_count) * 100 : 0;
                    if (pct <= 0) return null;
                    const color = bucket === '<50ms' ? 'var(--color-profit)' : bucket === '50-200ms' ? 'var(--color-brass)' : bucket === '200-500ms' ? '#c47d2b' : 'var(--color-loss)';
                    return (
                      <div
                        key={bucket}
                        title={`${bucket}: ${count} calls (${pct.toFixed(1)}%)`}
                        style={{ width: `${pct}%`, background: color }}
                      />
                    );
                  })}
                </div>
              </div>
            ))
          ) : (
            <div style={{ color: 'var(--color-ink-muted)', fontSize: '13px', textAlign: 'center', padding: '24px', fontFamily: 'var(--font-precision)' }}>
              No tool latency telemetry recorded in current session.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};


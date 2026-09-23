import React, { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { BookOpen, Zap, Clock, ChevronRight, GitBranch, Search, AlertTriangle, Eye, RotateCw, ShieldCheck, ShieldAlert, FileText, CornerDownRight } from 'lucide-react';
import { TypewriterButton } from '../ui/TypewriterButton';
import { api } from '../../lib/api';
import type { TraceSpanItem, SlowLlmSpanItem, TradeTrajectoryItem, CycleLineageResponse } from '../../types/api';

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
  const [activeTab, setActiveTab] = useState<'overview' | 'traces' | 'trajectories' | 'lineage'>('overview');
  const [playbookTree, setPlaybookTree] = useState<PlaybookNode | null>(null);
  const [cacheMetrics, setCacheMetrics] = useState<PromptCacheData | null>(null);
  const [toolLatencies, setToolLatencies] = useState<ToolStat[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Trace Inspector State
  const [traces, setTraces] = useState<TraceSpanItem[]>([]);
  const [slowLlm, setSlowLlm] = useState<SlowLlmSpanItem[]>([]);
  const [tracesLoading, setTracesLoading] = useState<boolean>(false);
  const [filterKind, setFilterKind] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterMinDuration, setFilterMinDuration] = useState<string>('');
  const [filterProvider, setFilterProvider] = useState<string>('');
  const [filterModel, setFilterModel] = useState<string>('');
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [traceTreeData, setTraceTreeData] = useState<any | null>(null);

  // Trajectories State (FASE 5A)
  const [trajectories, setTrajectories] = useState<TradeTrajectoryItem[]>([]);
  const [trajLoading, setTrajLoading] = useState<boolean>(false);
  const [selectedTraj, setSelectedTraj] = useState<TradeTrajectoryItem | null>(null);

  // Lineage & SHA-256 Event Chain State (FASE 5B)
  const [lineageCycleId, setLineageCycleId] = useState<string>('cycle-live-847');
  const [lineageData, setLineageData] = useState<CycleLineageResponse | null>(null);
  const [lineageLoading, setLineageLoading] = useState<boolean>(false);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  const fetchOverviewData = async () => {
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

  const fetchTraces = async () => {
    setTracesLoading(true);
    try {
      const [searchRes, slowRes] = await Promise.all([
        api.searchTraces({
          kind: filterKind || undefined,
          status: filterStatus || undefined,
          min_duration_ms: filterMinDuration ? Number(filterMinDuration) : undefined,
          provider: filterProvider || undefined,
          model: filterModel || undefined,
          limit: 100,
        }).catch(() => ({ count: 0, spans: [] })),
        api.slowLlmCalls(15000, 20).catch(() => ({ threshold_ms: 15000, count: 0, spans: [] })),
      ]);
      setTraces(searchRes.spans || []);
      setSlowLlm(slowRes.spans || []);
    } catch (err) {
      console.error('Failed to fetch traces:', err);
    } finally {
      setTracesLoading(false);
    }
  };

  const fetchTrajectories = async () => {
    setTrajLoading(true);
    try {
      const res = await api.tradeTrajectories(50);
      setTrajectories(res.trajectories || []);
      if (res.trajectories && res.trajectories.length > 0 && !selectedTraj) {
        setSelectedTraj(res.trajectories[0]);
      }
    } catch (err) {
      console.error('Failed to load trajectories:', err);
    } finally {
      setTrajLoading(false);
    }
  };

  const fetchLineage = async (cycleId?: string, seq?: number) => {
    const cid = cycleId || lineageCycleId;
    if (!cid) return;
    setLineageLoading(true);
    try {
      const res = await api.cycleLineage(cid, seq);
      setLineageData(res);
    } catch (err) {
      console.error('Failed to load decision lineage:', err);
      setLineageData(null);
    } finally {
      setLineageLoading(false);
    }
  };

  useEffect(() => {
    fetchOverviewData();
  }, []);

  useEffect(() => {
    if (activeTab === 'traces') {
      fetchTraces();
    } else if (activeTab === 'trajectories') {
      fetchTrajectories();
    } else if (activeTab === 'lineage') {
      fetchLineage();
    }
  }, [activeTab, filterKind, filterStatus]);

  const handleInspectTrace = async (traceId: string) => {
    setSelectedTraceId(traceId);
    try {
      const res = await api.traceTree(traceId);
      setTraceTreeData(res);
    } catch (err) {
      console.error(`Failed to fetch trace tree for ${traceId}:`, err);
      setTraceTreeData(null);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <Card><Skeleton height="200px" /></Card>
        <Card><Skeleton height="200px" /></Card>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontFamily: 'var(--font-precision)' }}>
      {/* Sub-tab Navigation Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '2px solid var(--color-rule)', paddingBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <TypewriterButton
            size="sm"
            variant={activeTab === 'overview' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('overview')}
          >
            <Zap size={12} /> [ METRICS & PLAYBOOKS ]
          </TypewriterButton>
          <TypewriterButton
            size="sm"
            variant={activeTab === 'traces' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('traces')}
          >
            <Search size={12} /> [ TRACE INSPECTOR ({traces.length}) ]
          </TypewriterButton>
          <TypewriterButton
            size="sm"
            variant={activeTab === 'trajectories' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('trajectories')}
          >
            <FileText size={12} /> [ TRAJECTORY BROWSER ({trajectories.length}) ]
          </TypewriterButton>
          <TypewriterButton
            size="sm"
            variant={activeTab === 'lineage' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('lineage')}
          >
            <ShieldCheck size={12} /> [ DECISION LINEAGE & SHA-256 ]
          </TypewriterButton>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          {activeTab === 'traces' && (
            <TypewriterButton size="sm" onClick={fetchTraces} disabled={tracesLoading}>
              <RotateCw size={12} className={tracesLoading ? 'animate-spin' : ''} /> [ REFRESH TRACES ]
            </TypewriterButton>
          )}
          {activeTab === 'trajectories' && (
            <TypewriterButton size="sm" onClick={fetchTrajectories} disabled={trajLoading}>
              <RotateCw size={12} className={trajLoading ? 'animate-spin' : ''} /> [ REFRESH TRAJECTORIES ]
            </TypewriterButton>
          )}
          {activeTab === 'lineage' && (
            <TypewriterButton size="sm" onClick={() => fetchLineage(lineageCycleId, selectedSeq || undefined)} disabled={lineageLoading}>
              <RotateCw size={12} className={lineageLoading ? 'animate-spin' : ''} /> [ REFRESH LINEAGE ]
            </TypewriterButton>
          )}
        </div>
      </div>

      {activeTab === 'traces' ? (
        /* TRACE INSPECTOR TAB */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Filters Bar */}
          <Card header={<span>[ TRACE SPAN SEARCH & FILTER ]</span>}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px' }}>
              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>SPAN KIND</label>
                <select
                  value={filterKind}
                  onChange={(e) => setFilterKind(e.target.value)}
                  style={{ width: '100%', padding: '6px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink)', fontSize: 'var(--text-xs)', marginTop: '4px' }}
                >
                  <option value="">All Kinds</option>
                  <option value="llm">LLM Calls</option>
                  <option value="tool">Tool Handlers</option>
                  <option value="node">Graph Nodes</option>
                  <option value="cycle">Cycle</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>STATUS</label>
                <select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  style={{ width: '100%', padding: '6px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink)', fontSize: 'var(--text-xs)', marginTop: '4px' }}
                >
                  <option value="">All Statuses</option>
                  <option value="OK">OK Only</option>
                  <option value="ERROR">Errors Only</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>MIN DURATION (MS)</label>
                <input
                  type="number"
                  placeholder="e.g. 5000"
                  value={filterMinDuration}
                  onChange={(e) => setFilterMinDuration(e.target.value)}
                  onBlur={fetchTraces}
                  style={{ width: '100%', padding: '6px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink)', fontSize: 'var(--text-xs)', marginTop: '4px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>PROVIDER</label>
                <select
                  value={filterProvider}
                  onChange={(e) => setFilterProvider(e.target.value)}
                  style={{ width: '100%', padding: '6px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink)', fontSize: 'var(--text-xs)', marginTop: '4px' }}
                >
                  <option value="">All Providers</option>
                  <option value="gemini">Gemini</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="openai">OpenAI</option>
                  <option value="groq">Groq</option>
                  <option value="openrouter">OpenRouter</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ink-muted)' }}>MODEL</label>
                <input
                  type="text"
                  placeholder="e.g. flash, claude"
                  value={filterModel}
                  onChange={(e) => setFilterModel(e.target.value)}
                  onBlur={fetchTraces}
                  style={{ width: '100%', padding: '6px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', color: 'var(--color-ink)', fontSize: 'var(--text-xs)', marginTop: '4px' }}
                />
              </div>
            </div>
          </Card>

          {/* Slow LLM Alert Card */}
          {slowLlm.length > 0 && (
            <Card
              variant="yellow"
              header={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertTriangle size={14} color="var(--color-brass)" />
                  <span>[ SLOW LLM INVOCATION ALERTS (&gt;15s) — {slowLlm.length} SPANS ]</span>
                </div>
              }
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {slowLlm.map((s, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--color-paper-raised)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: 'var(--text-xs)' }}>
                    <div>
                      <div style={{ fontWeight: 800 }}>{s.name}</div>
                      <div style={{ color: 'var(--color-ink-soft)' }}>
                        {s.provider} / {s.model} {s.cycle_id ? `· Cycle: ${s.cycle_id}` : ''}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 800, color: 'var(--color-loss)' }}>{(s.duration_ms / 1000).toFixed(1)}s</div>
                      {s.cost_usd && <div style={{ color: 'var(--color-ink-soft)' }}>${s.cost_usd.toFixed(4)}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Traces Search Results Table */}
          <Card header={<span>[ TRACE SPANS ({traces.length}) ]</span>}>
            {tracesLoading ? (
              <Skeleton height="160px" />
            ) : traces.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '24px', color: 'var(--color-ink-muted)' }}>
                No trace spans found matching current filters.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-rule)', textAlign: 'left', color: 'var(--color-ink-muted)' }}>
                      <th style={{ padding: '6px' }}>NAME / SPAN</th>
                      <th style={{ padding: '6px' }}>KIND</th>
                      <th style={{ padding: '6px' }}>DURATION</th>
                      <th style={{ padding: '6px' }}>STATUS</th>
                      <th style={{ padding: '6px' }}>START TIME</th>
                      <th style={{ padding: '6px' }}>ACTION</th>
                    </tr>
                  </thead>
                  <tbody>
                    {traces.map((span) => {
                      const isErr = span.status === 'ERROR';
                      return (
                        <tr key={span.span_id} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                          <td style={{ padding: '6px' }}>
                            <div style={{ fontWeight: 700 }}>{span.name}</div>
                            <div style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>{span.span_id}</div>
                          </td>
                          <td style={{ padding: '6px' }}>
                            <Badge variant="neutral">{span.kind.toUpperCase()}</Badge>
                          </td>
                          <td style={{ padding: '6px', fontWeight: 700 }}>
                            {span.duration_ms >= 1000 ? `${(span.duration_ms / 1000).toFixed(2)}s` : `${Math.round(span.duration_ms)}ms`}
                          </td>
                          <td style={{ padding: '6px' }}>
                            <Badge variant={isErr ? 'warn' : 'active'}>{span.status}</Badge>
                          </td>
                          <td style={{ padding: '6px', color: 'var(--color-ink-soft)' }}>
                            {span.start_time ? span.start_time.slice(11, 19) : '—'}
                          </td>
                          <td style={{ padding: '6px' }}>
                            <TypewriterButton size="sm" onClick={() => handleInspectTrace(span.trace_id)}>
                              <Eye size={10} /> Inspect
                            </TypewriterButton>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Trace Tree Inspector */}
          {selectedTraceId && (
            <Card
              header={
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>[ TRACE HIERARCHY TREE — {selectedTraceId} ]</span>
                  <TypewriterButton size="sm" onClick={() => setSelectedTraceId(null)}>✕ Close</TypewriterButton>
                </div>
              }
            >
              <pre style={{ background: 'var(--color-surface)', padding: '12px', borderRadius: '2px', fontSize: '11px', overflowX: 'auto', maxHeight: '300px' }}>
                <code>{JSON.stringify(traceTreeData || { trace_id: selectedTraceId, status: 'loading...' }, null, 2)}</code>
              </pre>
            </Card>
          )}
        </div>
      ) : activeTab === 'trajectories' ? (
        /* TRADE TRAJECTORIES BROWSER (FASE 5A) */
        <div style={{ display: 'grid', gridTemplateColumns: selectedTraj ? '1fr 1.2fr' : '1fr', gap: '16px' }}>
          {/* List of trajectories */}
          <Card header={<span>[ RECORDED TRADE TRAJECTORIES ({trajectories.length}) ]</span>}>
            {trajLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <Skeleton height="60px" />
                <Skeleton height="60px" />
                <Skeleton height="60px" />
              </div>
            ) : trajectories.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--color-ink-muted)', fontSize: '13px' }}>
                No trade trajectories recorded in logs yet.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '680px', overflowY: 'auto' }}>
                {trajectories.map((traj, idx) => {
                  const isSelected = selectedTraj?.ticket === traj.ticket && selectedTraj?.timestamp === traj.timestamp;
                  const isBuy = traj.decision.includes('BUY');
                  const isSell = traj.decision.includes('SELL');
                  return (
                    <div
                      key={idx}
                      onClick={() => setSelectedTraj(traj)}
                      style={{
                        padding: '10px 14px',
                        background: isSelected ? 'var(--color-surface-active, rgba(232, 185, 74, 0.08))' : 'var(--color-surface)',
                        border: isSelected ? '1.5px solid var(--color-brass)' : '1px solid var(--color-rule)',
                        borderRadius: '2px',
                        cursor: 'pointer',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 800, fontSize: '13px', color: 'var(--color-ink)' }}>{traj.symbol}</span>
                          <Badge variant={isBuy ? 'profit' : isSell ? 'loss' : 'neutral'}>
                            {traj.decision}
                          </Badge>
                          {traj.ticket && (
                            <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>#{traj.ticket}</span>
                          )}
                        </div>
                        {traj.pnl_pct !== null && traj.pnl_pct !== undefined ? (
                          <span style={{
                            fontWeight: 700,
                            fontSize: '12px',
                            color: traj.pnl_pct >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
                          }}>
                            {traj.pnl_pct >= 0 ? `+${traj.pnl_pct.toFixed(2)}%` : `${traj.pnl_pct.toFixed(2)}%`}
                          </span>
                        ) : (
                          <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>OPEN</span>
                        )}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        <span>{new Date(traj.timestamp).toLocaleString()}</span>
                        {traj.mae_points !== null && traj.mae_points !== undefined && (
                          <span>MAE: {traj.mae_points}pt | MFE: {traj.mfe_points}pt</span>
                        )}
                      </div>

                      {traj.reflection_tags && traj.reflection_tags.length > 0 && (
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '2px' }}>
                          {traj.reflection_tags.map(t => (
                            <span key={t} style={{ fontSize: '9px', padding: '1px 5px', background: 'var(--color-bg)', border: '1px solid var(--color-rule)', borderRadius: '2px', color: 'var(--color-ink-soft)' }}>
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Trajectory Inspector */}
          {selectedTraj && (
            <Card header={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileText size={16} color="var(--color-brass)" />
                  <span>[ TRAJECTORY TRACE: {selectedTraj.symbol} #{selectedTraj.ticket || 'UNFILLED'} ]</span>
                </div>
                <Badge variant={selectedTraj.decision.includes('BUY') ? 'profit' : 'loss'}>
                  {selectedTraj.decision}
                </Badge>
              </div>
            }>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', maxHeight: '680px', overflowY: 'auto' }}>
                {/* Meta Bar */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', padding: '8px 12px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '12px' }}>
                  <div>
                    <span style={{ color: 'var(--color-ink-muted)', display: 'block', fontSize: '10px' }}>TIMESTAMP</span>
                    <b>{new Date(selectedTraj.timestamp).toLocaleString()}</b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--color-ink-muted)', display: 'block', fontSize: '10px' }}>PNL REALIZED</span>
                    <b style={{ color: (selectedTraj.pnl_pct || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                      {selectedTraj.pnl_pct !== null && selectedTraj.pnl_pct !== undefined ? `${selectedTraj.pnl_pct.toFixed(2)}%` : 'PENDING'}
                    </b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--color-ink-muted)', display: 'block', fontSize: '10px' }}>MAE / MFE</span>
                    <b>{selectedTraj.mae_points ?? '-'} / {selectedTraj.mfe_points ?? '-'}</b>
                  </div>
                </div>

                {/* Milestone 1: Fundamental Macro Brief */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '4px' }}>
                    <CornerDownRight size={13} /> STAGE 1: FUNDAMENTAL MACRO BRIEF
                  </div>
                  <pre style={{ margin: 0, padding: '10px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '11px', whiteSpace: 'pre-wrap', maxHeight: '140px', overflowY: 'auto' }}>
                    <code>{JSON.stringify(selectedTraj.fundamental_brief || {}, null, 2)}</code>
                  </pre>
                </div>

                {/* Milestone 2: Specialist Pipeline Outputs */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '4px' }}>
                    <CornerDownRight size={13} /> STAGE 2: SPECIALIST PIPELINE OUTPUTS
                  </div>
                  <pre style={{ margin: 0, padding: '10px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '11px', whiteSpace: 'pre-wrap', maxHeight: '140px', overflowY: 'auto' }}>
                    <code>{JSON.stringify(selectedTraj.specialist_outputs || {}, null, 2)}</code>
                  </pre>
                </div>

                {/* Milestone 3: Dialectic Debate Verdict */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '4px' }}>
                    <CornerDownRight size={13} /> STAGE 3: DIALECTIC DEBATE VERDICT
                  </div>
                  <pre style={{ margin: 0, padding: '10px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '11px', whiteSpace: 'pre-wrap', maxHeight: '140px', overflowY: 'auto' }}>
                    <code>{JSON.stringify(selectedTraj.debate_verdict || {}, null, 2)}</code>
                  </pre>
                </div>

                {/* Milestone 4: Risk Gate Verification & Execution */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800, color: 'var(--color-brass)', marginBottom: '4px' }}>
                    <CornerDownRight size={13} /> STAGE 4 & 5: RISK GATE & EXECUTION
                  </div>
                  <pre style={{ margin: 0, padding: '10px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', fontSize: '11px', whiteSpace: 'pre-wrap', maxHeight: '140px', overflowY: 'auto' }}>
                    <code>{JSON.stringify({ risk: selectedTraj.risk_decision, execution: selectedTraj.execution_details }, null, 2)}</code>
                  </pre>
                </div>
              </div>
            </Card>
          )}
        </div>
      ) : activeTab === 'lineage' ? (
        /* DECISION LINEAGE & SHA-256 HASH CHAIN (FASE 5B) */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Header controls & Verification Banner */}
          <Card header={<span>[ TRADING CYCLE EVENT LOG & CRYPTOGRAPHIC PROVENANCE ]</span>}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--color-ink-muted)' }}>CYCLE ID:</span>
                <input
                  type="text"
                  value={lineageCycleId}
                  onChange={(e) => setLineageCycleId(e.target.value)}
                  placeholder="e.g. cycle-live-847"
                  style={{
                    padding: '6px 10px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink)',
                    fontSize: '12px',
                    fontFamily: 'var(--font-precision)',
                    borderRadius: '2px',
                    minWidth: '220px',
                  }}
                />
                <TypewriterButton size="sm" onClick={() => fetchLineage(lineageCycleId)} disabled={lineageLoading}>
                  <Search size={12} /> [ TRACE LINEAGE ]
                </TypewriterButton>
                {selectedSeq !== null && (
                  <TypewriterButton size="sm" variant="secondary" onClick={() => { setSelectedSeq(null); fetchLineage(lineageCycleId); }}>
                    [ CLEAR ANCESTOR FILTER ]
                  </TypewriterButton>
                )}
              </div>

              {/* Cryptographic SHA-256 Chain Integrity Status Banner */}
              {lineageData && (
                <div style={{
                  padding: '12px 16px',
                  background: lineageData.integrity_valid ? 'rgba(74, 185, 120, 0.08)' : 'rgba(235, 87, 87, 0.08)',
                  border: `1.5px solid ${lineageData.integrity_valid ? 'var(--color-profit)' : 'var(--color-loss)'}`,
                  borderRadius: '2px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '10px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {lineageData.integrity_valid ? (
                      <ShieldCheck size={20} color="var(--color-profit)" />
                    ) : (
                      <ShieldAlert size={20} color="var(--color-loss)" />
                    )}
                    <div>
                      <div style={{ fontWeight: 800, fontSize: '13px', color: lineageData.integrity_valid ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {lineageData.integrity_valid ? '[CRYPTO INTEGRITY VERIFIED] SHA-256 Hash Chain Unbroken' : '[INTEGRITY ALERT] Hash Chain Tampered or Broken'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        {lineageData.integrity_valid
                          ? `Total ${lineageData.total_events} monotonic event-sourced records verified against origin SHA-256 hash.`
                          : `Validation error: ${lineageData.integrity_error}`}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '14px', fontSize: '12px', fontFamily: 'var(--font-precision)' }}>
                    <span>EVENTS: <b>{lineageData.total_events}</b></span>
                    <span>START: <b>{lineageData.start_time ? new Date(lineageData.start_time).toLocaleTimeString() : '-'}</b></span>
                    <span>END: <b>{lineageData.end_time ? new Date(lineageData.end_time).toLocaleTimeString() : '-'}</b></span>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {/* Event Stream & Ancestor Lineage Tree */}
          <Card header={
            <span>
              [ {selectedSeq !== null ? `ANCESTOR PROVENANCE CHAIN FOR EVENT #${selectedSeq}` : `MONOTONIC EVENT CHAIN (${lineageData?.events?.length || 0})`} ]
            </span>
          }>
            {lineageLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <Skeleton height="40px" />
                <Skeleton height="40px" />
                <Skeleton height="40px" />
              </div>
            ) : !lineageData || lineageData.events.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--color-ink-muted)', fontSize: '13px' }}>
                No events found for cycle {lineageCycleId}.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--color-rule)', color: 'var(--color-ink-muted)' }}>
                      <th style={{ padding: '8px 10px' }}>SEQ</th>
                      <th style={{ padding: '8px 10px' }}>EVENT TYPE</th>
                      <th style={{ padding: '8px 10px' }}>TIMESTAMP</th>
                      <th style={{ padding: '8px 10px' }}>CHAIN HASH</th>
                      <th style={{ padding: '8px 10px' }}>PARENTS</th>
                      <th style={{ padding: '8px 10px', textAlign: 'right' }}>ACTION</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selectedSeq !== null && lineageData.lineage.length > 0 ? lineageData.lineage : lineageData.events).map((ev) => {
                      const isHighlighted = ev.seq === selectedSeq;
                      return (
                        <tr
                          key={ev.seq}
                          style={{
                            borderBottom: '1px solid var(--color-rule)',
                            background: isHighlighted ? 'rgba(232, 185, 74, 0.12)' : 'transparent',
                          }}
                        >
                          <td style={{ padding: '8px 10px', fontWeight: 800, color: 'var(--color-brass)' }}>#{ev.seq}</td>
                          <td style={{ padding: '8px 10px' }}>
                            <Badge variant={ev.event_type.includes('order') ? 'profit' : ev.event_type.includes('risk') ? 'warn' : 'neutral'}>
                              {ev.event_type}
                            </Badge>
                          </td>
                          <td style={{ padding: '8px 10px', color: 'var(--color-ink-muted)', fontVariantNumeric: 'tabular-nums' }}>
                            {new Date(ev.timestamp).toLocaleTimeString()}
                          </td>
                          <td style={{ padding: '8px 10px', fontFamily: 'monospace', fontSize: '10px', color: 'var(--color-ink-soft)' }} title={ev.chain_hash || ''}>
                            {ev.chain_hash ? `${ev.chain_hash.slice(0, 10)}...${ev.chain_hash.slice(-6)}` : '-'}
                          </td>
                          <td style={{ padding: '8px 10px' }}>
                            {ev.source_event_seqs && ev.source_event_seqs.length > 0 ? (
                              <div style={{ display: 'flex', gap: '4px' }}>
                                {ev.source_event_seqs.map(s => (
                                  <span key={s} style={{ fontSize: '10px', padding: '1px 4px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px' }}>
                                    #{s}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span style={{ fontSize: '10px', color: 'var(--color-ink-muted)' }}>origin</span>
                            )}
                          </td>
                          <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                            <TypewriterButton
                              size="sm"
                              variant={isHighlighted ? 'primary' : 'secondary'}
                              onClick={() => {
                                setSelectedSeq(ev.seq);
                                fetchLineage(lineageCycleId, ev.seq);
                              }}
                            >
                              [ TRACE ]
                            </TypewriterButton>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      ) : (
        /* METRICS & OVERVIEW TAB */
        <>
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
        </>
      )}
    </div>
  );
};


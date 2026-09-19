import React, { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { api } from '../../lib/api';
import type { DebateOutcomeItem } from '../../types/api';
import {
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Scale,
  RefreshCw,
  Search,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Award,
} from 'lucide-react';

const renderThesisContent = (content: unknown) => {
  if (!content) {
    return <span style={{ color: 'var(--color-ink-muted)', fontStyle: 'italic' }}>No thesis recorded.</span>;
  }
  if (typeof content === 'string') {
    return <span>{content}</span>;
  }
  if (typeof content === 'object') {
    const obj = content as Record<string, unknown>;
    const summary = obj.summary || obj.thesis || obj.claim || obj.argument || obj.core_thesis;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {summary && (
          <div style={{ fontWeight: 600, color: 'var(--color-ink)', fontSize: '13px' }}>
            {String(summary)}
          </div>
        )}
        {Object.entries(obj).map(([k, v]) => {
          if (['summary', 'thesis', 'claim', 'argument', 'core_thesis'].includes(k)) return null;
          return (
            <div key={k} style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <span style={{ color: 'var(--color-ink-muted)', textTransform: 'capitalize', fontWeight: 500 }}>
                {k.replace(/_/g, ' ')}:
              </span>
              <span style={{ color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          );
        })}
      </div>
    );
  }
  return <span>{String(content)}</span>;
};

export const DebateOutcomesPanel: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [debates, setDebates] = useState<DebateOutcomeItem[]>([]);
  const [symbolFilter, setSymbolFilter] = useState<string>('');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const res = await api.debateOutcomes(50);
      const items = res.items || [];
      setDebates(items);
      if (items.length > 0) {
        setExpandedId((prev) => (prev !== null ? prev : items[0].id));
      }
    } catch (err) {
      console.error('Failed to load debate outcomes data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggleExpand = (id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  // KPIs
  const totalDebates = debates.length;
  const buyDecisions = debates.filter((d) => d.decision?.toLowerCase() === 'buy').length;
  const sellDecisions = debates.filter((d) => d.decision?.toLowerCase() === 'sell').length;
  const avgConfidence =
    totalDebates > 0
      ? (
          debates.reduce((acc, d) => {
            const c = d.confidence ?? 0;
            return acc + (c <= 1 && c > 0 ? c * 100 : c);
          }, 0) / totalDebates
        ).toFixed(1)
      : '0.0';
  const avgConfluence =
    totalDebates > 0
      ? (
          debates.reduce((acc, d) => acc + (d.confluence_score || 0), 0) /
          totalDebates
        ).toFixed(1)
      : '0.0';

  const filteredDebates = debates.filter((d) => {
    if (!symbolFilter.trim()) return true;
    return d.symbol ? d.symbol.toLowerCase().includes(symbolFilter.toLowerCase().trim()) : false;
  });

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}><Skeleton height="90px" /></Card>
          ))}
        </div>
        <Card><Skeleton height="350px" /></Card>
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
            <Scale size={18} />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Bull vs Bear Debate Outcomes & Adjudication
            </h2>
            <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', marginTop: '2px', fontFamily: 'var(--font-precision)' }}>
              Multi-agent dialectic arbitration, specialist thesis comparison, and final trade conviction
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              height: '28px',
              boxSizing: 'border-box',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              padding: '0 8px',
            }}
          >
            <Search size={13} color="var(--color-ink-muted)" />
            <input
              type="text"
              placeholder="Search symbol..."
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-ink)',
                fontSize: '11px',
                outline: 'none',
                width: '120px',
                fontFamily: 'var(--font-precision)',
              }}
            />
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
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
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
      </div>

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
                Total Adjudicated Debates
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-ink)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {totalDebates}
              </div>
            </div>
            <div style={{ color: 'var(--color-brass)' }}>
              <Scale size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Multi-agent arbitration cycles
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Bull vs Bear Decisions
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-profit)', fontFamily: 'var(--font-precision)' }}>
                  ▲ {buyDecisions}
                </span>
                <span style={{ fontSize: '16px', color: 'var(--color-ink-muted)' }}>/</span>
                <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-loss)', fontFamily: 'var(--font-precision)' }}>
                  ▼ {sellDecisions}
                </span>
              </div>
            </div>
            <div style={{ color: 'var(--color-ink-muted)' }}>
              <Sparkles size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Directional outcome breakdown
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Average Conviction / Confidence
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: Number(avgConfidence) >= 70 ? 'var(--color-profit)' : 'var(--color-warning)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {avgConfidence}%
              </div>
            </div>
            <div style={{ color: 'var(--color-profit)' }}>
              <TrendingUp size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Post-debate confidence level
          </div>
        </Card>

        <Card className="ledger-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Average Confluence Score
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--color-brass)', marginTop: '4px', fontFamily: 'var(--font-precision)' }}>
                {avgConfluence}
              </div>
            </div>
            <div style={{ color: 'var(--color-brass)' }}>
              <ShieldAlert size={18} />
            </div>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '8px', fontFamily: 'var(--font-precision)' }}>
            Technical + macro signal alignment
          </div>
        </Card>
      </div>

      {/* Debates List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {filteredDebates.length > 0 ? (
          filteredDebates.map((item) => {
            const isBuy = item.decision?.toLowerCase() === 'buy';
            const isExpanded = expandedId === item.id;
            const rawConf = item.confidence ?? 0;
            const confVal = rawConf <= 1 && rawConf > 0 ? rawConf * 100 : rawConf;
            const adj = item.specialist_adjudication;

            return (
              <Card key={item.id} className="ledger-card">
                {/* Collapsible Card Header */}
                <div
                  onClick={() => toggleExpand(item.id)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    cursor: 'pointer',
                    userSelect: 'none',
                    flexWrap: 'wrap',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                    <div
                      style={{
                        fontSize: '15px',
                        fontWeight: 700,
                        color: 'var(--color-ink)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      {item.symbol}
                      <Badge variant={isBuy ? 'buy' : 'sell'} size="sm">
                        {isBuy ? (
                          <TrendingUp size={11} style={{ marginRight: 2 }} />
                        ) : (
                          <TrendingDown size={11} style={{ marginRight: 2 }} />
                        )}
                        {item.decision.toUpperCase()}
                      </Badge>
                    </div>

                    {/* Confidence with meter bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        Confidence:
                      </span>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                        {item.confidence !== null && item.confidence !== undefined ? `${confVal.toFixed(0)}%` : '—'}
                      </span>
                      <div style={{ width: '50px', height: '3px', background: 'var(--color-rule)', borderRadius: '1px', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.min(100, Math.max(0, confVal))}%`,
                            height: '100%',
                            background: isBuy ? 'var(--color-profit)' : 'var(--color-loss)',
                            borderRadius: '1px',
                          }}
                        />
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                        Confluence:
                      </span>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-brass)', fontFamily: 'var(--font-precision)' }}>
                        {item.confluence_score !== null && item.confluence_score !== undefined ? item.confluence_score : '—'}
                      </span>
                    </div>

                    {item.risk_multiplier !== null && item.risk_multiplier !== undefined && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                          Risk:
                        </span>
                        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
                          {item.risk_multiplier}x
                        </span>
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {item.execution_status && (
                      <Badge variant="neutral" size="sm">
                        {item.execution_status}
                      </Badge>
                    )}
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', display: 'flex', alignItems: 'center', gap: '4px', fontFamily: 'var(--font-precision)' }}>
                      <Clock size={11} />
                      {item.generated_at ? new Date(item.generated_at).toLocaleString() : '—'}
                    </div>
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: '14px',
                      paddingTop: '14px',
                      borderTop: '1px solid var(--color-border)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '14px',
                    }}
                  >
                    {/* Bull vs Bear Argument Cards Side-by-Side */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
                      {/* Bull Thesis Card */}
                      <div
                        style={{
                          background: 'var(--color-surface)',
                          border: '1px solid var(--color-profit)',
                          borderLeft: '3px solid var(--color-profit)',
                          borderRadius: '2px',
                          padding: '14px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '8px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--color-profit)', fontWeight: 700, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          <TrendingUp size={14} />
                          <span>Bull Thesis & Arguments</span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--color-ink)', lineHeight: 1.6 }}>
                          {renderThesisContent(item.debate_bull_thesis)}
                        </div>
                      </div>

                      {/* Bear Dissent Card */}
                      <div
                        style={{
                          background: 'var(--color-surface)',
                          border: '1px solid var(--color-loss)',
                          borderLeft: '3px solid var(--color-loss)',
                          borderRadius: '2px',
                          padding: '14px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '8px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--color-loss)', fontWeight: 700, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          <TrendingDown size={14} />
                          <span>Bear Dissent & Counter-Arguments</span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--color-ink)', lineHeight: 1.6 }}>
                          {renderThesisContent(item.debate_bear_dissent)}
                        </div>
                      </div>
                    </div>

                    {/* Debate Verdict & Reason Banner */}
                    {(item.debate_verdict || item.debate_reason) && (
                      <div
                        style={{
                          background: 'var(--color-surface-card)',
                          border: '1px solid var(--color-border)',
                          borderLeft: '3px solid var(--color-brass)',
                          borderRadius: '2px',
                          padding: '10px 14px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '4px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Award size={14} color="var(--color-brass)" />
                          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-brass)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Debate Verdict: {item.debate_verdict || item.decision.toUpperCase()}
                          </span>
                        </div>
                        {item.debate_reason && (
                          <div style={{ fontSize: '12px', color: 'var(--color-ink-muted)', lineHeight: 1.5 }}>
                            {item.debate_reason}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Synthesis Rationale */}
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
                        Synthesis Rationale
                      </div>
                      <div
                        style={{
                          fontSize: '12px',
                          color: 'var(--color-ink)',
                          lineHeight: 1.6,
                          background: 'var(--color-surface)',
                          padding: '10px 14px',
                          borderRadius: '2px',
                          border: '1px solid var(--color-border)',
                          whiteSpace: 'pre-wrap',
                          fontFamily: 'var(--font-precision)',
                        }}
                      >
                        {item.rationale || 'No specific rationale provided.'}
                      </div>
                    </div>

                    {/* Specialist Adjudication breakdown */}
                    {adj && (
                      <div>
                        <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
                          Specialist Dialectic Adjudication
                        </div>
                        <div
                          style={{
                            background: 'var(--color-surface)',
                            borderRadius: '2px',
                            padding: '10px 14px',
                            border: '1px solid var(--color-border)',
                          }}
                        >
                          {typeof adj === 'object' ? (
                            <pre
                              style={{
                                margin: 0,
                                fontSize: '11px',
                                fontFamily: 'var(--font-precision)',
                                color: 'var(--color-ink)',
                                overflowX: 'auto',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                              }}
                            >
                              {JSON.stringify(adj, null, 2)}
                            </pre>
                          ) : (
                            <div style={{ fontSize: '12px', color: 'var(--color-ink)', lineHeight: 1.6 }}>
                              {String(adj)}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            );
          })
        ) : (
          <Card className="ledger-card">
            <div style={{ textAlign: 'center', padding: '32px', color: 'var(--color-ink-muted)' }}>
              No debate outcomes found matching filter.
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};

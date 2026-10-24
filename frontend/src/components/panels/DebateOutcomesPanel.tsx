import React, { useEffect, useState, useCallback } from 'react';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { api } from '../../lib/api';
import type { DebateOutcomeItem } from '../../types/api';
import {
  TrendingUp,
  TrendingDown,
  Scale,
  RefreshCw,
  Search,
  Clock,
  ChevronDown,
  ChevronUp,
  Award,
} from 'lucide-react';

const renderThesisContent = (content: unknown) => {
  if (!content) {
    return (
      <span style={{ color: 'var(--color-ink-muted)', fontStyle: 'italic' }}>
        No thesis recorded for this cycle.
      </span>
    );
  }
  if (typeof content === 'string') {
    return <p style={{ margin: 0, lineHeight: 1.65, color: 'var(--color-ink-soft)' }}>{content}</p>;
  }
  if (typeof content === 'object') {
    const obj = content as Record<string, unknown>;
    const summary = obj.summary || obj.thesis || obj.claim || obj.argument || obj.core_thesis;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {summary && (
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '17px',
              lineHeight: 1.35,
              color: 'var(--color-ink)',
            }}
          >
            “{String(summary)}”
          </div>
        )}
        {Object.entries(obj).map(([k, v]) => {
          if (['summary', 'thesis', 'claim', 'argument', 'core_thesis'].includes(k)) return null;
          return (
            <div
              key={k}
              style={{
                fontSize: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                paddingTop: '6px',
                borderTop: '1px solid var(--color-rule)',
              }}
            >
              <span className="editorial-kicker">
                {k.replace(/_/g, ' ')}
              </span>
              <span style={{ color: 'var(--color-ink-soft)', fontFamily: 'var(--font-sans)', lineHeight: 1.55 }}>
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <Skeleton height="90px" />
        <Skeleton height="350px" />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {/* Editorial Broadsheet Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          flexWrap: 'wrap',
          gap: '16px',
          borderBottom: '1px solid var(--color-rule)',
          paddingBottom: '14px',
          marginBottom: '16px',
        }}
      >
        <div>
          <div className="editorial-kicker">I. DIALECTIC ADJUDICATION</div>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '24px',
              fontWeight: 400,
              margin: '2px 0 0 0',
              color: 'var(--color-ink)',
            }}
          >
            Bull vs. Bear Dialectic Broadsheet
          </h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              height: '30px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              padding: '0 10px',
            }}
          >
            <Search size={12} color="var(--color-ink-muted)" />
            <input
              type="text"
              placeholder="Filter instrument..."
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-ink)',
                fontSize: '11px',
                outline: 'none',
                width: '130px',
                fontFamily: 'var(--font-precision)',
              }}
            />
          </div>

          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="editorial-btn editorial-btn--ghost"
          >
            <RefreshCw size={12} className={refreshing ? 'spin-anim' : ''} />
            {refreshing ? 'SYNCING...' : 'REFRESH'}
          </button>
        </div>
      </div>

      {/* Unboxed 4-Column Architectural KPI Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
          borderTop: '1px solid var(--color-rule)',
          borderBottom: '1px solid var(--color-rule)',
          borderLeft: '1px solid var(--color-rule)',
          marginBottom: '20px',
          background: 'var(--color-paper-raised)',
        }}
      >
        <div style={{ padding: '14px 16px', borderRight: '1px solid var(--color-rule)' }}>
          <div className="editorial-kicker">ADJUDICATED DEBATES</div>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '28px',
              color: 'var(--color-ink)',
              marginTop: '4px',
            }}
          >
            {totalDebates}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
            Dialectic cycles recorded
          </div>
        </div>

        <div style={{ padding: '14px 16px', borderRight: '1px solid var(--color-rule)' }}>
          <div className="editorial-kicker">DIRECTIONAL SPLIT</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
            <span
              className="tabular-nums"
              style={{ fontFamily: 'var(--font-display)', fontSize: '28px', color: 'var(--color-profit)' }}
            >
              +{buyDecisions}
            </span>
            <span style={{ color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>/</span>
            <span
              className="tabular-nums"
              style={{ fontFamily: 'var(--font-display)', fontSize: '28px', color: 'var(--color-loss)' }}
            >
              -{sellDecisions}
            </span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
            Bullish vs. Bearish verdicts
          </div>
        </div>

        <div style={{ padding: '14px 16px', borderRight: '1px solid var(--color-rule)' }}>
          <div className="editorial-kicker">MEAN CONVICTION</div>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '28px',
              color: Number(avgConfidence) >= 70 ? 'var(--color-profit)' : 'var(--color-ink)',
              marginTop: '4px',
            }}
          >
            {avgConfidence}%
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
            Post-arbitration confidence
          </div>
        </div>

        <div style={{ padding: '14px 16px', borderRight: '1px solid var(--color-rule)' }}>
          <div className="editorial-kicker">MEAN CONFLUENCE</div>
          <div
            className="tabular-nums"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '28px',
              color: 'var(--color-ink)',
              marginTop: '4px',
            }}
          >
            {avgConfluence}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
            Macro + technical alignment
          </div>
        </div>
      </div>

      {/* Debates Broadsheet Stack */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {filteredDebates.length > 0 ? (
          filteredDebates.map((item) => {
            const isBuy = item.decision?.toLowerCase() === 'buy';
            const isExpanded = expandedId === item.id;
            const rawConf = item.confidence ?? 0;
            const confVal = rawConf <= 1 && rawConf > 0 ? rawConf * 100 : rawConf;
            const adj = item.specialist_adjudication;

            return (
              <div
                key={item.id}
                className="editorial-section swiss-crosshair"
                style={{
                  border: '1px solid var(--color-rule)',
                  background: 'var(--color-paper-raised)',
                }}
              >
                {/* Collapsible Broadsheet Masthead */}
                <div
                  onClick={() => toggleExpand(item.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      toggleExpand(item.id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    cursor: 'pointer',
                    userSelect: 'none',
                    flexWrap: 'wrap',
                    gap: '12px',
                    padding: '14px 18px',
                    background: isExpanded ? 'var(--color-paper)' : 'transparent',
                    borderBottom: isExpanded ? '1px solid var(--color-rule)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                    <div
                      style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: '20px',
                        color: 'var(--color-ink)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                      }}
                    >
                      {item.symbol}
                      <Badge variant={isBuy ? 'buy' : 'sell'} size="sm">
                        {isBuy ? (
                          <TrendingUp size={11} style={{ marginRight: 3 }} />
                        ) : (
                          <TrendingDown size={11} style={{ marginRight: 3 }} />
                        )}
                        {item.decision?.toUpperCase() ?? 'HOLD'}
                      </Badge>
                    </div>

                    {/* Confidence with hairline meter */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="editorial-kicker">CONVICTION</span>
                      <span
                        className="tabular-nums"
                        style={{
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--color-ink)',
                          fontFamily: 'var(--font-precision)',
                        }}
                      >
                        {item.confidence !== null && item.confidence !== undefined ? `${confVal.toFixed(0)}%` : '—'}
                      </span>
                      <div style={{ width: '56px', height: '3px', background: 'var(--color-rule)', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.min(100, Math.max(0, confVal))}%`,
                            height: '100%',
                            background: isBuy ? 'var(--color-profit)' : 'var(--color-loss)',
                          }}
                        />
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="editorial-kicker">CONFLUENCE</span>
                      <span
                        className="tabular-nums"
                        style={{
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--color-ink)',
                          fontFamily: 'var(--font-precision)',
                        }}
                      >
                        {item.confluence_score !== null && item.confluence_score !== undefined ? item.confluence_score : '—'}
                      </span>
                    </div>

                    {item.risk_multiplier !== null && item.risk_multiplier !== undefined && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="editorial-kicker">RISK MULT</span>
                        <span
                          className="tabular-nums"
                          style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: 'var(--color-ink-soft)',
                            fontFamily: 'var(--font-precision)',
                          }}
                        >
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
                    <div
                      style={{
                        fontSize: '11px',
                        color: 'var(--color-ink-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontFamily: 'var(--font-precision)',
                      }}
                    >
                      <Clock size={11} />
                      {item.generated_at ? new Date(item.generated_at).toLocaleString() : '—'}
                    </div>
                    {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  </div>
                </div>

                {/* Expanded 2-Column Swiss Broadsheet Details */}
                {isExpanded && (
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {/* 2-Column Bull vs Bear Broadsheet Grid */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        borderBottom: '1px solid var(--color-rule)',
                      }}
                    >
                      {/* Column I: Bullish Proponent */}
                      <div
                        style={{
                          padding: '18px 20px',
                          borderRight: '1px solid var(--color-rule)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span className="editorial-kicker" style={{ color: 'var(--color-profit)' }}>
                            I. BULLISH THESIS — PROPONENT
                          </span>
                          <TrendingUp size={13} color="var(--color-profit)" />
                        </div>
                        <div style={{ fontSize: '13px', color: 'var(--color-ink)', lineHeight: 1.65 }}>
                          {renderThesisContent(item.debate_bull_thesis)}
                        </div>
                      </div>

                      {/* Column II: Bearish Dissent */}
                      <div
                        style={{
                          padding: '18px 20px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span className="editorial-kicker" style={{ color: 'var(--color-loss)' }}>
                            II. BEARISH COUNTER-THESIS — DISSENT
                          </span>
                          <TrendingDown size={13} color="var(--color-loss)" />
                        </div>
                        <div style={{ fontSize: '13px', color: 'var(--color-ink)', lineHeight: 1.65 }}>
                          {renderThesisContent(item.debate_bear_dissent)}
                        </div>
                      </div>
                    </div>

                    {/* Section III: Judge Verdict Pull-Quote & Synthesis */}
                    <div
                      style={{
                        padding: '18px 20px',
                        background: 'var(--color-paper)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Scale size={14} color="var(--color-accent)" />
                          <span className="editorial-kicker" style={{ color: 'var(--color-accent)' }}>
                            III. CHIEF RISK JUDGE VERDICT — {item.debate_verdict || item.decision?.toUpperCase() || 'ADJUDICATED'}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Award size={13} color="var(--color-ink-muted)" />
                          <span style={{ fontSize: '11px', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-muted)' }}>
                            RECORD #{item.id}
                          </span>
                        </div>
                      </div>

                      {(item.debate_reason || item.rationale) && (
                        <blockquote
                          style={{
                            margin: 0,
                            paddingLeft: '14px',
                            borderLeft: '2px solid var(--color-accent)',
                            fontFamily: 'var(--font-display)',
                            fontSize: '18px',
                            lineHeight: 1.45,
                            color: 'var(--color-ink)',
                          }}
                        >
                          “{item.debate_reason || item.rationale}”
                        </blockquote>
                      )}

                      {item.rationale && item.debate_reason && item.rationale !== item.debate_reason && (
                        <div
                          style={{
                            fontSize: '12px',
                            color: 'var(--color-ink-soft)',
                            lineHeight: 1.6,
                            fontFamily: 'var(--font-sans)',
                            paddingTop: '8px',
                            borderTop: '1px solid var(--color-rule)',
                          }}
                        >
                          {item.rationale}
                        </div>
                      )}

                      {/* Specialist Adjudication breakdown */}
                      {adj && (
                        <div style={{ paddingTop: '10px', borderTop: '1px solid var(--color-rule)' }}>
                          <div className="editorial-kicker" style={{ marginBottom: '6px' }}>
                            IV. SPECIALIST DIALECTIC ADJUDICATION MATRIX
                          </div>
                          {typeof adj === 'object' ? (
                            <pre
                              style={{
                                margin: 0,
                                padding: '10px 12px',
                                background: 'var(--color-paper-raised)',
                                border: '1px solid var(--color-rule)',
                                fontSize: '11px',
                                fontFamily: 'var(--font-precision)',
                                color: 'var(--color-ink-soft)',
                                overflowX: 'auto',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                              }}
                            >
                              {JSON.stringify(adj, null, 2)}
                            </pre>
                          ) : (
                            <div style={{ fontSize: '12px', color: 'var(--color-ink-soft)', lineHeight: 1.6 }}>
                              {String(adj)}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div
            style={{
              textAlign: 'center',
              padding: '36px',
              border: '1px solid var(--color-rule)',
              color: 'var(--color-ink-muted)',
              fontFamily: 'var(--font-precision)',
              fontSize: '12px',
            }}
          >
            No dialectic debate outcomes found matching filter.
          </div>
        )}
      </div>
    </div>
  );
};

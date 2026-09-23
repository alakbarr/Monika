// ==============================================================================
// File: src/components/panels/MemoryBrowserPanel.tsx
// Description: Autonomous Memory Vault — Post-Trade Reflections & Empirical Playbook Lessons
// ==============================================================================

import React, { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { TypewriterButton } from '../ui/TypewriterButton';
import { api } from '../../lib/api';
import type { DecisionReflectionItem, CandidateLessonItem, MemorySearchResult, PlaybookRuleItem } from '../../types/api';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';
import {
  Brain,
  Search,
  Lightbulb,
  RefreshCw,
  BookOpen,
} from 'lucide-react';

type ViewMode = 'all' | 'profitable' | 'losses' | 'whatif' | 'lessons' | 'playbooks';

export const MemoryBrowserPanel: React.FC = () => {
  const [viewMode, setViewMode] = useState<ViewMode>('all');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [reflections, setReflections] = useState<DecisionReflectionItem[]>([]);
  const [lessons, setLessons] = useState<CandidateLessonItem[]>([]);
  const [playbooks, setPlaybooks] = useState<PlaybookRuleItem[]>([]);
  const [searchResults, setSearchResults] = useState<MemorySearchResult | null>(null);

  const fetchMemory = async () => {
    setLoading(true);
    try {
      if (searchQuery.trim().length >= 2) {
        const res = await api.memorySearch(searchQuery.trim(), selectedSymbol === 'ALL' ? undefined : selectedSymbol);
        setSearchResults(res);
      } else {
        setSearchResults(null);
        if (viewMode === 'playbooks') {
          const pData = await api.memoryPlaybooks(50);
          setPlaybooks(selectedSymbol === 'ALL' ? pData : pData.filter(p => p.symbol === selectedSymbol));
        } else if (viewMode === 'lessons') {
          const lData = await api.memoryLessons({
            symbol: selectedSymbol === 'ALL' ? undefined : selectedSymbol,
            limit: 50,
          });
          setLessons(lData);
        } else {
          const rData = await api.memoryReflections({
            symbol: selectedSymbol === 'ALL' ? undefined : selectedSymbol,
            profitable_only: viewMode === 'profitable' ? true : viewMode === 'losses' ? false : undefined,
            whatif_only: viewMode === 'whatif' ? true : undefined,
            limit: 50,
          });
          setReflections(rData);
        }
      }
    } catch (err) {
      console.error('Failed to load memory data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMemory();
  }, [viewMode, selectedSymbol]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sounds.playClick('typewriter');
    fetchMemory();
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults(null);
    sounds.playClick('toggle');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontFamily: 'var(--font-precision)' }}>
      {/* Header & Filter Card */}
      <Card padding="14px 18px" variant="yellow">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: '4px',
                background: 'var(--color-win-yellow)',
                border: '1.5px solid var(--color-rule)',
                boxShadow: '1.5px 1.5px 0 var(--color-rule)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#1C1917',
              }}
            >
              <Brain size={22} />
            </div>
            <div>
              <h3
                style={{
                  fontSize: 'var(--text-title-sm)',
                  fontWeight: 800,
                  color: 'var(--color-ink)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  margin: 0,
                }}
              >
                AUTONOMOUS MEMORY VAULT // REFLECTIONS & PLAYBOOK RULES
              </h3>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                Long-term episodic reflections, post-trade debriefs, and empirical lessons promoted from live execution.
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TypewriterButton size="sm" onClick={fetchMemory} disabled={loading} title="Refresh memory records">
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> [ REFRESH ]
            </TypewriterButton>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div
          style={{
            marginTop: '14px',
            paddingTop: '12px',
            borderTop: '1px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          {/* Mode Tabs */}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            <TypewriterButton
              size="sm"
              variant={viewMode === 'all' && !searchResults ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('all');
                clearSearch();
              }}
            >
              [ ALL REFLECTIONS ]
            </TypewriterButton>

            <TypewriterButton
              size="sm"
              variant={viewMode === 'profitable' ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('profitable');
                clearSearch();
              }}
            >
              [ WINNERS ]
            </TypewriterButton>

            <TypewriterButton
              size="sm"
              variant={viewMode === 'losses' ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('losses');
                clearSearch();
              }}
            >
              [ LOSERS & LESSONS ]
            </TypewriterButton>

            <TypewriterButton
              size="sm"
              variant={viewMode === 'whatif' ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('whatif');
                clearSearch();
              }}
            >
              [ WHAT-IFS ]
            </TypewriterButton>

            <TypewriterButton
              size="sm"
              variant={viewMode === 'lessons' ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('lessons');
                clearSearch();
              }}
            >
              <Lightbulb size={12} /> [ CANDIDATE LESSONS ]
            </TypewriterButton>

            <TypewriterButton
              size="sm"
              variant={viewMode === 'playbooks' ? 'primary' : 'secondary'}
              onClick={() => {
                setViewMode('playbooks');
                clearSearch();
              }}
            >
              <BookOpen size={12} /> [ PLAYBOOK RULES ]
            </TypewriterButton>
          </div>

          {/* Symbol Select & Search Box */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              style={{
                height: '28px',
                padding: '0 8px',
                background: 'var(--color-paper-raised)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-ink)',
                fontSize: 'var(--text-xs)',
                fontWeight: 700,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="ALL">ALL ASSETS</option>
              <option value="XAUUSD">XAUUSD</option>
              <option value="EURUSD">EURUSD</option>
              <option value="GBPUSD">GBPUSD</option>
              <option value="USDJPY">USDJPY</option>
              <option value="AUDUSD">AUDUSD</option>
              <option value="BTCUSD">BTCUSD</option>
            </select>

            <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search reflections & lessons..."
                style={{
                  height: '28px',
                  width: '210px',
                  padding: '0 8px',
                  background: 'var(--color-paper-raised)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-xs)',
                  outline: 'none',
                }}
              />
              <TypewriterButton size="sm" type="submit">
                <Search size={12} />
              </TypewriterButton>
              {searchQuery && (
                <TypewriterButton size="sm" onClick={clearSearch}>
                  ✕
                </TypewriterButton>
              )}
            </form>
          </div>
        </div>
      </Card>

      {/* Main Content Feed */}
      {loading ? (
        <Card padding="36px" variant="gray">
          <div style={{ textAlign: 'center', color: 'var(--color-ink-soft)' }}>
            Retrieving memory records from long-term database...
          </div>
        </Card>
      ) : searchResults ? (
        /* Unified Search Results View */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 700 }}>
            SEARCH RESULTS FOR "{searchResults.query}": {searchResults.total_matches} TOTAL MATCHES
          </div>

          {searchResults.reflections.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span className="stamp-badge" style={{ width: 'fit-content' }}>
                MATCHING REFLECTIONS ({searchResults.reflections.length})
              </span>
              {searchResults.reflections.map((r) => (
                <Card key={`search-ref-${r.id}`} padding="12px 16px" variant="gray">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge variant="active">{r.symbol}</Badge>
                      <Badge variant={r.decision === 'buy' ? 'active' : 'warn'}>{r.decision.toUpperCase()}</Badge>
                      {r.outcome_pnl_usd !== null && r.outcome_pnl_usd !== undefined && (
                        <span style={{ fontWeight: 800, color: r.outcome_pnl_usd >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                          {fmt.usd(r.outcome_pnl_usd, true)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: '1.5' }}>
                    {r.reflection_text || r.specific_lesson || 'No detailed text available.'}
                  </div>
                  {r.next_trade_adjustment && (
                    <div style={{ marginTop: '6px', fontSize: 'var(--text-xs)', color: 'var(--color-brass)' }}>
                      <strong>Rule Adjustment:</strong> {r.next_trade_adjustment}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          {searchResults.lessons.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '10px' }}>
              <span className="stamp-badge" style={{ width: 'fit-content' }}>
                MATCHING CANDIDATE LESSONS ({searchResults.lessons.length})
              </span>
              {searchResults.lessons.map((l) => (
                <Card key={`search-les-${l.id}`} padding="12px 16px" variant="yellow">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge variant="active">{l.symbol}</Badge>
                      <Badge variant={l.status === 'promoted' ? 'active' : l.status === 'shadow' ? 'warn' : 'neutral'}>
                        {l.status.toUpperCase()}
                      </Badge>
                    </div>
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ledger-green)' }}>
                      WR Δ: {(l.win_rate_delta * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)' }}>{l.lesson_text}</div>
                </Card>
              ))}
            </div>
          )}

          {searchResults.total_matches === 0 && (
            <Card padding="32px" variant="gray">
              <div style={{ textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                No memory entries matched the search query.
              </div>
            </Card>
          )}
        </div>
      ) : viewMode === 'lessons' ? (
        /* Candidate Lessons View */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {lessons.length === 0 ? (
            <Card padding="36px" variant="gray">
              <div style={{ textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                — No empirical candidate lessons currently recorded for {selectedSymbol} —
              </div>
            </Card>
          ) : (
            lessons.map((lesson) => (
              <Card key={lesson.id} padding="14px 18px" variant="yellow">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Badge variant="active">{lesson.symbol}</Badge>
                    <Badge variant={lesson.status === 'promoted' ? 'active' : lesson.status === 'shadow' ? 'warn' : 'neutral'}>
                      {lesson.status.toUpperCase()}
                    </Badge>
                    {lesson.condition_tags && (
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                        TAGS: {lesson.condition_tags}
                      </span>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: 'var(--text-xs)' }}>
                    <span>
                      Trades: <strong>{lesson.evaluated_trades_count}</strong>
                    </span>
                    <span style={{ color: lesson.win_rate_delta >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)', fontWeight: 800 }}>
                      Win Rate Δ: {(lesson.win_rate_delta * 100).toFixed(1)}%
                    </span>
                    <span style={{ color: 'var(--color-ink-soft)' }}>
                      Sharpe Δ: {lesson.sharpe_delta.toFixed(2)}
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: '1.6', fontWeight: 500 }}>
                  {lesson.lesson_text}
                </div>

                {lesson.rejection_reason && (
                  <div style={{ marginTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-ledger-red)' }}>
                    <strong>Rejection Reason:</strong> {lesson.rejection_reason}
                  </div>
                )}
              </Card>
            ))
          )}
        </div>
      ) : viewMode === 'playbooks' ? (
        /* Playbook Rules View */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {playbooks.length === 0 ? (
            <Card padding="36px" variant="gray">
              <div style={{ textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                — No empirical playbook rules currently active for {selectedSymbol} —
              </div>
            </Card>
          ) : (
            playbooks.map((rule) => {
              const statusVariant = rule.status === 'golden' ? 'active' : rule.status === 'deprecated' ? 'neutral' : 'warn';
              return (
                <Card key={rule.id} padding="14px 18px" variant={rule.status === 'golden' ? 'green' : rule.status === 'deprecated' ? 'gray' : 'yellow'}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge variant="active">{rule.symbol}</Badge>
                      <Badge variant={statusVariant}>{rule.status.toUpperCase()}</Badge>
                      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', fontFamily: 'monospace' }}>
                        #{rule.rule_hash.substring(0, 8)}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: 'var(--text-xs)' }}>
                      <span>
                        Triggers: <strong>{rule.times_triggered}</strong>
                      </span>
                      <span>
                        Wins / Losses: <strong style={{ color: 'var(--color-ledger-green)' }}>{rule.wins_count}</strong> / <strong style={{ color: 'var(--color-ledger-red)' }}>{rule.losses_count}</strong>
                      </span>
                      <span style={{ fontWeight: 800, color: rule.win_rate >= 0.5 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                        Win Rate: {(rule.win_rate * 100).toFixed(1)}%
                      </span>
                      <span style={{ fontWeight: 800, color: rule.total_pnl >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                        PnL: {fmt.usd(rule.total_pnl, true)}
                      </span>
                    </div>
                  </div>

                  <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: '1.6', fontWeight: 500 }}>
                    {rule.rule_text}
                  </div>

                  {rule.deprecated_at && rule.deprecation_reason && (
                    <div style={{ marginTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-ledger-red)' }}>
                      <strong>Deprecated ({new Date(rule.deprecated_at).toLocaleDateString()}):</strong> {rule.deprecation_reason}
                    </div>
                  )}

                  {rule.last_triggered_at && (
                    <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--color-ink-muted)' }}>
                      Last Triggered: {new Date(rule.last_triggered_at).toLocaleString()}
                    </div>
                  )}
                </Card>
              );
            })
          )}
        </div>
      ) : (
        /* Reflections View */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {reflections.length === 0 ? (
            <Card padding="36px" variant="gray">
              <div style={{ textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                — No decision reflections matching current filter criteria —
              </div>
            </Card>
          ) : (
            reflections.map((ref) => {
              const isWin = ref.outcome_pnl_usd && ref.outcome_pnl_usd > 0;
              const cardVariant = isWin ? 'green' : ref.is_paper_whatif ? 'yellow' : 'salmon';

              return (
                <Card key={ref.id} padding="14px 18px" variant={cardVariant}>
                  {/* Top Bar */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge variant="active">{ref.symbol}</Badge>
                      <Badge variant={ref.decision === 'buy' ? 'active' : 'warn'}>
                        {ref.decision.toUpperCase()}
                      </Badge>

                      {ref.is_paper_whatif ? (
                        <Badge variant="warn">[ WHAT-IF: {ref.whatif_reason || 'UNEXECUTED'} ]</Badge>
                      ) : (
                        <span
                          style={{
                            fontWeight: 800,
                            fontSize: 'var(--text-body-sm)',
                            color: isWin ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                          }}
                        >
                          {fmt.usd(ref.outcome_pnl_usd || 0, true)}
                        </span>
                      )}

                      {ref.alpha_return !== null && ref.alpha_return !== undefined && (
                        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: ref.alpha_return >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                          α: {(ref.alpha_return * 100).toFixed(2)}%
                        </span>
                      )}

                      {ref.exit_reason && (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                          · Exit: {ref.exit_reason}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {ref.outcome_process_classification && (
                        <span className="stamp-badge" style={{ fontSize: '9px' }}>
                          [{ref.outcome_process_classification.toUpperCase()}]
                        </span>
                      )}

                      {ref.macro_thesis_correct !== null && ref.macro_thesis_correct !== undefined && (
                        <Badge variant={ref.macro_thesis_correct ? 'active' : 'warn'}>
                          {ref.macro_thesis_correct ? 'THESIS CORRECT' : 'THESIS FAILED'}
                        </Badge>
                      )}

                      {ref.process_was_sound !== null && ref.process_was_sound !== undefined && (
                        <Badge variant={ref.process_was_sound ? 'active' : 'warn'}>
                          {ref.process_was_sound ? 'SOUND PROCESS' : 'FLAWED PROCESS'}
                        </Badge>
                      )}

                      {ref.debate_verdict && (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                          DEBATE: <strong>{ref.debate_verdict.toUpperCase()}</strong>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Original Rationale */}
                  {ref.rationale_summary && (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginBottom: '8px' }}>
                      <strong>Original Thesis:</strong> {ref.rationale_summary}
                    </div>
                  )}

                  {/* AI Reflection & Specific Lesson */}
                  <div
                    style={{
                      background: 'var(--color-paper-raised)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '10px 12px',
                      fontSize: 'var(--text-body-sm)',
                      lineHeight: '1.5',
                      color: 'var(--color-ink)',
                    }}
                  >
                    {ref.reflection_text && <div>{ref.reflection_text}</div>}
                    {ref.specific_lesson && (
                      <div style={{ marginTop: ref.reflection_text ? '6px' : 0, fontWeight: 600 }}>
                        <span style={{ color: 'var(--color-brass)' }}>💡 LESSON:</span> {ref.specific_lesson}
                      </div>
                    )}
                  </div>

                  {/* Rule Adjustment */}
                  {ref.next_trade_adjustment && (
                    <div style={{ marginTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-brass)' }}>
                      <strong>NEXT TRADE ADJUSTMENT:</strong> {ref.next_trade_adjustment}
                    </div>
                  )}
                </Card>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

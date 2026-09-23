// ==============================================================================
// File: src/components/panels/SkillManagerPanel.tsx
// Description: Autonomous Skill Crystallizer & Lifecycle Management Panel
// ==============================================================================

import React, { useEffect, useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { ConfirmModal } from '../ui/ConfirmModal';
import { Skeleton } from '../ui/Skeleton';
import { api } from '../../lib/api';
import type { CrystallizedSkillItem, SkillStatsItem } from '../../types/api';
import { fmt } from '../../lib/formatters';
import { sounds } from '../../lib/soundEffects';
import {
  Sparkles,
  Scissors,
  RefreshCw,
  FileCode,
} from 'lucide-react';

export const SkillManagerPanel: React.FC = () => {
  const [skills, setSkills] = useState<CrystallizedSkillItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterSymbol, setFilterSymbol] = useState<string>('ALL');
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'deprecated'>('all');
  const [selectedStats, setSelectedStats] = useState<SkillStatsItem | null>(null);
  const [deprecatingSkill, setDeprecatingSkill] = useState<string | null>(null);
  const [curating, setCurating] = useState<boolean>(false);
  const [crystallizing, setCrystallizing] = useState<boolean>(false);
  const [actionMsg, setActionMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const fetchSkills = async () => {
    setLoading(true);
    setActionMsg(null);
    try {
      const res = await api.skillsCrystallized();
      setSkills(res.skills || []);
    } catch (err: any) {
      console.error('Failed to load crystallized skills:', err);
      setActionMsg({ type: 'err', text: err.message || 'Failed to fetch crystallized skills' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const handleCurate = async () => {
    setCurating(true);
    setActionMsg(null);
    sounds.playClick('typewriter');
    try {
      const res = await api.skillCurate();
      setActionMsg({
        type: 'ok',
        text: `Curation complete: ${res.pruned_count} degraded skill(s) evaluated/pruned.`,
      });
      await fetchSkills();
    } catch (err: any) {
      setActionMsg({ type: 'err', text: err.message || 'Curation failed' });
    } finally {
      setCurating(false);
    }
  };

  const handleCrystallize = async () => {
    setCrystallizing(true);
    setActionMsg(null);
    sounds.playClick('typewriter');
    try {
      const sym = filterSymbol !== 'ALL' ? filterSymbol : undefined;
      const res = await api.skillCrystallize(sym);
      setActionMsg({
        type: 'ok',
        text: `Crystallization finished: ${res.count} skill(s) synthesized or updated.`,
      });
      await fetchSkills();
    } catch (err: any) {
      setActionMsg({ type: 'err', text: err.message || 'Crystallization failed' });
    } finally {
      setCrystallizing(false);
    }
  };

  const handleOpenStats = async (skillName: string) => {
    sounds.playClick('typewriter');
    try {
      const data = await api.skillStats(skillName);
      setSelectedStats(data);
    } catch (err: any) {
      setActionMsg({ type: 'err', text: `Failed to fetch stats: ${err.message}` });
    }
  };

  const handleConfirmDeprecate = async () => {
    if (!deprecatingSkill) return;
    sounds.playClick('toggle');
    try {
      await api.skillDeprecate(deprecatingSkill, 'Operator manual deprecation from dashboard');
      setActionMsg({
        type: 'ok',
        text: `Skill '${deprecatingSkill}' marked as deprecated.`,
      });
      setDeprecatingSkill(null);
      await fetchSkills();
    } catch (err: any) {
      setActionMsg({ type: 'err', text: `Failed to deprecate: ${err.message}` });
    }
  };

  // Aggregated metrics
  const activeCount = skills.filter((s) => !s.is_deprecated && s.status === 'active').length;
  const deprecatedCount = skills.filter((s) => s.is_deprecated || s.status === 'deprecated').length;
  const totalPnl = skills.reduce((acc, s) => acc + (s.total_pnl_usd || 0), 0);

  // Filter skills
  const symbols = ['ALL', ...Array.from(new Set(skills.map((s) => s.symbol).filter(Boolean)))];
  const displayedSkills = skills.filter((s) => {
    const matchSym = filterSymbol === 'ALL' || s.symbol.toUpperCase() === filterSymbol.toUpperCase();
    const isDep = s.is_deprecated || s.status === 'deprecated';
    const matchStatus =
      filterStatus === 'all' ||
      (filterStatus === 'active' && !isDep) ||
      (filterStatus === 'deprecated' && isDep);
    return matchSym && matchStatus;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Overview Metric Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
        <Card variant="gray" style={{ padding: '12px' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>
            TOTAL CRYSTALLIZED
          </div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'var(--font-precision)', marginTop: '4px' }}>
            {skills.length} <span style={{ fontSize: '14px', color: 'var(--color-ink-soft)' }}>playbooks</span>
          </div>
        </Card>

        <Card variant="gray" style={{ padding: '12px' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>
            ACTIVE INSTITUTIONAL
          </div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: 'var(--color-ledger-green)', marginTop: '4px' }}>
            {activeCount} <span style={{ fontSize: '14px', color: 'var(--color-ink-soft)' }}>in rotation</span>
          </div>
        </Card>

        <Card variant="gray" style={{ padding: '12px' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>
            PRUNED / DEPRECATED
          </div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: 'var(--color-ledger-red)', marginTop: '4px' }}>
            {deprecatedCount} <span style={{ fontSize: '14px', color: 'var(--color-ink-soft)' }}>skills</span>
          </div>
        </Card>

        <Card variant="gray" style={{ padding: '12px' }}>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontWeight: 'bold' }}>
            PORTFOLIO P&L ATTRIBUTION
          </div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: totalPnl >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)', marginTop: '4px' }}>
            {fmt.usd(totalPnl)}
          </div>
        </Card>
      </div>

      {/* Main Vault Window */}
      <WindowFrame
        title="AUTONOMOUS SKILL CRYSTALLIZER & LIFECYCLE LEDGER"
        icon={<Sparkles size={18} />}
        variant="yellow"
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              onClick={handleCrystallize}
              disabled={crystallizing}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: 700,
                background: 'var(--color-win-yellow)',
                color: '#1C1917',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                cursor: crystallizing ? 'not-allowed' : 'pointer',
              }}
              title="Scan resolved winning trades and formalize qualifying setups into crystallized skills"
            >
              <Sparkles size={13} />
              {crystallizing ? 'CRYSTALLIZING...' : 'EVAL & CRYSTALLIZE'}
            </button>

            <button
              type="button"
              onClick={handleCurate}
              disabled={curating}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: 700,
                background: 'var(--color-paper-raised)',
                color: 'var(--color-ink)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                cursor: curating ? 'not-allowed' : 'pointer',
              }}
              title="Evaluate attribution across recent trades and prune degraded skills below 50% win rate"
            >
              <Scissors size={13} />
              {curating ? 'PRUNING...' : 'CURATE & PRUNE'}
            </button>

            <button
              type="button"
              onClick={fetchSkills}
              disabled={loading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '4px 8px',
                fontSize: 'var(--text-xs)',
                background: 'var(--color-paper-raised)',
                color: 'var(--color-ink)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '2px',
                cursor: 'pointer',
              }}
              title="Refresh skills catalog"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        }
      >
        {/* Status / Notice banner */}
        {actionMsg && (
          <div
            style={{
              padding: '8px 14px',
              background: actionMsg.type === 'ok' ? 'color-mix(in srgb, var(--color-paper-raised) 90%, var(--color-ledger-green))' : 'color-mix(in srgb, var(--color-paper-raised) 90%, var(--color-ledger-red))',
              borderBottom: '1.5px solid var(--color-rule)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-precision)',
              fontWeight: 600,
              color: actionMsg.type === 'ok' ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
            }}
          >
            {actionMsg.type === 'ok' ? '✓ ' : '⚠ '}
            {actionMsg.text}
          </div>
        )}

        {/* Filter Toolbar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-paper-raised)',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>SYMBOL:</span>
            <div style={{ display: 'inline-flex', gap: '4px', flexWrap: 'wrap' }}>
              {symbols.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => setFilterSymbol(sym)}
                  style={{
                    padding: '2px 8px',
                    fontSize: '11px',
                    fontFamily: 'var(--font-precision)',
                    fontWeight: filterSymbol === sym ? 700 : 500,
                    background: filterSymbol === sym ? 'var(--color-win-yellow)' : 'var(--color-paper)',
                    color: filterSymbol === sym ? '#1C1917' : 'var(--color-ink)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    cursor: 'pointer',
                  }}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>STATUS:</span>
            {(['all', 'active', 'deprecated'] as const).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setFilterStatus(st)}
                style={{
                  padding: '2px 8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: filterStatus === st ? 700 : 500,
                  textTransform: 'uppercase',
                  background: filterStatus === st ? 'var(--color-win-yellow)' : 'var(--color-paper)',
                  color: filterStatus === st ? '#1C1917' : 'var(--color-ink)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  cursor: 'pointer',
                }}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* Content Table / List */}
        {loading ? (
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} height="52px" />
            ))}
          </div>
        ) : displayedSkills.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>
            — No crystallized procedural skills match current filters —
          </div>
        ) : (
          <div className="table-responsive" style={{ maxHeight: '600px', overflowY: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontFamily: 'var(--font-precision)',
                fontSize: 'var(--text-body-sm)',
              }}
            >
              <thead
                style={{
                  position: 'sticky',
                  top: 0,
                  zIndex: 10,
                  background: 'color-mix(in srgb, var(--color-paper-raised) 90%, var(--color-ink))',
                  borderBottom: '2px solid var(--color-rule)',
                }}
              >
                <tr>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Skill / File
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Symbol
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Status
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Win Rate
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Attributed P&L
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase', borderRight: '1px solid var(--color-rule)' }}>
                    Crystallized
                  </th>
                  <th style={{ padding: '8px 12px', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink)', textTransform: 'uppercase' }}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {displayedSkills.map((sk, idx) => {
                  const isDep = sk.is_deprecated || sk.status === 'deprecated';
                  const isEven = idx % 2 === 1;
                  return (
                    <tr
                      key={sk.name}
                      style={{
                        background: isEven
                          ? 'color-mix(in srgb, var(--color-paper-raised) 92%, var(--color-ledger-green))'
                          : 'var(--color-paper-raised)',
                        borderBottom: '1px solid var(--color-rule)',
                        opacity: isDep ? 0.75 : 1,
                      }}
                    >
                      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
                        <div style={{ fontWeight: 'bold', color: 'var(--color-ink)' }}>{sk.name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <FileCode size={11} /> {sk.file}
                        </div>
                        {sk.description && (
                          <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', marginTop: '2px', maxWidth: '380px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {sk.description}
                          </div>
                        )}
                      </td>

                      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', fontWeight: 'bold' }}>
                        {sk.symbol}
                      </td>

                      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
                        <Badge variant={isDep ? 'loss' : 'active'}>
                          {isDep ? 'DEPRECATED' : 'ACTIVE'}
                        </Badge>
                        {sk.deprecation_reason && (
                          <div style={{ fontSize: '10px', color: 'var(--color-ledger-red)', marginTop: '2px' }}>
                            {sk.deprecation_reason}
                          </div>
                        )}
                      </td>

                      <td className="tabular-nums" style={{ padding: '8px 12px', textAlign: 'right', borderRight: '1px solid var(--color-rule)', fontWeight: 'bold' }}>
                        <div>{(sk.win_rate * 100).toFixed(1)}%</div>
                        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
                          {sk.win_count}W / {sk.total_trades}T
                        </div>
                      </td>

                      <td className="tabular-nums" style={{ padding: '8px 12px', textAlign: 'right', borderRight: '1px solid var(--color-rule)', fontWeight: 'bold', color: sk.total_pnl_usd >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                        {fmt.usd(sk.total_pnl_usd)}
                      </td>

                      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', fontSize: '11px', color: 'var(--color-ink-soft)', whiteSpace: 'nowrap' }}>
                        {sk.last_crystallized_at ? fmt.datetime(sk.last_crystallized_at) : '—'}
                      </td>

                      <td style={{ padding: '6px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                        <button
                          type="button"
                          onClick={() => handleOpenStats(sk.name)}
                          style={{
                            padding: '2px 8px',
                            marginRight: '6px',
                            fontSize: '11px',
                            fontFamily: 'var(--font-precision)',
                            fontWeight: 'bold',
                            background: 'var(--color-paper)',
                            color: 'var(--color-ink)',
                            border: '1px solid var(--color-rule)',
                            borderRadius: '2px',
                            cursor: 'pointer',
                          }}
                          title="View empirical performance and recent trade attributions"
                        >
                          STATS
                        </button>

                        {!isDep && (
                          <button
                            type="button"
                            onClick={() => setDeprecatingSkill(sk.name)}
                            style={{
                              padding: '2px 8px',
                              fontSize: '11px',
                              fontFamily: 'var(--font-precision)',
                              fontWeight: 'bold',
                              background: 'var(--color-loss-dim)',
                              color: 'var(--color-ledger-red)',
                              border: '1px solid var(--color-ledger-red)',
                              borderRadius: '2px',
                              cursor: 'pointer',
                            }}
                            title="Manually deprecate this crystallized skill"
                          >
                            PRUNE
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </WindowFrame>

      {/* Stats Modal */}
      {selectedStats && (
        <ConfirmModal
          isOpen={Boolean(selectedStats)}
          title={`SKILL ATTRIBUTION STATS: ${selectedStats.skill_name.toUpperCase()}`}
          actionSummary={`EMPIRICAL TRACK RECORD`}
          details={
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: 'var(--text-body-sm)' }}>
              <div><strong>Skill Name:</strong> {selectedStats.skill_name}</div>
              <div><strong>Status:</strong> {selectedStats.status.toUpperCase()}</div>
              <div><strong>Times Triggered:</strong> {selectedStats.times_triggered}</div>
              <div><strong>Wins / Losses:</strong> {selectedStats.wins_count} W / {selectedStats.losses_count} L</div>
              <div><strong>Overall Win Rate:</strong> {(selectedStats.win_rate * 100).toFixed(1)}%</div>
              {selectedStats.recent_win_rate !== undefined && (
                <div><strong>Recent Win Rate:</strong> {(selectedStats.recent_win_rate * 100).toFixed(1)}%</div>
              )}
              <div><strong>Cumulative P&L:</strong> {fmt.usd(selectedStats.total_pnl)}</div>

              {selectedStats.recent_outcomes && selectedStats.recent_outcomes.length > 0 && (
                <div>
                  <strong>Recent 10 Outcomes:</strong>
                  <div style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
                    {selectedStats.recent_outcomes.map((won, idx) => (
                      <span
                        key={idx}
                        style={{
                          padding: '2px 6px',
                          fontSize: '10px',
                          fontWeight: 'bold',
                          borderRadius: '2px',
                          background: won ? 'var(--color-win-dim)' : 'var(--color-loss-dim)',
                          color: won ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                          border: `1px solid ${won ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)'}`,
                        }}
                      >
                        {won ? 'W' : 'L'}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {selectedStats.deprecation_reason && (
                <div style={{ color: 'var(--color-ledger-red)', fontSize: '11px', marginTop: '6px' }}>
                  <strong>Pruning Reason:</strong> {selectedStats.deprecation_reason}
                </div>
              )}
            </div>
          }
          confirmLabel="DISMISS"
          cancelLabel="CLOSE"
          danger={false}
          onConfirm={() => setSelectedStats(null)}
          onCancel={() => setSelectedStats(null)}
        />
      )}

      {/* Deprecate Skill Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(deprecatingSkill)}
        title="PRUNE / DEPRECATE SKILL"
        actionSummary={`DEPRECATE: ${deprecatingSkill}`}
        details={
          <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)' }}>
            Are you sure you want to deprecate <strong>{deprecatingSkill}</strong>?
            <p style={{ margin: '8px 0 0', color: 'var(--color-ledger-red)', fontSize: 'var(--text-xs)' }}>
              This marks the skill file as deprecated, excluding it from Stage 2 PromptAssembler and future trade plans.
            </p>
          </div>
        }
        confirmLabel="CONFIRM DEPRECATION"
        cancelLabel="CANCEL"
        danger={true}
        onConfirm={handleConfirmDeprecate}
        onCancel={() => setDeprecatingSkill(null)}
      />
    </div>
  );
};

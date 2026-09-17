import React from 'react';
import { Card } from '../../ui/Card';
import { Badge } from '../../ui/Badge';
import { Coins, Search } from 'lucide-react';
import type { TokenRoleItem } from '../../../types/api';

interface TokenRoleTableProps {
  filteredAndSortedRoles: TokenRoleItem[];
  maxRoleTokens: number;
  roleSortKey: keyof TokenRoleItem;
  roleSortAsc: boolean;
  toggleRoleSort: (key: keyof TokenRoleItem) => void;
  roleSearch: string;
  setRoleSearch: (s: string) => void;
  subsystemFilter: string;
  setSubsystemFilter: (s: string) => void;
  availableSubsystems: string[];
  renderSortIcon: (current: string, key: string, asc: boolean) => React.ReactNode;
}

export const TokenRoleTable: React.FC<TokenRoleTableProps> = ({
  filteredAndSortedRoles,
  maxRoleTokens,
  roleSortKey,
  roleSortAsc,
  toggleRoleSort,
  roleSearch,
  setRoleSearch,
  subsystemFilter,
  setSubsystemFilter,
  availableSubsystems,
  renderSortIcon,
}) => {
  return (
    <Card
      className="ledger-card"
      header={
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            width: '100%',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Coins size={16} color="var(--color-brass)" />
            <span style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', fontSize: '12px' }}>
              Task Role Consumption Breakdown
            </span>
            <Badge variant="neutral">{filteredAndSortedRoles.length} roles</Badge>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Search */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                height: '26px',
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
                placeholder="Filter role..."
                value={roleSearch}
                onChange={(e) => setRoleSearch(e.target.value)}
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

            {/* Subsystem filter */}
            <select
              value={subsystemFilter}
              onChange={(e) => setSubsystemFilter(e.target.value)}
              style={{
                height: '26px',
                boxSizing: 'border-box',
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--color-surface)',
                color: 'var(--color-ink)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                padding: '0 8px',
                fontSize: '11px',
                outline: 'none',
                cursor: 'pointer',
                fontFamily: 'var(--font-precision)',
              }}
            >
              <option value="all">All Subsystems</option>
              {availableSubsystems.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
      }
    >
      <div style={{ overflowX: 'auto' }}>
        <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr>
              <th
                onClick={() => toggleRoleSort('task_role')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  Role / Subsystem {renderSortIcon(roleSortKey, 'task_role', roleSortAsc)}
                </div>
              </th>
              <th
                onClick={() => toggleRoleSort('calls')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  Calls {renderSortIcon(roleSortKey, 'calls', roleSortAsc)}
                </div>
              </th>
              <th
                onClick={() => toggleRoleSort('sum_total')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  Total Tokens (Bar) {renderSortIcon(roleSortKey, 'sum_total', roleSortAsc)}
                </div>
              </th>
              <th>Avg In / Out</th>
              <th
                onClick={() => toggleRoleSort('thinking_pct')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  Thinking % {renderSortIcon(roleSortKey, 'thinking_pct', roleSortAsc)}
                </div>
              </th>
              <th
                onClick={() => toggleRoleSort('avg_latency_ms')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  Avg Latency {renderSortIcon(roleSortKey, 'avg_latency_ms', roleSortAsc)}
                </div>
              </th>
              <th
                onClick={() => toggleRoleSort('sum_cost_usd')}
                style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                  Total Cost {renderSortIcon(roleSortKey, 'sum_cost_usd', roleSortAsc)}
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredAndSortedRoles.length > 0 ? (
              filteredAndSortedRoles.map((r) => {
                const roleBarPct = Math.min(100, Math.max(2, (r.sum_total / maxRoleTokens) * 100));
                return (
                  <tr key={`${r.task_role}-${r.subsystem}`}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--color-ink)' }}>{r.task_role}</div>
                      <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>{r.subsystem}</div>
                    </td>
                    <td style={{ color: 'var(--color-ink-muted)' }}>
                      {r.calls}
                      {r.fallback_calls > 0 && (
                        <span style={{ color: 'var(--color-warning)', fontSize: '10px', marginLeft: '4px' }}>
                          ({r.fallback_calls} fb)
                        </span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        <span>{r.sum_total.toLocaleString()}</span>
                        <div style={{ height: '2px', background: 'var(--color-rule)', borderRadius: '1px', overflow: 'hidden', width: '100px' }}>
                          <div style={{ width: `${roleBarPct}%`, height: '100%', background: 'var(--color-brass)', borderRadius: '1px' }} />
                        </div>
                      </div>
                    </td>
                    <td style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                      {(r.avg_input ?? 0).toFixed(0)} / {(r.avg_output ?? 0).toFixed(0)}
                    </td>
                    <td>
                      <span
                        style={{
                          color: (r.thinking_pct ?? 0) > 30 ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                          fontWeight: (r.thinking_pct ?? 0) > 30 ? 600 : 400,
                        }}
                      >
                        {(r.thinking_pct ?? 0).toFixed(1)}%
                      </span>
                    </td>
                    <td style={{ fontSize: '11px', color: 'var(--color-ink-muted)' }}>
                      {(r.avg_latency_ms ?? 0).toFixed(0)} ms
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--color-brass)', fontWeight: 600 }}>
                      ${(r.sum_cost_usd ?? 0).toFixed(5)}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: 'var(--color-ink-muted)' }}>
                  No roles match the selected filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

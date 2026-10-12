import React from 'react';
import { Card } from '../../ui/Card';
import { Cpu } from 'lucide-react';
import type { TokenSubsystemItem, TokenSymbolItem } from '../../../types/api';

interface TokenChartsProps {
  subsystems: TokenSubsystemItem[];
  sortedSymbols: TokenSymbolItem[];
  maxSymTokens: number;
  symSortKey: keyof TokenSymbolItem;
  symSortAsc: boolean;
  toggleSymSort: (key: keyof TokenSymbolItem) => void;
  renderSortIcon: (current: string, key: string, asc: boolean) => React.ReactNode;
}

export const TokenCharts: React.FC<TokenChartsProps> = ({
  subsystems,
  sortedSymbols,
  maxSymTokens,
  symSortKey,
  symSortAsc,
  toggleSymSort,
  renderSortIcon,
}) => {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
      {/* Subsystems Breakdown */}
      <Card
        header={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cpu size={18} color="var(--color-brass)" />
            <span style={{ fontWeight: 600, fontFamily: 'var(--font-precision)' }}>
              [ SUBSYSTEM TOKEN & COST BREAKDOWN ]
            </span>
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {subsystems.length > 0 ? (
            subsystems.map((sub) => (
              <div key={sub.subsystem} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                    {sub.subsystem.toUpperCase()}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-precision)',
                      fontVariantNumeric: 'tabular-nums',
                      color: 'var(--color-ink-muted)',
                    }}
                  >
                    ${(sub.sum_cost_usd ?? 0).toFixed(4)} ({sub.pct_cost ?? 0}%) • {(sub.sum_total ?? 0).toLocaleString()} tok ({sub.pct_tokens ?? 0}%)
                  </span>
                </div>
                <div
                  style={{
                    height: '6px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, Math.max(2, sub.pct_cost))}%`,
                      height: '100%',
                      background: 'var(--color-brass)',
                      borderRadius: '1px',
                    }}
                  />
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '11px',
                    color: 'var(--color-ink-muted)',
                    fontFamily: 'var(--font-precision)',
                  }}
                >
                  <span>{sub.calls} calls</span>
                  <span>Cached: {sub.sum_cached.toLocaleString()} tokens</span>
                </div>
              </div>
            ))
          ) : (
            <div
              style={{
                color: 'var(--color-ink-muted)',
                fontSize: '13px',
                textAlign: 'center',
                padding: '24px',
                fontFamily: 'var(--font-precision)',
              }}
            >
              No subsystem data recorded in this time window.
            </div>
          )}
        </div>
      </Card>

      {/* Currency Symbol Attribution (Sortable Table) */}
      <Card
        title="PER-SYMBOL COST ATTRIBUTION"
        variant="yellow"
      >
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
            [ Click column header to sort ]
          </span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="ledger-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr>
                <th
                  onClick={() => toggleSymSort('symbol')}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    Symbol {renderSortIcon(symSortKey, 'symbol', symSortAsc)}
                  </div>
                </th>
                <th
                  onClick={() => toggleSymSort('calls')}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    Calls {renderSortIcon(symSortKey, 'calls', symSortAsc)}
                  </div>
                </th>
                <th
                  onClick={() => toggleSymSort('sum_total')}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    Total Tokens {renderSortIcon(symSortKey, 'sum_total', symSortAsc)}
                  </div>
                </th>
                <th
                  onClick={() => toggleSymSort('sum_thinking')}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    Thinking {renderSortIcon(symSortKey, 'sum_thinking', symSortAsc)}
                  </div>
                </th>
                <th
                  onClick={() => toggleSymSort('sum_cost_usd')}
                  style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                    Cost (USD) {renderSortIcon(symSortKey, 'sum_cost_usd', symSortAsc)}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedSymbols.length > 0 ? (
                sortedSymbols.map((sym) => {
                  const barPct = Math.min(100, Math.max(2, (sym.sum_total / maxSymTokens) * 100));
                  return (
                    <tr key={sym.symbol}>
                      <td style={{ fontWeight: 600, color: 'var(--color-ink)' }}>
                        {sym.symbol}
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)' }}>{sym.calls}</td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span>{sym.sum_total.toLocaleString()}</span>
                          <div
                            style={{
                              height: '2px',
                              background: 'var(--color-rule)',
                              borderRadius: '1px',
                              overflow: 'hidden',
                              width: '80px',
                            }}
                          >
                            <div
                              style={{
                                width: `${barPct}%`,
                                height: '100%',
                                background: 'var(--color-brass)',
                                borderRadius: '1px',
                              }}
                            />
                          </div>
                        </div>
                      </td>
                      <td style={{ color: 'var(--color-ink-muted)' }}>
                        {sym.sum_thinking.toLocaleString()}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-brass)', fontWeight: 600 }}>
                        ${(sym.sum_cost_usd ?? 0).toFixed(4)}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: 'var(--color-ink-muted)' }}>
                    No per-symbol activity found.
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

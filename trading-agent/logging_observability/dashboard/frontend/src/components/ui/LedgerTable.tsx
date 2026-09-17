import React from 'react';

export interface ColumnDef<T> {
  key: string;
  label: string;
  align?: 'left' | 'right' | 'center';
  width?: string;
  render?: (value: any, row: T, index: number) => React.ReactNode;
}

interface LedgerTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  keyField?: string;
  greenbar?: boolean;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  style?: React.CSSProperties;
}

export function LedgerTable<T extends Record<string, any>>({
  columns,
  data,
  keyField = 'id',
  greenbar = true,
  onRowClick,
  emptyMessage = 'No ledger entries recorded.',
  style,
}: LedgerTableProps<T>) {
  return (
    <div
      className="table-responsive win-window"
      style={{
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        background: 'var(--color-paper-raised)',
        boxShadow: 'var(--shadow-card)',
        overflowX: 'auto',
        ...style,
      }}
    >
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: 'var(--font-precision)',
          fontSize: 'var(--text-body-sm)',
          textAlign: 'left',
        }}
      >
        <thead>
          <tr
            style={{
              background: 'var(--color-paper)',
              borderBottom: '2px solid var(--color-rule)',
            }}
          >
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  padding: '8px 12px',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 'var(--weight-bold)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  textAlign: col.align || 'left',
                  width: col.width,
                  whiteSpace: 'nowrap',
                  borderRight: '1px solid var(--color-rule)',
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: '24px 12px',
                  textAlign: 'center',
                  color: 'var(--color-ink-soft)',
                  fontSize: 'var(--text-body-sm)',
                  fontStyle: 'italic',
                }}
              >
                — {emptyMessage} —
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const isEven = rowIndex % 2 === 1;
              const rowKey = row[keyField] !== undefined ? String(row[keyField]) : String(rowIndex);
              const isClickable = !!onRowClick;

              return (
                <tr
                  key={rowKey}
                  onClick={() => onRowClick && onRowClick(row)}
                  className={greenbar && isEven ? 'greenbar-row' : ''}
                  style={{
                    borderBottom: '1px solid var(--color-rule)',
                    background: greenbar && isEven
                      ? 'color-mix(in srgb, var(--color-paper-raised) 90%, var(--color-win-green))'
                      : 'var(--color-paper-raised)',
                    cursor: isClickable ? 'pointer' : 'default',
                    transition: 'background var(--transition-fast)',
                  }}
                >
                  {columns.map((col) => {
                    const val = row[col.key];
                    return (
                      <td
                        key={col.key}
                        className={col.align === 'right' ? 'tabular-nums' : ''}
                        style={{
                          padding: '7px 12px',
                          color: 'var(--color-ink)',
                          textAlign: col.align || 'left',
                          borderRight: '1px solid var(--color-rule)',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {col.render ? col.render(val, row, rowIndex) : String(val ?? '—')}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

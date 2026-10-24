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
  onRowClick,
  emptyMessage = 'No ledger entries recorded.',
  style,
}: LedgerTableProps<T>) {
  return (
    <div
      className="table-responsive"
      style={{
        borderTop: '1px solid var(--color-border-strong)',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        overflowX: 'auto',
        ...style,
      }}
    >
      <table className="ledger-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  textAlign: col.align || 'left',
                  width: col.width,
                  whiteSpace: 'nowrap',
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
                  fontSize: '12px',
                }}
              >
                — {emptyMessage} —
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const rowKey = row[keyField] !== undefined ? String(row[keyField]) : String(rowIndex);
              const isClickable = !!onRowClick;

              return (
                <tr
                  key={rowKey}
                  onClick={() => onRowClick && onRowClick(row)}
                  style={{
                    cursor: isClickable ? 'pointer' : 'default',
                  }}
                >
                  {columns.map((col) => {
                    const val = row[col.key];
                    return (
                      <td
                        key={col.key}
                        className={col.align === 'right' ? 'tabular-nums' : ''}
                        style={{
                          textAlign: col.align || 'left',
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

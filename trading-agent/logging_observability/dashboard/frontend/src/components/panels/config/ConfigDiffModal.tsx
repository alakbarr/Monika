import React from 'react';
import { Badge } from '../../ui/Badge';
import { SlidersHorizontal, X } from 'lucide-react';

export interface DiffItem {
  path: string;
  oldVal: unknown;
  newVal: unknown;
}

interface ConfigDiffModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  saving: boolean;
  diffItems: DiffItem[];
  targetConfig: Record<string, unknown>;
}

export const ConfigDiffModal: React.FC<ConfigDiffModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  saving,
  diffItems,
  targetConfig,
}) => {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
    >
      <div
        className="ledger-card"
        style={{
          width: '100%',
          maxWidth: '680px',
          background: 'var(--color-surface-card)',
          border: '1px solid var(--color-border)',
          borderRadius: '4px',
          overflow: 'hidden',
          boxShadow: '0 12px 36px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '85vh',
        }}
      >
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--color-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SlidersHorizontal size={18} color="var(--color-brass)" />
            <h3
              style={{
                margin: 0,
                fontSize: '14px',
                fontWeight: 700,
                color: 'var(--color-ink)',
                fontFamily: 'var(--font-precision)',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              Confirm Configuration Changes & Hot-Reload
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div
          style={{
            padding: '20px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <p
              style={{
                fontSize: '12px',
                color: 'var(--color-ink-muted)',
                margin: 0,
                fontFamily: 'var(--font-precision)',
              }}
            >
              Applying these changes will create a timestamped <code>.bak</code> backup and trigger
              runtime hot-reloads on active RiskGates.
            </p>
            <Badge variant={diffItems.length > 0 ? 'warn' : 'neutral'} size="sm">
              {diffItems.length} FIELD(S) CHANGED
            </Badge>
          </div>

          {diffItems.length > 0 ? (
            <div
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: '2px',
                maxHeight: '260px',
                overflowY: 'auto',
              }}
            >
              <table
                className="ledger-table"
                style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}
              >
                <thead>
                  <tr>
                    <th>Config Path</th>
                    <th style={{ color: 'var(--color-loss)' }}>Current Value</th>
                    <th style={{ color: 'var(--color-profit)' }}>New Value</th>
                  </tr>
                </thead>
                <tbody>
                  {diffItems.map((item) => (
                    <tr key={item.path}>
                      <td style={{ color: 'var(--color-brass)', fontWeight: 600 }}>{item.path}</td>
                      <td style={{ color: 'var(--color-ink-muted)', textDecoration: 'line-through' }}>
                        {item.oldVal === undefined ? '—' : JSON.stringify(item.oldVal)}
                      </td>
                      <td style={{ color: 'var(--color-profit)', fontWeight: 700 }}>
                        {item.newVal === undefined ? '—' : JSON.stringify(item.newVal)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div
              style={{
                padding: '16px',
                textAlign: 'center',
                color: 'var(--color-ink-muted)',
                fontSize: '12px',
              }}
            >
              No structural differences detected from original configuration.
            </div>
          )}

          <details style={{ marginTop: '6px' }}>
            <summary
              style={{
                fontSize: '11px',
                color: 'var(--color-ink-muted)',
                cursor: 'pointer',
                fontFamily: 'var(--font-precision)',
              }}
            >
              View Full Target JSON Payload Preview
            </summary>
            <div
              style={{
                marginTop: '6px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: '2px',
                padding: '10px',
                fontFamily: 'var(--font-precision)',
                fontSize: '11px',
                maxHeight: '160px',
                overflowY: 'auto',
                color: 'var(--color-ink)',
              }}
            >
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(targetConfig, null, 2)}
              </pre>
            </div>
          </details>
        </div>

        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid var(--color-border)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
            background: 'var(--color-surface)',
          }}
        >
          <button
            onClick={onClose}
            className="typewriter-btn"
            style={{
              padding: '6px 14px',
              borderRadius: '2px',
              background: 'transparent',
              border: '1px solid var(--color-border)',
              color: 'var(--color-ink)',
              cursor: 'pointer',
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={saving}
            className="typewriter-btn"
            style={{
              padding: '6px 18px',
              borderRadius: '2px',
              background: 'var(--color-brass)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-paper-dark)',
              fontWeight: 700,
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              cursor: saving ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-precision)',
            }}
          >
            {saving ? 'Writing...' : 'Confirm & Hot-Reload'}
          </button>
        </div>
      </div>
    </div>
  );
};

import React from 'react';
import { CheckCircle2, Clock, AlertCircle, X, Copy, Check } from 'lucide-react';
import type { GraphNode } from '../../../types/api';
import { getStatusColor } from './graphUtils';

interface GraphInspectorProps {
  selectedNode: GraphNode;
  onClose: () => void;
  copied: boolean;
  onCopyPayload: () => void;
}

export const GraphInspector: React.FC<GraphInspectorProps> = ({
  selectedNode,
  onClose,
  copied,
  onCopyPayload,
}) => {
  return (
    <div
      className="ledger-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRadius: '2px',
      }}
    >
      {/* Inspector Header */}
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-surface)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3
              style={{
                margin: 0,
                fontSize: 'var(--text-title-sm)',
                color: 'var(--color-ink)',
                fontWeight: 700,
                fontFamily: 'var(--font-precision)',
              }}
            >
              {selectedNode.name}
            </h3>
            <span
              style={{
                padding: '2px 6px',
                borderRadius: '2px',
                fontSize: '10px',
                fontWeight: 600,
                textTransform: 'uppercase',
                border: '1px solid var(--color-brass)',
                color: 'var(--color-brass)',
                fontFamily: 'var(--font-precision)',
              }}
            >
              {selectedNode.stage}
            </span>
          </div>
          <div
            style={{
              fontSize: 'var(--text-caption)',
              color: 'var(--color-ink-muted)',
              marginTop: 2,
              fontFamily: 'var(--font-precision)',
            }}
          >
            ID: {selectedNode.id}
          </div>
        </div>

        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            padding: 4,
            display: 'flex',
            alignItems: 'center',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Inspector Body Scroll */}
      <div
        style={{
          padding: '20px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '18px',
          flex: 1,
        }}
      >
        {/* Status & Timing Metrics */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '10px',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Status</span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 600,
                color: getStatusColor(selectedNode.status),
                textTransform: 'capitalize',
              }}
            >
              {selectedNode.status === 'done' && <CheckCircle2 size={14} />}
              {selectedNode.status === 'running' && <Clock size={14} />}
              {selectedNode.status === 'failed' && <AlertCircle size={14} />}
              {selectedNode.status}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Duration</span>
            <div
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-text-white)',
              }}
            >
              {((selectedNode.duration_ms ?? 0) / 1000).toFixed(2)}s
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
              Tokens (In / Out)
            </span>
            <div
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-primary)',
              }}
            >
              {selectedNode.tokens?.input ?? 0} / {selectedNode.tokens?.output ?? 0}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
            }}
          >
            <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Est. Cost</span>
            <div
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-profit)',
              }}
            >
              ${(selectedNode.tokens?.cost_usd ?? 0).toFixed(4)}
            </div>
          </div>
        </div>

        {/* Error Alert if Failed */}
        {selectedNode.error && (
          <div
            style={{
              padding: '12px 14px',
              borderRadius: 'var(--radius-md)',
              background: 'rgba(246,70,93,0.1)',
              border: '1px solid rgba(246,70,93,0.3)',
              color: 'var(--color-loss)',
              fontSize: 'var(--text-caption)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <strong>Node Execution Error:</strong>
              <div style={{ marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                {selectedNode.error}
              </div>
            </div>
          </div>
        )}

        {/* Input Summary Section */}
        <div>
          <span
            style={{
              fontSize: 'var(--text-caption)',
              fontWeight: 600,
              color: 'var(--color-text-secondary)',
              textTransform: 'uppercase',
            }}
          >
            Input Summary
          </span>
          <div
            style={{
              marginTop: 6,
              padding: '12px',
              background: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: 'var(--text-body-sm)',
              color: 'var(--color-text-primary)',
              lineHeight: 1.5,
            }}
          >
            {selectedNode.input_summary || 'Standard pipeline state inputs'}
          </div>
        </div>

        {/* Output Decision / Payload Section */}
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 6,
            }}
          >
            <span
              style={{
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--color-text-secondary)',
                textTransform: 'uppercase',
              }}
            >
              Output Decision Payload
            </span>
            <button
              onClick={onCopyPayload}
              disabled={!selectedNode.output_payload}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                background: 'transparent',
                border: 'none',
                color: copied ? 'var(--color-profit)' : 'var(--color-text-muted)',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy JSON'}
            </button>
          </div>

          <div
            style={{
              background: '#0d1117',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              padding: '12px',
              maxHeight: '220px',
              overflowY: 'auto',
            }}
          >
            <pre
              style={{
                margin: 0,
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
                color: '#c9d1d9',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {selectedNode.output_payload
                ? JSON.stringify(selectedNode.output_payload, null, 2)
                : selectedNode.status === 'pending'
                ? 'Node has not executed yet in this cycle (Pending upstream step completion)'
                : 'No output payload recorded for this node'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

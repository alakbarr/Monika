import React from 'react';
import { CheckCircle2, Clock, AlertCircle, X, Copy, Check, Activity, Coins } from 'lucide-react';
import type { GraphNode } from '../../../types/api';
import { getStatusColor } from './graphUtils';

interface GraphInspectorProps {
  selectedNode: GraphNode;
  onClose: () => void;
  copied: boolean;
  onCopyPayload: () => void;
  cycleTrace?: any;
  cycleTokens?: any;
}

export const GraphInspector: React.FC<GraphInspectorProps> = ({
  selectedNode,
  onClose,
  copied,
  onCopyPayload,
  cycleTrace,
  cycleTokens,
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
          borderBottom: '2px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-paper-raised)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3
              style={{
                margin: 0,
                fontSize: 'var(--text-title-sm)',
                color: 'var(--color-ink)',
                fontWeight: 800,
                fontFamily: 'var(--font-precision)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              {selectedNode.name}
            </h3>
            <span
              style={{
                padding: '2px 6px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '10px',
                fontWeight: 700,
                textTransform: 'uppercase',
                border: '1.5px solid var(--color-brass)',
                background: 'var(--color-paper)',
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
              color: 'var(--color-ink-soft)',
              marginTop: 4,
              fontFamily: 'var(--font-precision)',
            }}
          >
            NODE ID: {selectedNode.id}
          </div>
        </div>

        <button
          onClick={onClose}
          style={{
            background: 'var(--color-paper)',
            border: '1.5px solid var(--color-rule)',
            color: 'var(--color-ink)',
            cursor: 'pointer',
            padding: 4,
            display: 'flex',
            alignItems: 'center',
            borderRadius: 'var(--radius-sm)',
          }}
          title="Close Inspector"
        >
          <X size={16} />
        </button>
      </div>

      {/* Inspector Body Scroll */}
      <div
        style={{
          padding: '16px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          flex: 1,
          background: 'var(--color-paper-raised)',
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
              background: 'var(--color-paper)',
              borderRadius: 'var(--radius-sm)',
              border: '1.5px solid var(--color-rule)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 'bold', textTransform: 'uppercase' }}>Status</span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 700,
                color: getStatusColor(selectedNode.status),
                textTransform: 'uppercase',
                fontFamily: 'var(--font-precision)',
              }}
            >
              {selectedNode.status === 'done' && <CheckCircle2 size={14} />}
              {selectedNode.status === 'running' && <Clock size={14} />}
              {selectedNode.status === 'failed' && <AlertCircle size={14} />}
              [{selectedNode.status}]
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRadius: 'var(--radius-sm)',
              border: '1.5px solid var(--color-rule)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 'bold', textTransform: 'uppercase' }}>Duration</span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 700,
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ink)',
              }}
            >
              {((selectedNode.duration_ms ?? 0) / 1000).toFixed(2)}s
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRadius: 'var(--radius-sm)',
              border: '1.5px solid var(--color-rule)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 'bold', textTransform: 'uppercase' }}>
              Tokens (In / Out)
            </span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 700,
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-win-blue)',
              }}
            >
              {selectedNode.tokens?.input ?? 0} / {selectedNode.tokens?.output ?? 0}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRadius: 'var(--radius-sm)',
              border: '1.5px solid var(--color-rule)',
            }}
          >
            <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 'bold', textTransform: 'uppercase' }}>Est. Cost</span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: 'var(--text-body-sm)',
                fontWeight: 700,
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ledger-green)',
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
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-loss-bg)',
              border: '1.5px solid var(--color-ledger-red)',
              color: 'var(--color-ledger-red)',
              fontSize: 'var(--text-caption)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <strong style={{ textTransform: 'uppercase' }}>Node Execution Error:</strong>
              <div style={{ marginTop: 4, fontFamily: 'var(--font-precision)' }}>
                {selectedNode.error}
              </div>
            </div>
          </div>
        )}

        {/* Input Summary Section */}
        <div>
          <span
            style={{
              fontSize: '10px',
              fontWeight: 800,
              color: 'var(--color-ink-soft)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)',
            }}
          >
            INPUT SUMMARY
          </span>
          <div
            style={{
              marginTop: 6,
              padding: '12px',
              background: 'var(--color-paper)',
              borderRadius: 'var(--radius-sm)',
              border: '1.5px solid var(--color-rule)',
              fontSize: 'var(--text-body-sm)',
              color: 'var(--color-ink)',
              fontFamily: 'var(--font-precision)',
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
                fontSize: '10px',
                fontWeight: 800,
                color: 'var(--color-ink-soft)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                fontFamily: 'var(--font-precision)',
              }}
            >
              OUTPUT DECISION PAYLOAD
            </span>
            <button
              onClick={onCopyPayload}
              disabled={!selectedNode.output_payload}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                padding: '2px 8px',
                color: copied ? 'var(--color-ledger-green)' : 'var(--color-ink)',
                fontSize: '10px',
                fontWeight: 700,
                fontFamily: 'var(--font-precision)',
                cursor: 'pointer',
              }}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? '[ COPIED ]' : '[ COPY JSON ]'}
            </button>
          </div>

          <div
            style={{
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              padding: '12px',
              maxHeight: '220px',
              overflowY: 'auto',
              boxShadow: 'inset 1px 1px 0 rgba(0,0,0,0.06)',
            }}
          >
            <pre
              style={{
                margin: 0,
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ink)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                lineHeight: 1.5,
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

        {/* Cycle Telemetry Summary (from api.cycleTraceSummary) */}
        {cycleTrace && (
          <div style={{ marginTop: '4px', borderTop: '1px dashed var(--color-rule)', paddingTop: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Activity size={14} color="var(--color-brass)" />
              <span style={{ fontSize: '11px', fontWeight: 800, textTransform: 'uppercase', color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                CYCLE TRACE TELEMETRY // {cycleTrace.cycle_id || 'ACTIVE'}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
              <div style={{ background: 'var(--color-paper)', padding: '6px 8px', borderRadius: 'var(--radius-sm)', border: '1.5px solid var(--color-rule)' }}>
                <span style={{ color: 'var(--color-ink-soft)' }}>Spans: </span>
                <strong style={{ color: 'var(--color-ink)' }}>{cycleTrace.spans?.length ?? (cycleTrace.summary?.span_count ?? '—')}</strong>
              </div>
              <div style={{ background: 'var(--color-paper)', padding: '6px 8px', borderRadius: 'var(--radius-sm)', border: '1.5px solid var(--color-rule)' }}>
                <span style={{ color: 'var(--color-ink-soft)' }}>Root: </span>
                <strong style={{ color: 'var(--color-ink)' }}>{cycleTrace.summary?.root_name ?? 'Workflow'}</strong>
              </div>
            </div>
          </div>
        )}

        {/* Cycle Token Cost Attribution (from api.tokenCycles) */}
        {cycleTokens && (
          <div style={{ marginTop: '4px', borderTop: '1px dashed var(--color-rule)', paddingTop: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Coins size={14} color="var(--color-ledger-green)" />
              <span style={{ fontSize: '11px', fontWeight: 800, textTransform: 'uppercase', color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                CYCLE TOKEN ATTRIBUTION
              </span>
            </div>
            <div style={{ background: 'var(--color-paper)', padding: '8px', borderRadius: 'var(--radius-sm)', border: '1.5px solid var(--color-rule)', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
              {cycleTokens.total_cost_usd != null && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--color-ink-soft)' }}>Cycle Cost:</span>
                  <strong style={{ color: 'var(--color-ledger-green)' }}>${Number(cycleTokens.total_cost_usd).toFixed(4)}</strong>
                </div>
              )}
              {cycleTokens.total_tokens != null && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-ink-soft)' }}>Total Tokens:</span>
                  <strong style={{ color: 'var(--color-ink)' }}>{Number(cycleTokens.total_tokens).toLocaleString()}</strong>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

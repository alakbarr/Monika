import React from 'react';
import { CheckCircle2, Clock, AlertCircle, X, Copy, Check, Activity, Coins } from 'lucide-react';
import type { GraphNode } from '../../../types/api';
import { getStageKicker, getStatusColor } from './graphUtils';

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
      className="editorial-section swiss-crosshair"
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        border: '1px solid var(--color-rule)',
        background: 'var(--color-paper-raised)',
      }}
    >
      {/* Inspector Header */}
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          background: 'var(--color-paper)',
        }}
      >
        <div>
          <div className="editorial-kicker">
            {getStageKicker(selectedNode.id, selectedNode.stage)}
          </div>
          <h3
            style={{
              margin: '2px 0 0 0',
              fontFamily: 'var(--font-display)',
              fontSize: '20px',
              fontWeight: 400,
              color: 'var(--color-ink)',
            }}
          >
            {selectedNode.name}
          </h3>
          <div
            style={{
              fontSize: '11px',
              color: 'var(--color-ink-muted)',
              marginTop: 2,
              fontFamily: 'var(--font-precision)',
            }}
          >
            NODE ID: {selectedNode.id}
          </div>
        </div>

        <button
          onClick={onClose}
          className="editorial-btn editorial-btn--ghost"
          style={{ padding: '4px 8px' }}
          title="Close Inspector"
        >
          <X size={14} />
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
        }}
      >
        {/* Status & Timing Metrics */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            borderTop: '1px solid var(--color-rule)',
            borderLeft: '1px solid var(--color-rule)',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRight: '1px solid var(--color-rule)',
              borderBottom: '1px solid var(--color-rule)',
            }}
          >
            <span className="editorial-kicker">STATUS</span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                marginTop: 4,
                fontSize: '12px',
                fontWeight: 600,
                color: getStatusColor(selectedNode.status),
                textTransform: 'uppercase',
                fontFamily: 'var(--font-precision)',
              }}
            >
              {selectedNode.status === 'done' && <CheckCircle2 size={13} />}
              {selectedNode.status === 'running' && <Clock size={13} />}
              {selectedNode.status === 'failed' && <AlertCircle size={13} />}
              {selectedNode.status === 'skipped' && <Activity size={13} />}
              {selectedNode.status}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRight: '1px solid var(--color-rule)',
              borderBottom: '1px solid var(--color-rule)',
            }}
          >
            <span className="editorial-kicker">DURATION</span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: '12px',
                fontWeight: 600,
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ink)',
              }}
            >
              {selectedNode.status === 'skipped' ? 'BYPASSED' : `${((selectedNode.duration_ms ?? 0) / 1000).toFixed(2)}s`}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRight: '1px solid var(--color-rule)',
              borderBottom: '1px solid var(--color-rule)',
            }}
          >
            <span className="editorial-kicker">TOKENS (IN / OUT)</span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: '12px',
                fontWeight: 600,
                fontFamily: 'var(--font-precision)',
                color: (selectedNode.tokens?.total ?? 0) > 0 ? 'var(--color-ink)' : 'var(--color-ink-soft)',
              }}
            >
              {(selectedNode.tokens?.total ?? 0) > 0 ? (
                `${selectedNode.tokens?.input ?? 0} / ${selectedNode.tokens?.output ?? 0}`
              ) : selectedNode.id === 'execution' ? (
                <span style={{ fontSize: '11px' }}>0 (Deterministic MT5)</span>
              ) : selectedNode.id === 'risk_gate' ? (
                <span style={{ fontSize: '11px' }}>0 (Rule-Based Fortress)</span>
              ) : selectedNode.status === 'skipped' ? (
                <span style={{ fontSize: '11px' }}>0 (Skipped)</span>
              ) : (
                '0 / 0'
              )}
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper)',
              borderRight: '1px solid var(--color-rule)',
              borderBottom: '1px solid var(--color-rule)',
            }}
          >
            <span className="editorial-kicker">EST. COST</span>
            <div
              className="tabular-nums"
              style={{
                marginTop: 4,
                fontSize: '12px',
                fontWeight: 600,
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
              background: 'var(--color-loss-bg)',
              border: '1px solid var(--color-ledger-red)',
              color: 'var(--color-ledger-red)',
              fontSize: '11px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
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
          <span className="editorial-kicker">INPUT SUMMARY</span>
          <div
            style={{
              marginTop: 6,
              padding: '12px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              fontSize: '12px',
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
            <span className="editorial-kicker">OUTPUT DECISION PAYLOAD</span>
            <button
              onClick={onCopyPayload}
              disabled={!selectedNode.output_payload}
              className="editorial-btn editorial-btn--ghost"
              style={{ padding: '2px 8px', fontSize: '11px' }}
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? 'COPIED' : 'COPY JSON'}
            </button>
          </div>

          <div
            style={{
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              padding: '12px',
              maxHeight: '220px',
              overflowY: 'auto',
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
                : selectedNode.status === 'skipped'
                ? `Node execution bypassed: ${selectedNode.input_summary}`
                : selectedNode.status === 'pending'
                ? 'Node has not executed yet in this cycle (Pending upstream step completion)'
                : 'No output payload recorded for this node'}
            </pre>
          </div>
        </div>

        {/* Cycle Telemetry Summary */}
        {cycleTrace && (
          <div style={{ borderTop: '1px solid var(--color-rule)', paddingTop: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Activity size={13} color="var(--color-ink-muted)" />
              <span className="editorial-kicker">
                CYCLE TRACE TELEMETRY — {cycleTrace.cycle_id || 'ACTIVE'}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
              <div style={{ background: 'var(--color-paper)', padding: '6px 8px', border: '1px solid var(--color-rule)' }}>
                <span style={{ color: 'var(--color-ink-soft)' }}>Spans: </span>
                <strong style={{ color: 'var(--color-ink)' }}>{cycleTrace.spans?.length ?? (cycleTrace.summary?.span_count ?? '—')}</strong>
              </div>
              <div style={{ background: 'var(--color-paper)', padding: '6px 8px', border: '1px solid var(--color-rule)' }}>
                <span style={{ color: 'var(--color-ink-soft)' }}>Root: </span>
                <strong style={{ color: 'var(--color-ink)' }}>{cycleTrace.summary?.root_name ?? 'Workflow'}</strong>
              </div>
            </div>
          </div>
        )}

        {/* Cycle Token Cost Attribution */}
        {cycleTokens && (
          <div style={{ borderTop: '1px solid var(--color-rule)', paddingTop: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <Coins size={13} color="var(--color-ledger-green)" />
              <span className="editorial-kicker">
                CYCLE TOKEN ATTRIBUTION
              </span>
            </div>
            <div style={{ background: 'var(--color-paper)', padding: '8px', border: '1px solid var(--color-rule)', fontSize: '11px', fontFamily: 'var(--font-precision)' }}>
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

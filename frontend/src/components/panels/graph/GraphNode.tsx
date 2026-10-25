import React from 'react';
import { Clock } from 'lucide-react';
import type { GraphNode as GraphNodeType } from '../../../types/api';
import { getNodeIcon, getStageKicker, getStatusColor } from './graphUtils';

interface GraphNodeProps {
  node: GraphNodeType;
  isSelected: boolean;
  onSelect: (id: string) => void;
  pos: { x: number; y: number };
  nodeWidth: number;
  nodeHeight: number;
  totalDurationMs?: number;
}

export const GraphNodeComponent: React.FC<GraphNodeProps> = ({
  node,
  isSelected,
  onSelect,
  pos,
  nodeWidth,
  nodeHeight,
  totalDurationMs = 0,
}) => {
  const Icon = getNodeIcon(node.id);
  const statusColor = getStatusColor(node.status);
  const stageKicker = getStageKicker(node.id, node.stage);
  const isFortressGate = node.id === 'risk_gate';
  const durationSharePct =
    totalDurationMs > 0 && node.duration_ms > 0
      ? Math.min(100, Math.max(2, Math.round((node.duration_ms / totalDurationMs) * 100)))
      : 0;

  return (
    <g
      transform={`translate(${pos.x}, ${pos.y})`}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(node.id);
      }}
      style={{ cursor: 'pointer' }}
    >
      {/* 1px Architectural Schematic Node Frame */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height={nodeHeight}
        rx="0"
        fill="var(--color-paper-raised)"
        stroke={
          isSelected
            ? 'var(--color-ink)'
            : isFortressGate
              ? 'var(--color-brass)'
              : node.status === 'skipped'
                ? 'var(--color-ink-muted)'
                : 'var(--color-rule-strong)'
        }
        strokeWidth={isSelected ? 1.5 : isFortressGate ? 1.25 : 1}
        strokeDasharray={node.status === 'skipped' ? '4 3' : undefined}
        opacity={node.status === 'skipped' ? 0.78 : 1}
      />

      {/* Inner Mechanical Fortress Double-Hairline Perimeter */}
      {isFortressGate && (
        <rect
          x="3"
          y="3"
          width={nodeWidth - 6}
          height={nodeHeight - 6}
          rx="0"
          fill="none"
          stroke="var(--color-brass)"
          strokeWidth="0.75"
          strokeDasharray="3 2"
          opacity="0.55"
        />
      )}

      {/* Top Hairline Status Indicator */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height="2.5"
        rx="0"
        fill={isSelected ? 'var(--color-accent)' : statusColor}
        opacity={node.status === 'skipped' ? 0.5 : 1}
      />

      {/* Bottom Latency Waterfall Proportion Bar */}
      {durationSharePct > 0 && node.status !== 'skipped' && (
        <rect
          x="0"
          y={nodeHeight - 2.5}
          width={Math.round((nodeWidth * durationSharePct) / 100)}
          height="2.5"
          rx="0"
          fill={statusColor}
          opacity="0.45"
        />
      )}

      {/* Swiss Crosshair Corner Tick (Top-Left) */}
      <path
        d="M -3 0 L 3 0 M 0 -3 L 0 3"
        stroke="var(--color-ink-muted)"
        strokeWidth="1"
      />

      {/* Node Schematic Content */}
      <foreignObject x="10" y="9" width={nodeWidth - 20} height={nodeHeight - 17}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            height: '100%',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-precision)',
          }}
        >
          {/* Stage Kicker + Status */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px', marginBottom: '4px' }}>
              <span
                style={{
                  fontSize: '11px',
                  letterSpacing: '0.04em',
                  color: isFortressGate ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                  fontWeight: isFortressGate ? 600 : 400,
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                }}
              >
                {stageKicker}
              </span>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  color: statusColor,
                  whiteSpace: 'nowrap',
                }}
              >
                <span
                  style={{
                    width: 5,
                    height: 5,
                    backgroundColor: statusColor,
                    display: 'inline-block',
                  }}
                />
                {node.status}
              </span>
            </div>

            {/* Title Row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
              <Icon size={13} color={isFortressGate ? 'var(--color-brass)' : statusColor} style={{ flexShrink: 0 }} />
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '15px',
                  fontWeight: 400,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  color: 'var(--color-ink)',
                }}
                title={node.name}
              >
                {node.name}
              </span>
            </div>
          </div>

          {/* Node Telemetry Footer */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '6px',
              paddingTop: '6px',
              borderTop: '1px solid var(--color-rule)',
            }}
          >
            <span
              className="tabular-nums"
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ink-soft)',
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
              }}
            >
              <Clock size={10} />
              {node.status === 'skipped'
                ? 'BYPASSED'
                : `${(node.duration_ms / 1000).toFixed(2)}s${durationSharePct > 0 ? ` (${durationSharePct}%)` : ''}`}
            </span>

            <span
              className="tabular-nums"
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 600,
                color: isFortressGate
                  ? 'var(--color-brass)'
                  : node.tokens.total > 0
                    ? 'var(--color-ink)'
                    : 'var(--color-ink-muted)',
              }}
            >
              {isFortressGate
                ? 'FAIL-CLOSED'
                : node.tokens.total > 0
                  ? `${(node.tokens.total / 1000).toFixed(1)}k tok`
                  : 'DETERMINISTIC'}
            </span>
          </div>
        </div>
      </foreignObject>
    </g>
  );
};

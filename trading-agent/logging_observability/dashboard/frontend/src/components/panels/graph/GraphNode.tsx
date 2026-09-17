import React from 'react';
import {
  FileText,
  Database,
  TrendingUp,
  TrendingDown,
  Scale,
  Shield,
  Zap,
  Layers,
  Clock,
} from 'lucide-react';
import type { GraphNode as GraphNodeType, GraphNodeStatus } from '../../../types/api';

interface GraphNodeProps {
  node: GraphNodeType;
  isSelected: boolean;
  onSelect: (id: string) => void;
  pos: { x: number; y: number };
  nodeWidth: number;
  nodeHeight: number;
}

export const getNodeIcon = (id: string) => {
  switch (id) {
    case 'fundamental_brief':
      return FileText;
    case 'prefetch_data':
      return Database;
    case 'bull_advocate':
      return TrendingUp;
    case 'bear_dissent':
      return TrendingDown;
    case 'debate_judge':
      return Scale;
    case 'risk_gate':
      return Shield;
    case 'execution':
      return Zap;
    default:
      return Layers;
  }
};

export const getStatusColor = (status: GraphNodeStatus) => {
  switch (status) {
    case 'done':
      return '#2D5A27';
    case 'running':
      return '#C49A45';
    case 'failed':
      return '#8B261E';
    case 'pending':
    default:
      return '#6C6558';
  }
};

export const GraphNodeComponent: React.FC<GraphNodeProps> = ({
  node,
  isSelected,
  onSelect,
  pos,
  nodeWidth,
  nodeHeight,
}) => {
  const Icon = getNodeIcon(node.id);
  const statusColor = getStatusColor(node.status);

  return (
    <g
      transform={`translate(${pos.x}, ${pos.y})`}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(node.id);
      }}
      style={{ cursor: 'pointer' }}
    >
      {/* Node Card Background Rect */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height={nodeHeight}
        rx="2"
        fill="var(--color-surface-card)"
        stroke={isSelected ? 'var(--color-brass)' : statusColor}
        strokeWidth={isSelected ? 2 : 1}
      />

      {/* Top Accent Strip */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height="3"
        rx="1"
        fill={statusColor}
      />

      {/* Node Header: Icon + Title */}
      <foreignObject x="12" y="14" width={nodeWidth - 24} height={nodeHeight - 28}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            height: '100%',
            color: 'var(--color-text-white)',
          }}
        >
          {/* Title Row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: '6px',
                  background: 'rgba(255,255,255,0.06)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: statusColor,
                }}
              >
                <Icon size={15} />
              </div>
              <span
                style={{
                  fontSize: '13px',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '110px',
                }}
              >
                {node.name}
              </span>
            </div>

            {/* Status pill with animated dot */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 6px',
                borderRadius: '10px',
                background: 'rgba(0,0,0,0.4)',
                border: `1px solid ${statusColor}44`,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: statusColor,
                  display: 'inline-block',
                  boxShadow: node.status === 'running' ? `0 0 6px ${statusColor}` : undefined,
                }}
              />
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  color: statusColor,
                }}
              >
                {node.status}
              </span>
            </div>
          </div>

          {/* Node Body Chips */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
            <span
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
              }}
            >
              <Clock size={11} />
              {(node.duration_ms / 1000).toFixed(2)}s
            </span>

            <span
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                color: node.tokens.total > 0 ? 'var(--color-primary)' : 'var(--color-text-muted)',
              }}
            >
              {node.tokens.total > 0 ? `${(node.tokens.total / 1000).toFixed(1)}k tok` : '0 tok'}
            </span>
          </div>
        </div>
      </foreignObject>
    </g>
  );
};

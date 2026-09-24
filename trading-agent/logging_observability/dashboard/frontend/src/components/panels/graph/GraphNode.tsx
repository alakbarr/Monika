import React from 'react';
import { Clock } from 'lucide-react';
import type { GraphNode as GraphNodeType } from '../../../types/api';
import { getNodeIcon, getStatusColor } from './graphUtils';

interface GraphNodeProps {
  node: GraphNodeType;
  isSelected: boolean;
  onSelect: (id: string) => void;
  pos: { x: number; y: number };
  nodeWidth: number;
  nodeHeight: number;
}

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
      {/* Retro 3D Hard Shadow Rect */}
      <rect
        x="3"
        y="3"
        width={nodeWidth}
        height={nodeHeight}
        rx="3"
        fill="var(--color-rule)"
      />

      {/* Node Card Background Rect */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height={nodeHeight}
        rx="3"
        fill="var(--color-paper-raised)"
        stroke={isSelected ? 'var(--color-brass)' : 'var(--color-rule)'}
        strokeWidth={isSelected ? 2.5 : 1.5}
      />

      {/* Top Accent Strip */}
      <rect
        x="0"
        y="0"
        width={nodeWidth}
        height="4"
        rx="2"
        fill={statusColor}
      />

      {/* Node Header: Icon + Title */}
      <foreignObject x="10" y="12" width={nodeWidth - 20} height={nodeHeight - 20}>
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
          {/* Title Row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '3px',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: statusColor,
                  flexShrink: 0,
                }}
              >
                <Icon size={14} />
              </div>
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 800,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  color: 'var(--color-ink)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.02em',
                }}
                title={node.name}
              >
                {node.name}
              </span>
            </div>

            {/* Status pill with retro pixel LED */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '1px 6px',
                borderRadius: '3px',
                background: 'var(--color-paper)',
                border: `1.5px solid ${statusColor}`,
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 1,
                  backgroundColor: statusColor,
                  display: 'inline-block',
                }}
              />
              <span
                style={{
                  fontSize: '9px',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  color: statusColor,
                }}
              >
                {node.status}
              </span>
            </div>
          </div>

          {/* Node Body Chips */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '6px',
              paddingTop: '6px',
              borderTop: '1px dashed var(--color-rule)',
            }}
          >
            <span
              style={{
                fontSize: '10.5px',
                fontFamily: 'var(--font-precision)',
                color: 'var(--color-ink-soft)',
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
                fontSize: '10.5px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 700,
                color: node.tokens.total > 0 ? 'var(--color-win-blue)' : 'var(--color-ink-soft)',
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

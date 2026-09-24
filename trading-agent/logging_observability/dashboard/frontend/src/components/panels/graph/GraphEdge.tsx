import React from 'react';
import type { GraphNode } from '../../../types/api';

interface GraphEdgeProps {
  fromId: string;
  toId: string;
  srcPos: { x: number; y: number };
  dstPos: { x: number; y: number };
  srcNode?: GraphNode;
  dstNode?: GraphNode;
  nodeWidth: number;
  nodeHeight: number;
}

export const GraphEdge: React.FC<GraphEdgeProps> = ({
  fromId,
  toId,
  srcPos,
  dstPos,
  srcNode,
  dstNode,
  nodeWidth,
  nodeHeight,
}) => {
  const startX = srcPos.x + nodeWidth;
  const startY = srcPos.y + nodeHeight / 2;
  const endX = dstPos.x;
  const endY = dstPos.y + nodeHeight / 2;

  const dx = endX - startX;
  const c1x = startX + dx * 0.45;
  const c1y = startY;
  const c2x = startX + dx * 0.55;
  const c2y = endY;

  const pathData = `M ${startX} ${startY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${endX} ${endY}`;

  const isDone = srcNode?.status === 'done' && dstNode?.status === 'done';
  const isRunning =
    srcNode?.status === 'running' ||
    (srcNode?.status === 'done' && dstNode?.status === 'running');

  const strokeColor = isDone
    ? 'var(--color-ledger-green)'
    : isRunning
    ? 'var(--color-brass)'
    : 'var(--color-ink-soft)';
  const markerId = isDone
    ? 'url(#arrow-done)'
    : isRunning
    ? 'url(#arrow-running)'
    : 'url(#arrow-pending)';

  return (
    <g key={`${fromId}-${toId}`}>
      {/* Tactile depth underlay */}
      <path
        d={pathData}
        fill="none"
        stroke="var(--color-rule)"
        strokeWidth={isRunning ? 4 : 2.5}
        strokeOpacity={0.2}
        transform="translate(1, 1)"
      />
      <path
        d={pathData}
        fill="none"
        stroke={strokeColor}
        strokeWidth={isRunning ? 3 : 2}
        strokeOpacity={isDone ? 1 : isRunning ? 1 : 0.6}
        strokeDasharray={isRunning ? '6 4' : undefined}
        markerEnd={markerId}
      />
    </g>
  );
};

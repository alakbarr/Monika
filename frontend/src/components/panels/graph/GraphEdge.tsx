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
  const isVerticalDown = Math.abs(srcPos.x - dstPos.x) < 80 && dstPos.y > srcPos.y;
  const isHorizontalForward = dstPos.x >= srcPos.x + nodeWidth * 0.7;

  let startX: number;
  let startY: number;
  let endX: number;
  let endY: number;
  let c1x: number;
  let c1y: number;
  let c2x: number;
  let c2y: number;

  if (isVerticalDown) {
    startX = srcPos.x + nodeWidth / 2;
    startY = srcPos.y + nodeHeight;
    endX = dstPos.x + nodeWidth / 2;
    endY = dstPos.y;
    const dy = endY - startY;
    c1x = startX;
    c1y = startY + dy * 0.45;
    c2x = endX;
    c2y = startY + dy * 0.55;
  } else if (isHorizontalForward) {
    startX = srcPos.x + nodeWidth;
    startY = srcPos.y + nodeHeight / 2;
    endX = dstPos.x;
    endY = dstPos.y + nodeHeight / 2;
    const dx = endX - startX;
    c1x = startX + Math.max(dx * 0.45, 25);
    c1y = startY;
    c2x = startX + Math.max(dx * 0.55, 35);
    c2y = endY;
  } else {
    startX = srcPos.x + nodeWidth / 2;
    startY = srcPos.y + nodeHeight;
    endX = dstPos.x + nodeWidth / 2;
    endY = dstPos.y;
    const midY = (startY + endY) / 2;
    c1x = startX;
    c1y = midY;
    c2x = endX;
    c2y = midY;
  }

  const pathData = `M ${startX} ${startY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${endX} ${endY}`;

  const isDone = srcNode?.status === 'done' && dstNode?.status === 'done';
  const isRunning =
    srcNode?.status === 'running' ||
    (srcNode?.status === 'done' && dstNode?.status === 'running');
  const isSkipped = srcNode?.status === 'skipped' || dstNode?.status === 'skipped';

  const strokeColor = isDone
    ? 'var(--color-ledger-green)'
    : isRunning
    ? 'var(--color-brass)'
    : isSkipped
    ? 'var(--color-ink-muted)'
    : 'var(--color-rule-strong)';
  const markerId = isDone
    ? 'url(#arrow-done)'
    : isRunning
    ? 'url(#arrow-running)'
    : isSkipped
    ? 'url(#arrow-skipped)'
    : 'url(#arrow-pending)';

  return (
    <g key={`${fromId}-${toId}`}>
      <path
        d={pathData}
        fill="none"
        stroke={strokeColor}
        strokeWidth={isRunning ? 1.75 : 1.15}
        strokeOpacity={isDone ? 0.9 : isRunning ? 1 : isSkipped ? 0.4 : 0.65}
        strokeDasharray={isRunning ? '5 3' : isSkipped ? '3 3' : undefined}
        markerEnd={markerId}
      />
    </g>
  );
};

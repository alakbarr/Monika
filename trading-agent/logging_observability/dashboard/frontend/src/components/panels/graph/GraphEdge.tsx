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
  // Determine connection orientation (vertical downward vs horizontal forward)
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
    // Flow straight downward from bottom-center of source to top-center of target
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
    // Standard left-to-right flow from right-center of source to left-center of target
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
    // Diagonal or wrap-around connection
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

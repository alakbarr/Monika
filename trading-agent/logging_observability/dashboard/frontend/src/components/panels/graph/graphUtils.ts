import {
  FileText,
  Database,
  TrendingUp,
  TrendingDown,
  Scale,
  Shield,
  Zap,
  Layers,
} from 'lucide-react';
import type { GraphNodeStatus } from '../../../types/api';

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
      return 'var(--color-ledger-green)';
    case 'running':
      return 'var(--color-brass)';
    case 'failed':
      return 'var(--color-ledger-red)';
    case 'pending':
    default:
      return 'var(--color-ink-soft)';
  }
};

export const COMPACT_POSITIONS: Record<string, { x: number; y: number }> = {
  fundamental_brief: { x: 40, y: 50 },
  prefetch_data: { x: 40, y: 250 },
  bull_advocate: { x: 340, y: 50 },
  bear_dissent: { x: 340, y: 250 },
  debate_judge: { x: 630, y: 150 },
  risk_gate: { x: 930, y: 50 },
  execution: { x: 930, y: 250 },
};

export const WIDE_POSITIONS: Record<string, { x: number; y: number }> = {
  fundamental_brief: { x: 50, y: 260 },
  prefetch_data: { x: 330, y: 260 },
  bull_advocate: { x: 650, y: 130 },
  bear_dissent: { x: 650, y: 390 },
  debate_judge: { x: 950, y: 260 },
  risk_gate: { x: 1250, y: 260 },
  execution: { x: 1510, y: 260 },
};

export const CANONICAL_POSITIONS = COMPACT_POSITIONS;

export const computeGraphLayout = (
  nodes: { id: string }[],
  edges: { from: string; to: string }[],
  mode: 'compact' | 'wide' = 'compact'
): Record<string, { x: number; y: number }> => {
  const basePositions = mode === 'compact' ? COMPACT_POSITIONS : WIDE_POSITIONS;
  const positions: Record<string, { x: number; y: number }> = {};
  const unpositioned: { id: string }[] = [];

  for (const node of nodes) {
    if (basePositions[node.id]) {
      positions[node.id] = { ...basePositions[node.id] };
    } else {
      unpositioned.push(node);
    }
  }

  if (unpositioned.length === 0) {
    return positions;
  }

  // Calculate in-degree and adjacency
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  nodes.forEach(n => {
    inDegree[n.id] = 0;
    adj[n.id] = [];
  });
  edges.forEach(e => {
    if (adj[e.from]) adj[e.from].push(e.to);
    if (inDegree[e.to] !== undefined) inDegree[e.to]++;
  });

  // Calculate topological depth using longest path
  const depth: Record<string, number> = {};
  nodes.forEach(n => {
    depth[n.id] = inDegree[n.id] === 0 ? 0 : 1;
  });

  for (let iter = 0; iter < nodes.length; iter++) {
    edges.forEach(e => {
      const fromDepth = depth[e.from] || 0;
      if ((depth[e.to] || 0) <= fromDepth) {
        depth[e.to] = fromDepth + 1;
      }
    });
  }

  // Group unpositioned nodes by depth
  const layers: Record<number, { id: string }[]> = {};
  unpositioned.forEach(node => {
    const d = depth[node.id] || 0;
    if (!layers[d]) layers[d] = [];
    layers[d].push(node);
  });

  Object.entries(layers).forEach(([dStr, layerNodes]) => {
    const d = Number(dStr);
    const total = layerNodes.length;
    layerNodes.forEach((node, idx) => {
      positions[node.id] = {
        x: 50 + d * 300,
        y: 260 + (idx - (total - 1) / 2) * 160,
      };
    });
  });

  return positions;
};


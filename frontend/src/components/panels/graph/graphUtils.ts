import {
  FileText,
  Database,
  Activity,
  TrendingUp,
  TrendingDown,
  Scale,
  Brain,
  Shield,
  Zap,
  Layers,
} from 'lucide-react';
import type { GraphNodeStatus } from '../../../types/api';

export const getNodeIcon = (id: string) => {
  switch (id) {
    case 'prefetch_data':
      return Database;
    case 'fundamental_brief':
      return FileText;
    case 'per_asset_analysis':
      return Activity;
    case 'bull_advocate':
      return TrendingUp;
    case 'bear_dissent':
      return TrendingDown;
    case 'debate_judge':
      return Scale;
    case 'reflection':
      return Brain;
    case 'risk_gate':
      return Shield;
    case 'execution':
      return Zap;
    default:
      return Layers;
  }
};

export const getStageKicker = (id: string, fallbackStage?: string): string => {
  switch (id) {
    case 'prefetch_data':
    case 'fundamental_brief':
      return 'STAGE I — MACRO';
    case 'per_asset_analysis':
      return 'STAGE II — SYNTHESIS';
    case 'bull_advocate':
    case 'bear_dissent':
    case 'debate_judge':
      return 'STAGE III — DIALECTIC';
    case 'reflection':
    case 'risk_gate':
      return 'STAGE IV — FORTRESS';
    case 'execution':
      return 'STAGE V — EXECUTION';
    default:
      return fallbackStage ? `STAGE — ${fallbackStage.toUpperCase()}` : 'STAGE — NODE';
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
    case 'skipped':
      return 'var(--color-ink-muted)';
    case 'pending':
    default:
      return 'var(--color-ink-soft)';
  }
};

export const COMPACT_POSITIONS: Record<string, { x: number; y: number }> = {
  prefetch_data: { x: 40, y: 100 },
  fundamental_brief: { x: 40, y: 265 },
  per_asset_analysis: { x: 290, y: 190 },
  bull_advocate: { x: 540, y: 80 },
  bear_dissent: { x: 540, y: 300 },
  debate_judge: { x: 790, y: 190 },
  reflection: { x: 1045, y: 80 },
  risk_gate: { x: 1045, y: 245 },
  execution: { x: 1045, y: 410 },
};

export const WIDE_POSITIONS: Record<string, { x: number; y: number }> = {
  prefetch_data: { x: 40, y: 240 },
  fundamental_brief: { x: 320, y: 240 },
  per_asset_analysis: { x: 600, y: 240 },
  bull_advocate: { x: 890, y: 110 },
  bear_dissent: { x: 890, y: 370 },
  debate_judge: { x: 1180, y: 240 },
  reflection: { x: 1470, y: 240 },
  risk_gate: { x: 1750, y: 240 },
  execution: { x: 2030, y: 240 },
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

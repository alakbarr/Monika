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
      return '01 · INGESTION';
    case 'fundamental_brief':
      return '02 · MACRO BRIEF';
    case 'per_asset_analysis':
      return '03 · SYNTHESIS';
    case 'bull_advocate':
      return '04A · BULL THESIS';
    case 'bear_dissent':
      return '04B · BEAR DISSENT';
    case 'debate_judge':
      return '05 · CHIEF JUDGE';
    case 'reflection':
      return '06 · MEMORY GATE';
    case 'risk_gate':
      return '07 · RISK FORTRESS';
    case 'execution':
      return '08 · MT5 DISPATCH';
    default:
      return fallbackStage ? `STAGE · ${fallbackStage.toUpperCase()}` : 'STAGE · NODE';
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

export interface StageZoneSpec {
  id: string;
  title: string;
  subtitle: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isFortress?: boolean;
}

export const STAGE_ZONES_COMPACT: StageZoneSpec[] = [
  {
    id: 'stage-1',
    title: 'STAGE I · MACRO & INGESTION',
    subtitle: 'PREFETCH + FUNDAMENTAL BRIEF',
    x: 16,
    y: 28,
    width: 228,
    height: 436,
  },
  {
    id: 'stage-2',
    title: 'STAGE II · SYNTHESIS',
    subtitle: 'SMC & QUANT ALPHA',
    x: 266,
    y: 28,
    width: 228,
    height: 436,
  },
  {
    id: 'stage-3',
    title: 'STAGE III · DIALECTIC ARBITRATION',
    subtitle: 'ADVERSARIAL BULL / BEAR + REBUTTAL LOOP + CHIEF JUDGE',
    x: 516,
    y: 28,
    width: 468,
    height: 436,
  },
  {
    id: 'stage-4',
    title: 'STAGE IV · FORTRESS',
    subtitle: 'MEMORY + DETERMINISTIC GATE',
    x: 1006,
    y: 28,
    width: 228,
    height: 436,
    isFortress: true,
  },
  {
    id: 'stage-5',
    title: 'STAGE V · EXECUTION',
    subtitle: 'MT5 SOCKET DISPATCH',
    x: 1256,
    y: 28,
    width: 228,
    height: 436,
  },
];

export const COMPACT_POSITIONS: Record<string, { x: number; y: number }> = {
  prefetch_data: { x: 28, y: 78 },
  fundamental_brief: { x: 28, y: 336 },
  per_asset_analysis: { x: 278, y: 207 },
  bull_advocate: { x: 528, y: 78 },
  bear_dissent: { x: 528, y: 336 },
  debate_judge: { x: 768, y: 207 },
  reflection: { x: 1018, y: 78 },
  risk_gate: { x: 1018, y: 336 },
  execution: { x: 1268, y: 336 },
};

export const WIDE_POSITIONS: Record<string, { x: number; y: number }> = {
  prefetch_data: { x: 40, y: 220 },
  fundamental_brief: { x: 330, y: 220 },
  per_asset_analysis: { x: 620, y: 220 },
  bull_advocate: { x: 910, y: 100 },
  bear_dissent: { x: 910, y: 340 },
  debate_judge: { x: 1200, y: 220 },
  reflection: { x: 1490, y: 220 },
  risk_gate: { x: 1780, y: 220 },
  execution: { x: 2070, y: 220 },
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

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

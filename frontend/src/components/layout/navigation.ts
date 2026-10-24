// ==============================================================================
// File: src/components/layout/navigation.ts
// Description: 5 Swiss Editorial Chapters + Complete 23-View Mapping
// ==============================================================================

import React from 'react';
import {
  CrtMonitorIcon,
  FolderDeskIcon,
  NotebookDeskIcon,
  TelegraphDeskIcon,
  FloppyDiskIcon,
} from '../ui/Icons';

export interface WorkspaceItem {
  id: string;
  roman: string;
  code: string;
  keyNum: string;
  label: string;
  subtitle: string;
  icon: React.ElementType;
  defaultTab: string;
  subTabs: { id: string; label: string }[];
}

export const WORKSPACES: WorkspaceItem[] = [
  {
    id: 'capital',
    roman: 'I',
    code: 'CAP',
    keyNum: '1',
    label: 'Capital',
    subtitle: 'Sculptural Equity Monument, SMC Charts & Position Ledger',
    icon: CrtMonitorIcon,
    defaultTab: 'overview',
    subTabs: [
      { id: 'overview', label: 'Capital Desk' },
      { id: 'positions', label: 'Position Ledger' },
      { id: 'signals', label: 'Signals & Triggers' },
      { id: 'market', label: 'Macro & Watchlist' },
    ],
  },
  {
    id: 'journal',
    roman: 'II',
    code: 'JRN',
    keyNum: '2',
    label: 'Journal',
    subtitle: 'Bull vs Bear Dialectics, LangGraph DAG & Autonomous Memory',
    icon: FolderDeskIcon,
    defaultTab: 'debates',
    subTabs: [
      { id: 'debates', label: 'Bull vs Bear Dialectics' },
      { id: 'analysis', label: 'Market Dispatches' },
      { id: 'brief', label: 'Macro Intelligence Brief' },
      { id: 'graph', label: 'Pipeline DAG & Steering' },
      { id: 'memory', label: 'Memory Vault & Playbooks' },
      { id: 'skills', label: 'Crystallized Skills' },
    ],
  },
  {
    id: 'risk',
    roman: 'III',
    code: 'RSK',
    keyNum: '3',
    label: 'Risk',
    subtitle: 'Mechanical Fortress, Circuit Breakers & Graduation Gate',
    icon: NotebookDeskIcon,
    defaultTab: 'risk',
    subTabs: [
      { id: 'risk', label: 'Mechanical Fortress' },
      { id: 'performance', label: 'Graduation & Attribution' },
      { id: 'edge', label: 'Rolling Expectancy' },
    ],
  },
  {
    id: 'lab',
    roman: 'IV',
    code: 'LAB',
    keyNum: '4',
    label: 'Lab',
    subtitle: 'Point-in-Time Historical Backtest & Multi-Model Benchmark',
    icon: TelegraphDeskIcon,
    defaultTab: 'backtest',
    subTabs: [
      { id: 'backtest', label: 'Historical Backtest' },
      { id: 'benchmark', label: 'LLM Benchmark Lab' },
      { id: 'tokens', label: 'Token & Cost Ledger' },
    ],
  },
  {
    id: 'atelier',
    roman: 'V',
    code: 'ATL',
    keyNum: '5',
    label: 'Atelier',
    subtitle: 'System Configuration, SHA-256 Lineage & PTY Terminal',
    icon: FloppyDiskIcon,
    defaultTab: 'config',
    subTabs: [
      { id: 'config', label: 'Configuration & Schema' },
      { id: 'observability', label: 'Traces & SHA-256 Lineage' },
      { id: 'plugins', label: 'Plugin Marketplace' },
      { id: 'system', label: 'Host Diagnostics' },
      { id: 'terminal', label: 'PTY OS Terminal' },
      { id: 'sessions', label: 'Session Transcripts' },
      { id: 'chat', label: 'Agent Dialogue' },
    ],
  },
];

export interface NavItem {
  id: string;
  label: string;
  chapterId?: string;
  chapterRoman?: string;
  icon?: React.ElementType;
}

export const NAV_ITEMS: NavItem[] = WORKSPACES.flatMap((w) =>
  w.subTabs.map((s) => ({
    id: s.id,
    label: `${w.roman}. ${w.label} — ${s.label}`,
    chapterId: w.id,
    chapterRoman: w.roman,
    icon: w.icon,
  }))
);

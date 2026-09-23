import React from 'react';
import {
  CrtMonitorIcon,
  FolderDeskIcon,
  NotebookDeskIcon,
  TelegraphDeskIcon,
  FloppyDiskIcon,
} from '../ui/RetroIcons';

export interface WorkspaceItem {
  id: string;
  code: string;
  keyNum: string;
  label: string;
  icon: React.ElementType;
  defaultTab: string;
  subTabs: { id: string; label: string }[];
}

export const WORKSPACES: WorkspaceItem[] = [
  {
    id: 'desk',
    code: 'TRD',
    keyNum: '1',
    label: 'Trading Desk',
    icon: CrtMonitorIcon,
    defaultTab: 'overview',
    subTabs: [
      { id: 'overview', label: 'Overview' },
      { id: 'positions', label: 'Position Ledger' },
      { id: 'signals', label: 'Signals & Triggers' },
      { id: 'market', label: 'Market Data' },
    ],
  },
  {
    id: 'intel',
    code: 'INT',
    keyNum: '2',
    label: 'Market Intelligence',
    icon: FolderDeskIcon,
    defaultTab: 'graph',
    subTabs: [
      { id: 'graph', label: 'Pipeline DAG Flow' },
      { id: 'debates', label: 'Debate Arbitration' },
      { id: 'analysis', label: 'Market Analysis' },
      { id: 'brief', label: 'Macroeconomic Intelligence Brief' },
      { id: 'memory', label: 'Memory Vault & Lessons' },
      { id: 'skills', label: 'Crystallized Skills' },
    ],
  },
  {
    id: 'ledger',
    code: 'LED',
    keyNum: '3',
    label: 'Ledger & Risk',
    icon: NotebookDeskIcon,
    defaultTab: 'performance',
    subTabs: [
      { id: 'performance', label: 'P&L Performance' },
      { id: 'edge', label: 'Edge & Expectancy' },
      { id: 'risk', label: 'Risk & Limits' },
      { id: 'tokens', label: 'LLM Token Audit' },
      { id: 'backtest', label: 'Historical Backtest' },
    ],
  },
  {
    id: 'console',
    code: 'TEL',
    keyNum: '4',
    label: 'Telegraph & Desk Console',
    icon: TelegraphDeskIcon,
    defaultTab: 'chat',
    subTabs: [
      { id: 'chat', label: 'Chat' },
      { id: 'sessions', label: 'Session History' },
      { id: 'observability', label: 'Dispatch Audit Log' },
    ],
  },
  {
    id: 'system',
    code: 'SYS',
    keyNum: '5',
    label: 'System Configuration',
    icon: FloppyDiskIcon,
    defaultTab: 'config',
    subTabs: [
      { id: 'config', label: 'Configuration Settings' },
      { id: 'plugins', label: 'Plugin Marketplace & Harness' },
      { id: 'system', label: 'Host Diagnostics' },
    ],
  },
];

// Flat export for backwards compatibility
export interface NavItem {
  id: string;
  label: string;
  icon?: React.ElementType;
}

export const NAV_ITEMS: NavItem[] = WORKSPACES.flatMap((w) =>
  w.subTabs.map((s) => ({ id: s.id, label: s.label, icon: w.icon }))
);

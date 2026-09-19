// ==============================================================================
// File: src/components/layout/BreadcrumbBar.tsx
// Description: Retro OS Breadcrumb Bar displaying current Workspace & Subtab context
// ==============================================================================

import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { WORKSPACES } from './navigation';

export const BreadcrumbBar: React.FC = () => {
  const { activeTab } = useDashboardStore();

  const activeWorkspace =
    WORKSPACES.find((w) => w.subTabs.some((s) => s.id === activeTab)) || WORKSPACES[0];
  const activeSubTab = activeWorkspace.subTabs.find((s) => s.id === activeTab);

  return (
    <div className="breadcrumb-bar" role="navigation" aria-label="Breadcrumb Navigation">
      <span style={{ color: 'var(--color-win-yellow)', fontWeight: 800 }}>
        [{activeWorkspace.keyNum}]
      </span>
      <span>{activeWorkspace.label}</span>
      <span className="breadcrumb-separator">›</span>
      <span style={{ color: 'var(--color-ink)', fontWeight: 800 }}>
        {activeSubTab?.label || activeTab}
      </span>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', letterSpacing: '0.04em' }}>
          MONIKA OS // WORKSPACE {activeWorkspace.code}
        </span>
      </div>
    </div>
  );
};

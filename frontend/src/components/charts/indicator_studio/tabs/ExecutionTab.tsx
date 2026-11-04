// ==============================================================================
// File: src/components/charts/indicator_studio/tabs/ExecutionTab.tsx
// Description: Indicator Studio Tab for AI & Execution Overlays (Active Positions, Execution Markers, Latest AI Proposals)
// ==============================================================================

import React from 'react';
import type { ChartWorkspaceConfig } from '../../../../types/api';

interface ExecutionTabProps {
  activeConfig: ChartWorkspaceConfig;
  commitConfig: (mutator: (prev: ChartWorkspaceConfig) => ChartWorkspaceConfig) => void;
}

export const ExecutionTab: React.FC<ExecutionTabProps> = ({ activeConfig, commitConfig }) => {
  return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--color-ink)',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={activeConfig.overlays.timesfm_cone}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.timesfm_cone = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>TimesFM Foundation Model Quantile Cone (q10/q50/q90)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Zero-Shot Forecast
                </span>
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--color-ink)',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={activeConfig.overlays.show_positions}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.show_positions = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Active Live & Paper Positions (Entry / SL / TP Lines)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-gain)', fontFamily: 'var(--font-mono)' }}>
                  Realtime Execution
                </span>
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--color-ink)',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={activeConfig.overlays.show_ai_proposals}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.show_ai_proposals = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Latest Stage 2 AI Trade Proposal (Hypothesis Levels)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Dialectical Decision
                </span>
              </div>
            </div>

  );
};

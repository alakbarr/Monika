// ==============================================================================
// File: src/components/charts/indicator_studio/tabs/SmcTab.tsx
// Description: Indicator Studio Tab for SMC & Market Structure (Order Blocks, FVGs, Liquidity Pools, Structure Breaks, TimesFM Cone)
// ==============================================================================

import React from 'react';
import type { ChartWorkspaceConfig } from '../../../../types/api';

interface SmcTabProps {
  activeConfig: ChartWorkspaceConfig;
  commitConfig: (mutator: (prev: ChartWorkspaceConfig) => ChartWorkspaceConfig) => void;
}

export const SmcTab: React.FC<SmcTabProps> = ({ activeConfig, commitConfig }) => {
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
                    checked={activeConfig.overlays.smc_order_blocks}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.smc_order_blocks = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Institutional Order Blocks (OB)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Bullish / Bearish Blocks
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
                    checked={activeConfig.overlays.smc_fvg}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.smc_fvg = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Fair Value Gaps (FVG / Imbalances)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Liquidity Inefficiencies
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
                    checked={activeConfig.overlays.smc_bos}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.smc_bos = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Market Structure Breaks (BOS / CHoCH)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Trend Shifts & Continuations
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
                    checked={activeConfig.overlays.smc_liquidity}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.smc_liquidity = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Liquidity Pools (EQH / EQL Sweep Targets)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Stop Clusters
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
                    checked={activeConfig.overlays.volume_profile}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.volume_profile = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Volume Profile (POC / VAH / VAL)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Point of Control & Value Area
                </span>
              </div>
            </div>

  );
};

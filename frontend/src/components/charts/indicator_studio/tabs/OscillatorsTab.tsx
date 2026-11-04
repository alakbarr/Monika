// ==============================================================================
// File: src/components/charts/indicator_studio/tabs/OscillatorsTab.tsx
// Description: Indicator Studio Tab for Oscillators (Volume MA, RSI, MACD, Stochastic, ATR, ADX, Yang-Zhang Volatility, CVD)
// ==============================================================================

import React from 'react';
import type { ChartWorkspaceConfig } from '../../../../types/api';

interface OscillatorsTabProps {
  activeConfig: ChartWorkspaceConfig;
  commitConfig: (mutator: (prev: ChartWorkspaceConfig) => ChartWorkspaceConfig) => void;
}

export const OscillatorsTab: React.FC<OscillatorsTabProps> = ({ activeConfig, commitConfig }) => {
  return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Volume + MA */}
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
                    checked={activeConfig.oscillators.volume.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.volume.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Volume + Moving Average</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    MA Period:
                  </span>
                  <input
                    type="number"
                    value={activeConfig.oscillators.volume.ma_period}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.volume.ma_period = Number(e.target.value) || 20;
                        return p;
                      })
                    }
                    style={{
                      width: '45px',
                      padding: '2px 4px',
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      background: 'var(--color-canvas)',
                      border: '1px solid var(--color-rule)',
                      color: 'var(--color-ink)',
                    }}
                  />
                </div>
              </div>

              {/* RSI */}
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                  flexWrap: 'wrap',
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
                    checked={activeConfig.oscillators.rsi.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.rsi.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Relative Strength Index (RSI)</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                      Period:
                    </span>
                    <input
                      type="number"
                      value={activeConfig.oscillators.rsi.period}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.oscillators.rsi.period = Number(e.target.value) || 14;
                          return p;
                        })
                      }
                      style={{
                        width: '45px',
                        padding: '2px 4px',
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        background: 'var(--color-canvas)',
                        border: '1px solid var(--color-rule)',
                        color: 'var(--color-ink)',
                      }}
                    />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                      OB/OS:
                    </span>
                    <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink)' }}>
                      {activeConfig.oscillators.rsi.overbought}/{activeConfig.oscillators.rsi.oversold}
                    </span>
                  </div>
                </div>
              </div>

              {/* MACD */}
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
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
                    checked={activeConfig.oscillators.macd.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.macd.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>MACD (Moving Average Convergence Divergence)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  (12, 26, 9)
                </span>
              </div>

              {/* Stochastic */}
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
                    checked={activeConfig.oscillators.stochastic.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.stochastic.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Stochastic Oscillator (%K, %D)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  (14, 3)
                </span>
              </div>

              {/* ADX */}
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
                    checked={activeConfig.oscillators.adx.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.adx.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Average Directional Index (ADX + DI)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Trend Strength
                </span>
              </div>

              {/* ATR */}
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
                    checked={activeConfig.oscillators.atr.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.atr.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Average True Range (ATR 14)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Volatility Budget
                </span>
              </div>

              {/* CVD / Volatility */}
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
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
                    checked={activeConfig.oscillators.cvd_volatility.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.oscillators.cvd_volatility.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Cumulative Delta / Advanced Volatility</span>
                </label>

                <select
                  value={activeConfig.oscillators.cvd_volatility.mode}
                  onChange={(e) =>
                    commitConfig((p) => {
                      p.oscillators.cvd_volatility.mode = e.target.value as any;
                      return p;
                    })
                  }
                  style={{
                    padding: '3px 8px',
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    background: 'var(--color-canvas)',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink)',
                  }}
                >
                  <option value="cvd">CVD (Cumulative Volume Delta)</option>
                  <option value="yz_vol">Yang-Zhang Volatility %</option>
                  <option value="ac1">AC1 Autocorrelation (Chop)</option>
                </select>
              </div>
            </div>

  );
};

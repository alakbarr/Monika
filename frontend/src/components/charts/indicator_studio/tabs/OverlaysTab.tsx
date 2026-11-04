// ==============================================================================
// File: src/components/charts/indicator_studio/tabs/OverlaysTab.tsx
// Description: Indicator Studio Tab for Overlays (EMA Ribbon, Bollinger, Keltner, Donchian, Supertrend, VWAP, Pivot Points)
// ==============================================================================

import React from 'react';
import type { ChartWorkspaceConfig } from '../../../../types/api';

interface OverlaysTabProps {
  activeConfig: ChartWorkspaceConfig;
  commitConfig: (mutator: (prev: ChartWorkspaceConfig) => ChartWorkspaceConfig) => void;
}

export const OverlaysTab: React.FC<OverlaysTabProps> = ({ activeConfig, commitConfig }) => {
  const togglePeriodChip = (
    type: 'ema' | 'sma' | 'wma',
    period: number
  ) => {
    commitConfig((prev) => {
      const currentPeriods = prev.overlays[type].periods || [];
      if (currentPeriods.includes(period)) {
        prev.overlays[type].periods = currentPeriods.filter((p) => p !== period);
      } else {
        prev.overlays[type].periods = [...currentPeriods, period].sort((a, b) => a - b);
      }
      return prev;
    });
  };

  return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* EMA Row */}
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
                      checked={activeConfig.overlays.ema.enabled}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.ema.enabled = e.target.checked;
                          return p;
                        })
                      }
                      style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                    />
                    <span>Exponential Moving Averages (EMA)</span>
                  </label>
                  <span
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-ink-muted)',
                    }}
                  >
                    {activeConfig.overlays.ema.periods.join(', ') || 'None selected'}
                  </span>
                </div>

                {/* Period chips */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    Active Periods:
                  </span>
                  {[9, 20, 21, 50, 100, 200].map((period) => {
                    const isChipActive = activeConfig.overlays.ema.periods.includes(period);
                    return (
                      <button
                        key={period}
                        type="button"
                        onClick={() => togglePeriodChip('ema', period)}
                        disabled={!activeConfig.overlays.ema.enabled}
                        style={{
                          padding: '2px 8px',
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          border: `1px solid ${
                            isChipActive ? 'var(--color-ink)' : 'var(--color-rule)'
                          }`,
                          background: isChipActive
                            ? 'var(--color-ink)'
                            : 'var(--color-canvas)',
                          color: isChipActive
                            ? 'var(--color-canvas)'
                            : 'var(--color-ink-secondary)',
                          cursor: activeConfig.overlays.ema.enabled ? 'pointer' : 'not-allowed',
                          opacity: activeConfig.overlays.ema.enabled ? 1 : 0.5,
                        }}
                      >
                        {period}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* SMA Row */}
              <div
                style={{
                  padding: '12px 14px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
                      checked={activeConfig.overlays.sma.enabled}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.sma.enabled = e.target.checked;
                          return p;
                        })
                      }
                      style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                    />
                    <span>Simple Moving Averages (SMA)</span>
                  </label>
                  <span
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-ink-muted)',
                    }}
                  >
                    {activeConfig.overlays.sma.periods.join(', ') || 'None selected'}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    Active Periods:
                  </span>
                  {[20, 50, 100, 200].map((period) => {
                    const isChipActive = activeConfig.overlays.sma.periods.includes(period);
                    return (
                      <button
                        key={period}
                        type="button"
                        onClick={() => togglePeriodChip('sma', period)}
                        disabled={!activeConfig.overlays.sma.enabled}
                        style={{
                          padding: '2px 8px',
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          border: `1px solid ${
                            isChipActive ? 'var(--color-ink)' : 'var(--color-rule)'
                          }`,
                          background: isChipActive
                            ? 'var(--color-ink)'
                            : 'var(--color-canvas)',
                          color: isChipActive
                            ? 'var(--color-canvas)'
                            : 'var(--color-ink-secondary)',
                          cursor: activeConfig.overlays.sma.enabled ? 'pointer' : 'not-allowed',
                          opacity: activeConfig.overlays.sma.enabled ? 1 : 0.5,
                        }}
                      >
                        {period}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Bollinger Bands */}
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
                    checked={activeConfig.overlays.bollinger.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.bollinger.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Bollinger Bands (BB)</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                      Period:
                    </span>
                    <input
                      type="number"
                      min="5"
                      max="200"
                      value={activeConfig.overlays.bollinger.period}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.bollinger.period = Number(e.target.value) || 20;
                          return p;
                        })
                      }
                      style={{
                        width: '50px',
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
                      StdDev:
                    </span>
                    <input
                      type="number"
                      step="0.1"
                      min="0.5"
                      max="5"
                      value={activeConfig.overlays.bollinger.std_dev}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.bollinger.std_dev = Number(e.target.value) || 2.0;
                          return p;
                        })
                      }
                      style={{
                        width: '50px',
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
              </div>

              {/* Keltner Channels */}
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
                    checked={activeConfig.overlays.keltner.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.keltner.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Keltner Channels (KC)</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                      Win:
                    </span>
                    <input
                      type="number"
                      value={activeConfig.overlays.keltner.window}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.keltner.window = Number(e.target.value) || 20;
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
                      Mult:
                    </span>
                    <input
                      type="number"
                      step="0.1"
                      value={activeConfig.overlays.keltner.multiplier}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.keltner.multiplier = Number(e.target.value) || 1.5;
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
              </div>

              {/* Donchian Channels */}
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
                    checked={activeConfig.overlays.donchian.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.donchian.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Donchian Channels (DC)</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    Window:
                  </span>
                  <input
                    type="number"
                    value={activeConfig.overlays.donchian.window}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.donchian.window = Number(e.target.value) || 20;
                        return p;
                      })
                    }
                    style={{
                      width: '50px',
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

              {/* VWAP */}
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
                    checked={activeConfig.overlays.vwap.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.vwap.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Volume-Weighted Average Price (VWAP)</span>
                </label>
                <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                  Institutional Benchmark
                </span>
              </div>

              {/* Supertrend */}
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
                    checked={activeConfig.overlays.supertrend.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.supertrend.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Supertrend Indicator</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                      Period:
                    </span>
                    <input
                      type="number"
                      value={activeConfig.overlays.supertrend.period}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.supertrend.period = Number(e.target.value) || 10;
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
                      Multiplier:
                    </span>
                    <input
                      type="number"
                      step="0.5"
                      value={activeConfig.overlays.supertrend.multiplier}
                      onChange={(e) =>
                        commitConfig((p) => {
                          p.overlays.supertrend.multiplier = Number(e.target.value) || 3.0;
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
              </div>

              {/* Ichimoku Cloud */}
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
                    checked={activeConfig.overlays.ichimoku.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.ichimoku.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Ichimoku Kinko Hyo</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-mono)' }}>
                    (9, 26, 52)
                  </span>
                </div>
              </div>

              {/* Pivot Points */}
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
                    checked={activeConfig.overlays.pivot_points.enabled}
                    onChange={(e) =>
                      commitConfig((p) => {
                        p.overlays.pivot_points.enabled = e.target.checked;
                        return p;
                      })
                    }
                    style={{ accentColor: 'var(--color-ink)', cursor: 'pointer' }}
                  />
                  <span>Pivot Points</span>
                </label>

                <select
                  value={activeConfig.overlays.pivot_points.method}
                  onChange={(e) =>
                    commitConfig((p) => {
                      p.overlays.pivot_points.method = e.target.value as any;
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
                  <option value="classic">Classic (Standard Floor)</option>
                  <option value="fibonacci">Fibonacci Golden Ratio</option>
                  <option value="camarilla">Camarilla (Reversal)</option>
                  <option value="woodie">Woodie (Weighted Close)</option>
                </select>
              </div>
            </div>

  );
};

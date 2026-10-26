// ==============================================================================
// File: src/components/charts/IndicatorStudioPopover.tsx
// Description: Swiss Editorial & Liquid Glass v4.0 Institutional Indicator Studio
// Popover & Configuration Engine.
// Allows seamless switching between Global Asset Defaults and Symbol-Specific Pins,
// 1-Click Institutional Presets, Multi-Pane Overlays & Oscillators, and AI Vision Sync.
// ==============================================================================

import React, { useState, useEffect } from 'react';
import {
  X,
  SlidersHorizontal,
  RotateCcw,
  Sparkles,
  Layers,
  Activity,
  Cpu,
  TrendingUp,
  Check,
  Globe,
  Pin,
} from 'lucide-react';
import { useDashboardStore } from '../../store/dashboardStore';
import type {
  ChartPresetId,
  ChartWorkspaceConfig,
} from '../../types/api';
import {
  countActiveIndicators,
} from '../../lib/chartIndicatorsClientMath';

interface IndicatorStudioPopoverProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
}

type StudioTab = 'overlays' | 'oscillators' | 'smc' | 'execution';

const PRESET_OPTIONS: Array<{ id: ChartPresetId; label: string; desc: string }> = [
  {
    id: 'smc_institutional',
    label: 'SMC Institutional',
    desc: 'OB, FVG, Liquidity, VWAP & TimesFM Cone',
  },
  {
    id: 'trend_momentum',
    label: 'Trend & Momentum',
    desc: 'EMA Ribbon, Supertrend, MACD & ADX',
  },
  {
    id: 'volatility_reversion',
    label: 'Volatility & Reversion',
    desc: 'Bollinger, Keltner, Donchian, RSI & YZ Vol',
  },
  {
    id: 'quant_orderflow',
    label: 'Orderflow & Quant',
    desc: 'CVD, Volume Profile, VWAP & TimesFM',
  },
];

export const IndicatorStudioPopover: React.FC<IndicatorStudioPopoverProps> = ({
  isOpen,
  onClose,
  symbol,
}) => {
  const getEffectiveChartConfig = useDashboardStore((s) => s.getEffectiveChartConfig);
  const saveChartWorkspaceConfig = useDashboardStore((s) => s.saveChartWorkspaceConfig);
  const applyChartPreset = useDashboardStore((s) => s.applyChartPreset);
  const resetSymbolChartOverride = useDashboardStore((s) => s.resetSymbolChartOverride);

  const { config: activeConfig, isSymbolOverride } = getEffectiveChartConfig(symbol);

  // Persistence scope: defaults to 'symbol' if already overridden, else 'global'
  const [scope, setScope] = useState<'global' | 'symbol'>(
    isSymbolOverride ? 'symbol' : 'global'
  );
  const [activeTab, setActiveTab] = useState<StudioTab>('overlays');

  // Sync scope state when override changes
  useEffect(() => {
    if (isSymbolOverride) {
      setScope('symbol');
    }
  }, [isSymbolOverride, symbol]);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const counts = countActiveIndicators(activeConfig);

  // Helper to commit config changes immediately (optimistic + persistent)
  const commitConfig = (mutator: (prev: ChartWorkspaceConfig) => ChartWorkspaceConfig) => {
    const updated = mutator(JSON.parse(JSON.stringify(activeConfig)));
    updated.preset_id = 'custom';
    saveChartWorkspaceConfig(symbol, updated, scope);
  };

  const handleApplyPreset = (presetId: ChartPresetId) => {
    applyChartPreset(symbol, presetId, scope);
  };

  const handleResetOverride = async () => {
    await resetSymbolChartOverride(symbol);
    setScope('global');
  };

  const toggleVisionSync = () => {
    commitConfig((prev) => {
      prev.vision_sync_enabled = !prev.vision_sync_enabled;
      return prev;
    });
  };

  // Overlay Period Chip toggler
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
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="indicator-studio-title"
      className="editorial-modal-scrim"
      style={{
        zIndex: 10000,
        padding: '16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '720px',
          maxHeight: '90vh',
          background: 'var(--color-canvas)',
          border: '1px solid var(--color-rule-strong)',
          boxShadow: 'var(--shadow-modal, 0 20px 45px rgba(0,0,0,0.35))',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* ================================================================== */}
        {/* 1. Header Bar: Title, Scope Switcher & Close                       */}
        {/* ================================================================== */}
        <div
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-well)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <SlidersHorizontal size={16} style={{ color: 'var(--color-ink)' }} />
            <div>
              <div
                id="indicator-studio-title"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  color: 'var(--color-ink)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span>Indicator Studio</span>
                <span
                  style={{
                    fontSize: '11px',
                    padding: '1px 6px',
                    borderRadius: '2px',
                    background: 'var(--color-canvas)',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink-secondary)',
                  }}
                >
                  {symbol}
                </span>
                {isSymbolOverride && (
                  <span
                    style={{
                      fontSize: '10px',
                      padding: '1px 6px',
                      background: 'var(--color-warn-bg, rgba(217, 119, 6, 0.15))',
                      color: 'var(--color-warn)',
                      border: '1px solid var(--color-warn)',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                    }}
                  >
                    PINNED OVERRIDE
                  </span>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Scope Selector: Global vs Symbol */}
            <div
              style={{
                display: 'inline-flex',
                background: 'var(--color-canvas)',
                border: '1px solid var(--color-rule)',
                padding: '2px',
                borderRadius: '3px',
              }}
            >
              <button
                type="button"
                onClick={() => setScope('global')}
                style={{
                  padding: '4px 8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  background: scope === 'global' ? 'var(--color-ink)' : 'transparent',
                  color: scope === 'global' ? 'var(--color-canvas)' : 'var(--color-ink-secondary)',
                  fontWeight: scope === 'global' ? 600 : 400,
                  transition: 'all 0.15s ease',
                }}
                title="Save changes to global chart default for all symbols"
              >
                <Globe size={12} />
                Global
              </button>
              <button
                type="button"
                onClick={() => setScope('symbol')}
                style={{
                  padding: '4px 8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  background: scope === 'symbol' ? 'var(--color-ink)' : 'transparent',
                  color: scope === 'symbol' ? 'var(--color-canvas)' : 'var(--color-ink-secondary)',
                  fontWeight: scope === 'symbol' ? 600 : 400,
                  transition: 'all 0.15s ease',
                }}
                title={`Pin custom indicator workspace exclusively for ${symbol}`}
              >
                <Pin size={12} />
                {symbol}
              </button>
            </div>

            {/* Reset to Global button (visible when symbol override exists) */}
            {isSymbolOverride && (
              <button
                type="button"
                onClick={handleResetOverride}
                style={{
                  padding: '4px 8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  border: '1px solid var(--color-rule)',
                  background: 'var(--color-canvas)',
                  color: 'var(--color-ink-secondary)',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                title={`Discard custom override and inherit Global Workspace`}
              >
                <RotateCcw size={12} />
                Reset
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              aria-label="Close indicator studio"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-ink-muted)',
                cursor: 'pointer',
                padding: '4px',
                display: 'inline-flex',
                alignItems: 'center',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ================================================================== */}
        {/* 2. Subheader: Presets Bar & AI Vision Telemetry Sync               */}
        {/* ================================================================== */}
        <div
          style={{
            padding: '12px 20px',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-canvas)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          {/* Presets Chips */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--color-ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                fontWeight: 600,
              }}
            >
              1-Click Presets:
            </span>
            {PRESET_OPTIONS.map((p) => {
              const isSelected = activeConfig.preset_id === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleApplyPreset(p.id)}
                  style={{
                    padding: '4px 10px',
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    border: `1px solid ${
                      isSelected ? 'var(--color-ink)' : 'var(--color-rule)'
                    }`,
                    background: isSelected ? 'var(--color-well)' : 'var(--color-canvas)',
                    color: isSelected ? 'var(--color-ink)' : 'var(--color-ink-secondary)',
                    fontWeight: isSelected ? 600 : 400,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    transition: 'all 0.15s ease',
                  }}
                  title={p.desc}
                >
                  {isSelected && <Check size={11} style={{ color: 'var(--color-gain)' }} />}
                  {p.label}
                </button>
              );
            })}
          </div>

          {/* AI Vision & Telemetry Sync Toggle */}
          <button
            type="button"
            onClick={toggleVisionSync}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              border: `1px solid ${
                activeConfig.vision_sync_enabled
                  ? 'var(--color-gain)'
                  : 'var(--color-rule)'
              }`,
              background: activeConfig.vision_sync_enabled
                ? 'var(--color-gain-bg, rgba(16, 185, 129, 0.1))'
                : 'var(--color-well)',
              color: activeConfig.vision_sync_enabled
                ? 'var(--color-gain)'
                : 'var(--color-ink-muted)',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 600,
            }}
            title="Stage 2 AI Vision Sync: Transmits enabled technical indicators and SMC zones into LLM vision analysis context"
          >
            <Sparkles size={12} />
            <span>AI Stage 2 Vision Sync:</span>
            <span>{activeConfig.vision_sync_enabled ? 'ON' : 'OFF'}</span>
          </button>
        </div>

        {/* ================================================================== */}
        {/* 3. Tab Navigation                                                  */}
        {/* ================================================================== */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid var(--color-rule)',
            background: 'var(--color-well)',
            overflowX: 'auto',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('overlays')}
            style={{
              flex: 1,
              padding: '10px 14px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: activeTab === 'overlays' ? 700 : 500,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              background: activeTab === 'overlays' ? 'var(--color-canvas)' : 'transparent',
              color: activeTab === 'overlays' ? 'var(--color-ink)' : 'var(--color-ink-secondary)',
              border: 'none',
              borderBottom: `2px solid ${
                activeTab === 'overlays' ? 'var(--color-ink)' : 'transparent'
              }`,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <Layers size={13} />
            <span>Overlays</span>
            <span
              style={{
                fontSize: '10px',
                padding: '0 5px',
                borderRadius: '999px',
                background: 'var(--color-well-sunken, rgba(0,0,0,0.06))',
                color: 'var(--color-ink-muted)',
              }}
            >
              {counts.overlaysCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('oscillators')}
            style={{
              flex: 1,
              padding: '10px 14px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: activeTab === 'oscillators' ? 700 : 500,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              background: activeTab === 'oscillators' ? 'var(--color-canvas)' : 'transparent',
              color:
                activeTab === 'oscillators' ? 'var(--color-ink)' : 'var(--color-ink-secondary)',
              border: 'none',
              borderBottom: `2px solid ${
                activeTab === 'oscillators' ? 'var(--color-ink)' : 'transparent'
              }`,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <Activity size={13} />
            <span>Oscillators</span>
            <span
              style={{
                fontSize: '10px',
                padding: '0 5px',
                borderRadius: '999px',
                background: 'var(--color-well-sunken, rgba(0,0,0,0.06))',
                color: 'var(--color-ink-muted)',
              }}
            >
              {counts.oscillatorsCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('smc')}
            style={{
              flex: 1,
              padding: '10px 14px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: activeTab === 'smc' ? 700 : 500,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              background: activeTab === 'smc' ? 'var(--color-canvas)' : 'transparent',
              color: activeTab === 'smc' ? 'var(--color-ink)' : 'var(--color-ink-secondary)',
              border: 'none',
              borderBottom: `2px solid ${
                activeTab === 'smc' ? 'var(--color-ink)' : 'transparent'
              }`,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <TrendingUp size={13} />
            <span>SMC & Structure</span>
            <span
              style={{
                fontSize: '10px',
                padding: '0 5px',
                borderRadius: '999px',
                background: 'var(--color-well-sunken, rgba(0,0,0,0.06))',
                color: 'var(--color-ink-muted)',
              }}
            >
              {counts.smcCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('execution')}
            style={{
              flex: 1,
              padding: '10px 14px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: activeTab === 'execution' ? 700 : 500,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              background: activeTab === 'execution' ? 'var(--color-canvas)' : 'transparent',
              color: activeTab === 'execution' ? 'var(--color-ink)' : 'var(--color-ink-secondary)',
              border: 'none',
              borderBottom: `2px solid ${
                activeTab === 'execution' ? 'var(--color-ink)' : 'transparent'
              }`,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <Cpu size={13} />
            <span>AI & Execution</span>
          </button>
        </div>

        {/* ================================================================== */}
        {/* 4. Tab Body: Scrollable Panel                                      */}
        {/* ================================================================== */}
        <div
          style={{
            padding: '20px',
            overflowY: 'auto',
            maxHeight: 'calc(90vh - 180px)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {/* TAB 1: OVERLAYS */}
          {activeTab === 'overlays' && (
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
          )}

          {/* TAB 2: OSCILLATORS */}
          {activeTab === 'oscillators' && (
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
          )}

          {/* TAB 3: SMC & STRUCTURE */}
          {activeTab === 'smc' && (
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
          )}

          {/* TAB 4: AI & EXECUTION OVERLAYS */}
          {activeTab === 'execution' && (
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
          )}
        </div>

        {/* ================================================================== */}
        {/* 5. Footer Bar: Summary and Close                                   */}
        {/* ================================================================== */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid var(--color-rule)',
            background: 'var(--color-well)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--color-ink-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <span>
              Target:{' '}
              <strong style={{ color: 'var(--color-ink)' }}>
                {scope === 'global' ? 'All Assets (Global Default)' : `${symbol} Only`}
              </strong>
            </span>
            <span>•</span>
            <span>{counts.total} active components</span>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '6px 16px',
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              background: 'var(--color-ink)',
              color: 'var(--color-canvas)',
              border: 'none',
              borderRadius: '2px',
              cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

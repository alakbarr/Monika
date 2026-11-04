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
import { OverlaysTab } from './indicator_studio/tabs/OverlaysTab';
import { OscillatorsTab } from './indicator_studio/tabs/OscillatorsTab';
import { SmcTab } from './indicator_studio/tabs/SmcTab';
import { ExecutionTab } from './indicator_studio/tabs/ExecutionTab';

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
            <OverlaysTab activeConfig={activeConfig} commitConfig={commitConfig} />
          )}

          {/* TAB 2: OSCILLATORS */}
          {activeTab === 'oscillators' && (
            <OscillatorsTab activeConfig={activeConfig} commitConfig={commitConfig} />
          )}

          {/* TAB 3: SMC & STRUCTURE */}
          {activeTab === 'smc' && (
            <SmcTab activeConfig={activeConfig} commitConfig={commitConfig} />
          )}

          {/* TAB 4: AI & EXECUTION OVERLAYS */}
          {activeTab === 'execution' && (
            <ExecutionTab activeConfig={activeConfig} commitConfig={commitConfig} />
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

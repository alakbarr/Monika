// ==============================================================================
// File: src/components/charts/candlestick/ChartControlsToolbar.tsx
// Description: Multi-Pane financial chart workstation controls toolbar:
// Symbol selector, live quote/spread, timeframe selector, 1-click presets,
// Indicator Studio trigger, AI Vision Sync, and Fullscreen toggle.
// ==============================================================================

import React from 'react';
import { Badge } from '../../ui/Badge';
import {
  RefreshCw,
  Maximize2,
  Minimize2,
  Sparkles,
  SlidersHorizontal,
  Pin,
  Globe,
} from 'lucide-react';
import { formatPrice, PRESET_BUTTONS, TIMEFRAMES } from './chartUtils';
import type { ChartPresetId, ChartWorkspaceConfig } from '../../../types/api';

interface ChartControlsToolbarProps {
  symbol: string;
  displaySymbols: string[];
  lastPrice: number | null;
  spreadPips: number | null;
  source: string;
  timeframe: string;
  loading: boolean;
  activeConfig: ChartWorkspaceConfig;
  isSymbolPinned: boolean;
  isStudioOpen: boolean;
  isFullscreen: boolean;
  activeIndicatorsCount: { total: number };
  onSelectSymbol: (s: string) => void;
  onSelectTimeframe: (tf: string) => void;
  onRefresh: () => void;
  onApplyPreset: (presetId: ChartPresetId) => void;
  onOpenStudio: () => void;
  onToggleVisionSync: () => void;
  onToggleFullscreen: () => void;
}

export const ChartControlsToolbar: React.FC<ChartControlsToolbarProps> = ({
  symbol,
  displaySymbols,
  lastPrice,
  spreadPips,
  source,
  timeframe,
  loading,
  activeConfig,
  isSymbolPinned,
  isStudioOpen,
  isFullscreen,
  activeIndicatorsCount,
  onSelectSymbol,
  onSelectTimeframe,
  onRefresh,
  onApplyPreset,
  onOpenStudio,
  onToggleVisionSync,
  onToggleFullscreen,
}) => {
  const getSourceBadge = (src: string) => {
    switch (src) {
      case 'mt5':
        return <Badge variant="profit" size="sm">MT5 LIVE</Badge>;
      case 'database':
        return <Badge variant="neutral" size="sm">DB HISTORICAL</Badge>;
      case 'synthetic_preview':
        return <Badge variant="warn" size="sm">SYNTHETIC PREVIEW</Badge>;
      case 'demo':
      default:
        return <Badge variant="neutral" size="sm">DEMO</Badge>;
    }
  };

  return (
    <>
      {/* ==================================================================== */}
      {/* Row 1: Symbol Pills, Live Quote, Timeframe, Refresh                  */}
      {/* ==================================================================== */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: '12px',
        }}
      >
        {/* Symbol Pills & Live Quote */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {displaySymbols.map((s) => {
              const isSelected = symbol.toUpperCase() === s;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSelectSymbol(s)}
                  className="touch-target-expand"
                  style={{
                    padding: '4px 8px',
                    borderRadius: '2px',
                    fontSize: '11px',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono)',
                    border: `1px solid ${isSelected ? 'var(--color-ink)' : 'var(--color-border)'}`,
                    background: isSelected ? 'var(--color-ink)' : 'transparent',
                    color: isSelected ? 'var(--color-surface)' : 'var(--color-ink-muted)',
                    cursor: 'pointer',
                  }}
                >
                  {s}
                </button>
              );
            })}
          </div>

          {lastPrice !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                className="tabular-nums"
                style={{
                  fontSize: '17px',
                  fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--color-ink)',
                }}
              >
                {formatPrice(lastPrice, symbol)}
              </span>
              {spreadPips !== null && (
                <Badge variant="neutral" size="sm">
                  SPREAD: {spreadPips.toFixed(1)} P
                </Badge>
              )}
              {getSourceBadge(source)}
            </div>
          )}
        </div>

        {/* Timeframes & Refresh */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'flex',
              gap: '2px',
              background: 'var(--color-surface-well)',
              padding: '2px',
              borderRadius: '2px',
            }}
          >
            {TIMEFRAMES.map((tf) => {
              const isTfSelected = timeframe === tf;
              return (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onSelectTimeframe(tf)}
                  className="touch-target-expand"
                  style={{
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono)',
                    borderRadius: '2px',
                    border: 'none',
                    background: isTfSelected ? 'var(--color-surface)' : 'transparent',
                    color: isTfSelected ? 'var(--color-ink)' : 'var(--color-ink-muted)',
                    cursor: 'pointer',
                    borderBottom: isTfSelected ? '2px solid var(--color-ink)' : 'none',
                  }}
                >
                  {tf}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="touch-target-expand"
            style={{
              padding: '6px',
              borderRadius: '2px',
              border: '1px solid var(--color-border)',
              background: 'transparent',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
            }}
            title="Refresh Market Candles & Telemetry"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* ==================================================================== */}
      {/* Row 2: Workstation Controls (Presets, Studio, Vision Sync, Fullscreen)*/}
      {/* ==================================================================== */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px',
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: '10px',
        }}
      >
        {/* Preset Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)', fontWeight: 700, marginRight: '4px' }}>
            PRESET:
          </span>
          {PRESET_BUTTONS.map((p) => {
            const isSelected = activeConfig.preset_id === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onApplyPreset(p.id)}
                className="touch-target-expand"
                style={{
                  padding: '3px 8px',
                  fontSize: '11px',
                  fontWeight: isSelected ? 700 : 500,
                  fontFamily: 'var(--font-mono)',
                  borderRadius: '2px',
                  border: `1px solid ${isSelected ? 'var(--color-ink)' : 'var(--color-border)'}`,
                  background: isSelected ? 'var(--color-ink)' : 'transparent',
                  color: isSelected ? 'var(--color-surface)' : 'var(--color-ink-muted)',
                  cursor: 'pointer',
                }}
                title={`Apply ${p.label} Preset`}
              >
                {p.label}
              </button>
            );
          })}
        </div>

        {/* Studio Popover Toggle, Pin Scope, Vision Sync & Fullscreen */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {/* Pin Scope Badge */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '3px 6px',
              fontSize: '10px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              borderRadius: '2px',
              border: '1px solid var(--color-border)',
              color: isSymbolPinned ? 'var(--color-warning)' : 'var(--color-ink-muted)',
              background: isSymbolPinned ? 'var(--color-warning-soft)' : 'transparent',
            }}
            title={isSymbolPinned ? `This asset has a custom pinned configuration` : `Using global workspace defaults`}
          >
            {isSymbolPinned ? <Pin size={10} /> : <Globe size={10} />}
            <span>{isSymbolPinned ? `PINNED (${symbol})` : 'GLOBAL'}</span>
          </div>

          {/* Indicator Studio Button */}
          <button
            type="button"
            onClick={onOpenStudio}
            className="touch-target-expand"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              fontSize: '11px',
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              borderRadius: '2px',
              border: '1px solid var(--color-ink)',
              background: isStudioOpen ? 'var(--color-ink)' : 'transparent',
              color: isStudioOpen ? 'var(--color-surface)' : 'var(--color-ink)',
              cursor: 'pointer',
            }}
            title="Open Indicator Studio"
          >
            <SlidersHorizontal size={12} />
            <span>INDICATORS</span>
            <span
              style={{
                padding: '0 4px',
                borderRadius: '2px',
                fontSize: '10px',
                fontWeight: 800,
                background: isStudioOpen ? 'var(--color-surface)' : 'var(--color-ink)',
                color: isStudioOpen ? 'var(--color-ink)' : 'var(--color-surface)',
              }}
            >
              {activeIndicatorsCount.total}
            </span>
          </button>

          {/* AI Vision Sync Toggle */}
          <button
            type="button"
            onClick={onToggleVisionSync}
            className="touch-target-expand"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              fontSize: '11px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              borderRadius: '2px',
              border: `1px solid ${activeConfig.vision_sync_enabled ? 'var(--color-profit)' : 'var(--color-border)'}`,
              background: activeConfig.vision_sync_enabled ? 'var(--color-profit-soft)' : 'transparent',
              color: activeConfig.vision_sync_enabled ? 'var(--color-profit)' : 'var(--color-ink-muted)',
              cursor: 'pointer',
            }}
            title="Toggle AI Vision & Quant Telemetry Synchronization"
          >
            <Sparkles size={12} />
            <span>{activeConfig.vision_sync_enabled ? 'VISION + QUANT SYNC' : 'VISION SYNC OFF'}</span>
          </button>

          {/* Fullscreen Expand Button */}
          <button
            type="button"
            onClick={onToggleFullscreen}
            className="touch-target-expand"
            style={{
              padding: '4px 8px',
              borderRadius: '2px',
              border: '1px solid var(--color-border)',
              background: isFullscreen ? 'var(--color-ink)' : 'transparent',
              color: isFullscreen ? 'var(--color-surface)' : 'var(--color-ink-muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
            }}
            title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen Workstation'}
          >
            {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            <span>{isFullscreen ? 'EXIT' : 'EXPAND'}</span>
          </button>
        </div>
      </div>
    </>
  );
};

import React from 'react';
import { ZoomIn, ZoomOut, Maximize2, RotateCcw, Play, LayoutGrid, StretchHorizontal } from 'lucide-react';

interface GraphControlsProps {
  onZoom: (factor: number) => void;
  onReset: () => void;
  onTriggerCycle: () => void;
  triggering: boolean;
  layoutMode: 'compact' | 'wide';
  onChangeLayoutMode: (mode: 'compact' | 'wide') => void;
  autoFit: boolean;
  onToggleAutoFit: () => void;
}

export const GraphControls: React.FC<GraphControlsProps> = ({
  onZoom,
  onReset,
  onTriggerCycle,
  triggering,
  layoutMode,
  onChangeLayoutMode,
  autoFit,
  onToggleAutoFit,
}) => {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
      {/* Layout Mode Switcher */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--color-paper)',
          border: '1.5px solid var(--color-rule)',
          borderRadius: 'var(--radius-sm)',
          boxShadow: '1.5px 1.5px 0 var(--color-rule)',
          padding: '2px',
          gap: '2px',
        }}
      >
        <button
          onClick={() => onChangeLayoutMode('compact')}
          title="Compact Descending Flow (Screen-Fitted Multi-tier)"
          style={{
            background: layoutMode === 'compact' ? 'var(--color-win-yellow)' : 'transparent',
            color: layoutMode === 'compact' ? '#1C1917' : 'var(--color-ink-soft)',
            border: layoutMode === 'compact' ? '1px solid var(--color-rule)' : '1px solid transparent',
            padding: '4px 8px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: layoutMode === 'compact' ? 800 : 600,
          }}
        >
          <LayoutGrid size={13} />
          <span>COMPACT</span>
        </button>
        <button
          onClick={() => onChangeLayoutMode('wide')}
          title="Wide Linear Flow"
          style={{
            background: layoutMode === 'wide' ? 'var(--color-win-yellow)' : 'transparent',
            color: layoutMode === 'wide' ? '#1C1917' : 'var(--color-ink-soft)',
            border: layoutMode === 'wide' ? '1px solid var(--color-rule)' : '1px solid transparent',
            padding: '4px 8px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: layoutMode === 'wide' ? 800 : 600,
          }}
        >
          <StretchHorizontal size={13} />
          <span>WIDE</span>
        </button>
      </div>

      {/* Auto-Fit Toggle & Viewport Controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--color-paper)',
          border: '1.5px solid var(--color-rule)',
          borderRadius: 'var(--radius-sm)',
          boxShadow: '1.5px 1.5px 0 var(--color-rule)',
          padding: '2px',
          gap: '2px',
        }}
      >
        <button
          onClick={onToggleAutoFit}
          title={autoFit ? 'Auto-Fit Enabled (Adapts to screen and inspector resize)' : 'Auto-Fit Disabled (Manual Zoom Active)'}
          style={{
            background: autoFit ? 'var(--color-profit-dim)' : 'transparent',
            color: autoFit ? 'var(--color-ledger-green)' : 'var(--color-ink-soft)',
            border: autoFit ? '1px solid var(--color-ledger-green)' : '1px solid transparent',
            padding: '4px 8px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: autoFit ? 800 : 600,
          }}
        >
          <Maximize2 size={13} />
          <span>{autoFit ? 'AUTO-FIT: ON' : 'FIT SCREEN'}</span>
        </button>
        <button
          onClick={() => onZoom(1.15)}
          title="Zoom In"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-ink)',
            padding: '5px 7px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomIn size={14} />
        </button>
        <button
          onClick={() => onZoom(0.85)}
          title="Zoom Out"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-ink)',
            padding: '5px 7px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomOut size={14} />
        </button>
        <button
          onClick={onReset}
          title="Reset Viewport"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-ink)',
            padding: '5px 7px',
            borderRadius: '2px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <RotateCcw size={14} />
        </button>
      </div>

      {/* Retro Run Cycle Action Button */}
      <button
        onClick={onTriggerCycle}
        disabled={triggering}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 14px',
          background: triggering ? 'var(--color-surface)' : 'var(--color-win-yellow)',
          color: '#1C1917',
          border: '1.5px solid var(--color-rule)',
          borderRadius: 'var(--radius-sm)',
          boxShadow: triggering ? 'none' : '1.5px 1.5px 0 var(--color-rule)',
          fontWeight: 800,
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-precision)',
          letterSpacing: '0.04em',
          cursor: triggering ? 'not-allowed' : 'pointer',
          opacity: triggering ? 0.7 : 1,
          textTransform: 'uppercase',
        }}
      >
        <Play size={13} fill="currentColor" />
        {triggering ? 'TRIGGERING...' : 'RUN CYCLE'}
      </button>
    </div>
  );
};

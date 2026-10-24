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
          border: '1px solid var(--color-rule)',
        }}
      >
        <button
          onClick={() => onChangeLayoutMode('compact')}
          title="Compact Architectural Schematic"
          style={{
            background: layoutMode === 'compact' ? 'var(--color-ink)' : 'transparent',
            color: layoutMode === 'compact' ? 'var(--color-paper)' : 'var(--color-ink-soft)',
            border: 'none',
            borderRight: '1px solid var(--color-rule)',
            padding: '5px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: 600,
          }}
        >
          <LayoutGrid size={12} />
          <span>COMPACT</span>
        </button>
        <button
          onClick={() => onChangeLayoutMode('wide')}
          title="Linear Architectural Flow"
          style={{
            background: layoutMode === 'wide' ? 'var(--color-ink)' : 'transparent',
            color: layoutMode === 'wide' ? 'var(--color-paper)' : 'var(--color-ink-soft)',
            border: 'none',
            padding: '5px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: 600,
          }}
        >
          <StretchHorizontal size={12} />
          <span>LINEAR</span>
        </button>
      </div>

      {/* Auto-Fit Toggle & Viewport Controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--color-paper)',
          border: '1px solid var(--color-rule)',
        }}
      >
        <button
          onClick={onToggleAutoFit}
          title={autoFit ? 'Auto-Fit Enabled' : 'Auto-Fit Disabled'}
          style={{
            background: autoFit ? 'var(--color-ink)' : 'transparent',
            color: autoFit ? 'var(--color-paper)' : 'var(--color-ink-soft)',
            border: 'none',
            borderRight: '1px solid var(--color-rule)',
            padding: '5px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '11px',
            fontFamily: 'var(--font-precision)',
            fontWeight: 600,
          }}
        >
          <Maximize2 size={12} />
          <span>{autoFit ? 'AUTO-FIT' : 'FIT'}</span>
        </button>
        <button
          onClick={() => onZoom(1.15)}
          title="Zoom In"
          style={{
            background: 'transparent',
            border: 'none',
            borderRight: '1px solid var(--color-rule)',
            color: 'var(--color-ink)',
            padding: '5px 8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomIn size={13} />
        </button>
        <button
          onClick={() => onZoom(0.85)}
          title="Zoom Out"
          style={{
            background: 'transparent',
            border: 'none',
            borderRight: '1px solid var(--color-rule)',
            color: 'var(--color-ink)',
            padding: '5px 8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomOut size={13} />
        </button>
        <button
          onClick={onReset}
          title="Reset Viewport"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-ink)',
            padding: '5px 8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <RotateCcw size={13} />
        </button>
      </div>

      {/* Run Cycle Action Button */}
      <button
        onClick={onTriggerCycle}
        disabled={triggering}
        className="editorial-btn editorial-btn--accent"
      >
        <Play size={11} fill="currentColor" />
        {triggering ? 'DISPATCHING...' : 'RUN CYCLE'}
      </button>
    </div>
  );
};

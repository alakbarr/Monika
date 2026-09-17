import React from 'react';
import { ZoomIn, ZoomOut, Maximize2, RotateCcw, Play } from 'lucide-react';

interface GraphControlsProps {
  onZoom: (factor: number) => void;
  onFitScreen: () => void;
  onReset: () => void;
  onTriggerCycle: () => void;
  triggering: boolean;
}

export const GraphControls: React.FC<GraphControlsProps> = ({
  onZoom,
  onFitScreen,
  onReset,
  onTriggerCycle,
  triggering,
}) => {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--color-surface-elevated)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-border)',
          padding: '2px',
        }}
      >
        <button
          onClick={() => onZoom(1.15)}
          title="Zoom In"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            padding: '6px 8px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => onZoom(0.85)}
          title="Zoom Out"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            padding: '6px 8px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ZoomOut size={16} />
        </button>
        <button
          onClick={onFitScreen}
          title="Fit to Screen"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            padding: '6px 8px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Maximize2 size={16} />
        </button>
        <button
          onClick={onReset}
          title="Reset Viewport"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-secondary)',
            padding: '6px 8px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <RotateCcw size={16} />
        </button>
      </div>

      <button
        onClick={onTriggerCycle}
        disabled={triggering}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '8px 16px',
          background: 'linear-gradient(90deg, var(--color-primary) 0%, var(--color-primary-active) 100%)',
          color: 'var(--color-on-primary)',
          border: 'none',
          borderRadius: 'var(--radius-md)',
          fontWeight: 600,
          fontSize: 'var(--text-body-sm)',
          cursor: triggering ? 'not-allowed' : 'pointer',
          boxShadow: '0 4px 12px rgba(245,166,35,0.25)',
          opacity: triggering ? 0.7 : 1,
        }}
      >
        <Play size={14} fill="currentColor" />
        {triggering ? 'Triggering...' : 'Run Cycle'}
      </button>
    </div>
  );
};

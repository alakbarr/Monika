import React, { useEffect } from 'react';
import { X } from 'lucide-react';

interface Shortcut {
  key: string;
  description: string;
  category: string;
}

const SHORTCUTS: Shortcut[] = [
  { key: '1', description: 'Chapter I. Capital — Sculptural Monument & Ledger', category: 'Navigation' },
  { key: '2', description: 'Chapter II. Journal — Dialectics, DAG & Memory', category: 'Navigation' },
  { key: '3', description: 'Chapter III. Risk — Mechanical Fortress & Edge', category: 'Navigation' },
  { key: '4', description: 'Chapter IV. Lab — Backtest & Model Benchmark', category: 'Navigation' },
  { key: '5', description: 'Chapter V. Atelier — Config, Lineage & Terminal', category: 'Navigation' },
  { key: '⌘K / Ctrl+K', description: 'Open Command Palette', category: 'Command' },
  { key: 'T', description: 'Toggle Alabaster Light / Graphite Dark Mode', category: 'Display' },
  { key: '?', description: 'Toggle Keyboard Shortcuts Reference', category: 'System' },
  { key: 'ESC', description: 'Dismiss Modal / Drawer', category: 'System' },
];

interface KeyboardShortcutsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KeyboardShortcutsPanel: React.FC<KeyboardShortcutsPanelProps> = ({ isOpen, onClose }) => {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="editorial-modal-scrim"
      style={{
        zIndex: 10000,
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '520px',
          background: 'var(--color-canvas)',
          border: '1px solid var(--color-rule-strong)',
          boxShadow: 'var(--shadow-modal)',
        }}
      >
        <div
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          <span>Keyboard Navigation & Command Reference</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
              display: 'inline-flex',
            }}
          >
            <X size={15} />
          </button>
        </div>

        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column' }}>
          {SHORTCUTS.map((s, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 0',
                borderBottom: idx === SHORTCUTS.length - 1 ? 'none' : '1px solid var(--color-rule)',
                fontSize: 'var(--text-body-sm)',
              }}
            >
              <span style={{ color: 'var(--color-ink)' }}>{s.description}</span>
              <kbd
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  padding: '2px 8px',
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  color: 'var(--color-ink)',
                }}
              >
                {s.key}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

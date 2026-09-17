import React, { useEffect } from 'react';

interface Shortcut {
  key: string;
  description: string;
  category: string;
}

const SHORTCUTS: Shortcut[] = [
  { key: '1', description: 'Overview', category: 'Navigation' },
  { key: '2', description: 'Position Ledger', category: 'Navigation' },
  { key: '3', description: 'Market Analysis & Signals', category: 'Navigation' },
  { key: '4', description: 'Chat', category: 'Navigation' },
  { key: 'T', description: 'Toggle Day / Night Mode', category: 'Display' },
  { key: '?', description: 'Toggle Shortcuts Reference', category: 'System' },
  { key: 'ESC', description: 'Dismiss Modal / Dialog', category: 'System' },
];

interface KeyboardShortcutsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KeyboardShortcutsPanel: React.FC<KeyboardShortcutsPanelProps> = ({ isOpen, onClose }) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault();
        if (isOpen) onClose();
      }
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(28, 25, 23, 0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <div
        className="win-window"
        style={{
          width: '100%',
          maxWidth: '520px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          boxShadow: '4px 4px 0 var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          overflow: 'hidden',
        }}
      >
        {/* Retro Window Title Bar */}
        <div
          className="win-titlebar"
          style={{
            padding: '6px 10px',
            borderBottom: '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-win-blue)',
            color: 'var(--color-titlebar-text)',
            fontWeight: 'bold',
          }}
        >
          <span>KEYBOARD SHORTCUTS REFERENCE // SYSTEM</span>
          <div className="win-controls">
            <button
              type="button"
              className="win-control-btn"
              onClick={onClose}
              title="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {SHORTCUTS.map((s, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 'var(--text-body-sm)',
              }}
            >
              <span style={{ color: 'var(--color-ink)', fontWeight: 500 }}>{s.description}</span>
              <kbd
                style={{
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 'var(--weight-bold)',
                  padding: '2px 8px',
                  background: 'var(--color-paper-raised)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: '3px',
                  boxShadow: '1px 1px 0 var(--color-rule)',
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

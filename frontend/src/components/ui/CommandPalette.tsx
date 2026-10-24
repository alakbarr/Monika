import React, { useEffect, useState, useMemo, useRef } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { NAV_ITEMS } from '../layout/navigation';
import { sounds } from '../../lib/soundEffects';
import { api } from '../../lib/api';
import { ConfirmModal } from './ConfirmModal';

interface CommandItem {
  id: string;
  title: string;
  category: 'Navigation' | 'Action';
  shortcut?: string;
  run: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showKillConfirm, setShowKillConfirm] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { setActiveTab, theme, setTheme } = useDashboardStore();

  const handleExecuteKill = async () => {
    setShowKillConfirm(false);
    try {
      await api.emergencyKill();
      sounds.playAlert();
    } catch {}
    onClose();
  };

  const commands: CommandItem[] = useMemo(() => {
    const navCommands: CommandItem[] = NAV_ITEMS.map((item) => ({
      id: `nav-${item.id}`,
      title: `Go to ${item.label}`,
      category: 'Navigation',
      run: () => {
        setActiveTab(item.id);
        onClose();
      },
    }));

    navCommands.push({
      id: 'nav-terminal',
      title: 'Go to System Terminal (PTY)',
      category: 'Navigation',
      run: () => {
        setActiveTab('terminal');
        onClose();
      },
    });

    const actionCommands: CommandItem[] = [
      {
        id: 'act-theme',
        title: `Switch Theme (Current: ${theme})`,
        category: 'Action',
        shortcut: 'T',
        run: () => {
          const next = theme === 'dark' ? 'light' : 'dark';
          setTheme(next);
          sounds.playClick('toggle');
          onClose();
        },
      },
      {
        id: 'act-cycle',
        title: 'Trigger Immediate Analysis Cycle',
        category: 'Action',
        run: async () => {
          try {
            await api.triggerCycle(true, 'Command Palette');
            sounds.playClick('typewriter');
          } catch {}
          onClose();
        },
      },
      {
        id: 'act-resume',
        title: 'Resume Trading / Clear Pause Flags',
        category: 'Action',
        run: async () => {
          try {
            await api.resumeTrading();
            sounds.playClick('typewriter');
          } catch {}
          onClose();
        },
      },
      {
        id: 'act-kill',
        title: 'Emergency Kill Switch (Liquidate & Halt)',
        category: 'Action',
        run: () => {
          setShowKillConfirm(true);
        },
      },
    ];

    return [...actionCommands, ...navCommands];
  }, [setActiveTab, theme, setTheme, onClose]);

  const filteredCommands = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(
      (c) => c.title.toLowerCase().includes(q) || c.category.toLowerCase().includes(q)
    );
  }, [commands, query]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (filteredCommands.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filteredCommands.length) % (filteredCommands.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredCommands[selectedIndex]) {
        filteredCommands[selectedIndex].run();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
      className="retro-modal-scrim"
      style={{
        zIndex: 10000,
        alignItems: 'flex-start',
        paddingTop: '10vh',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '90%',
          maxWidth: '580px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-strong)',
          borderRadius: '2px',
          boxShadow: 'var(--shadow-modal)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: '10px 16px',
            borderBottom: '1px solid var(--color-border)',
            background: 'var(--color-surface-well)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--color-ink)',
          }}
        >
          <span>MONIKA COMMAND PALETTE</span>
          <span style={{ color: 'var(--color-ink-soft)' }}>ESC TO CLOSE</span>
        </div>

        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)' }}>
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={filteredCommands.length > 0}
            aria-controls="command-palette-listbox"
            aria-activedescendant={filteredCommands[selectedIndex] ? `cmd-${filteredCommands[selectedIndex].id}` : undefined}
            aria-label="Search commands or navigation views"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or navigate to view…"
            style={{
              width: '100%',
              padding: '10px 12px',
              fontSize: '13px',
              background: 'var(--color-surface-well)',
              color: 'var(--color-ink)',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              outline: 'none',
              fontFamily: 'var(--font-sans)',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div
          role="listbox"
          id="command-palette-listbox"
          aria-label="Available commands"
          style={{
            maxHeight: '360px',
            overflowY: 'auto',
            padding: '6px',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
          }}
        >
          {filteredCommands.length === 0 ? (
            <div
              style={{
                padding: '24px',
                textAlign: 'center',
                color: 'var(--color-ink-soft)',
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
              }}
            >
              No matching commands or navigation targets found.
            </div>
          ) : (
            filteredCommands.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  id={`cmd-${item.id}`}
                  role="option"
                  aria-selected={isSelected}
                  onClick={item.run}
                  style={{
                    padding: '8px 12px',
                    borderRadius: '2px',
                    background: isSelected ? 'var(--color-ink)' : 'transparent',
                    color: isSelected ? 'var(--color-surface)' : 'var(--color-ink)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '13px',
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '11px',
                        padding: '1px 6px',
                        borderRadius: '2px',
                        border: '1px solid currentColor',
                        opacity: 0.75,
                      }}
                    >
                      {item.category.toUpperCase()}
                    </span>
                    <span>{item.title}</span>
                  </div>
                  {item.shortcut && (
                    <kbd
                      style={{
                        padding: '1px 6px',
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        borderRadius: '2px',
                        border: '1px solid currentColor',
                      }}
                    >
                      {item.shortcut}
                    </kbd>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      <ConfirmModal
        isOpen={showKillConfirm}
        title="Emergency Kill Switch"
        actionSummary="Liquidate all open positions and halt autonomous execution daemon immediately."
        confirmLabel="EXECUTE KILL"
        cancelLabel="Cancel"
        danger
        onConfirm={handleExecuteKill}
        onCancel={() => setShowKillConfirm(false)}
      />
    </div>
  );
};

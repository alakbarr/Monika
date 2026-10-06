import React, { useEffect, useState, useMemo, useRef } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { NAV_ITEMS } from '../layout/navigation';
import { sounds } from '../../lib/soundEffects';

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
  const inputRef = useRef<HTMLInputElement>(null);
  const { setActiveTab, theme, setTheme } = useDashboardStore();

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
            await fetch('/api/actions/trigger-cycle', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ force: true, context: 'Command Palette' }),
            });
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
            await fetch('/api/actions/resume', { method: 'POST' });
            sounds.playClick('typewriter');
          } catch {}
          onClose();
        },
      },
      {
        id: 'act-kill',
        title: '🚨 Emergency Kill Switch (Liquidate & Halt)',
        category: 'Action',
        run: async () => {
          if (window.confirm('Are you sure you want to execute emergency liquidation?')) {
            try {
              await fetch('/api/actions/kill', { method: 'POST' });
              sounds.playAlert();
            } catch {}
          }
          onClose();
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
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(3px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '10vh',
      }}
      onClick={onClose}
    >
      <div
        className="win-window ledger-card"
        style={{
          width: '90%',
          maxWidth: '560px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="win-titlebar"
          style={{
            padding: '6px 14px',
            borderBottom: '2px solid var(--color-rule)',
            background: 'var(--color-paper-raised)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-precision)',
            fontSize: 'var(--text-body-sm)',
            fontWeight: 'bold',
          }}
        >
          <span>⚡ Monika Command Palette</span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            ESC to close
          </span>
        </div>

        <div style={{ padding: '12px', borderBottom: '1px solid var(--color-rule)' }}>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or navigate to tab..."
            style={{
              width: '100%',
              padding: '10px 14px',
              fontSize: 'var(--text-body-md)',
              background: 'var(--color-paper)',
              color: 'var(--color-ink)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-control)',
              outline: 'none',
              fontFamily: 'var(--font-precision)',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <div
          style={{
            maxHeight: '360px',
            overflowY: 'auto',
            padding: '6px',
            display: 'flex',
            flexDirection: 'column',
            gap: '3px',
          }}
        >
          {filteredCommands.length === 0 ? (
            <div
              style={{
                padding: '24px',
                textAlign: 'center',
                color: 'var(--color-ink-soft)',
                fontSize: 'var(--text-body-sm)',
                fontFamily: 'var(--font-precision)',
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
                  onClick={item.run}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-control)',
                    background: isSelected ? 'var(--color-primary)' : 'transparent',
                    color: isSelected ? 'var(--color-on-primary)' : 'var(--color-ink)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontFamily: 'var(--font-precision)',
                    fontSize: 'var(--text-body-sm)',
                    transition: 'background 0.1s ease',
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        fontSize: 'var(--text-xs)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: isSelected ? 'rgba(255,255,255,0.2)' : 'var(--color-paper-sunken)',
                        color: isSelected ? 'inherit' : 'var(--color-ink-soft)',
                      }}
                    >
                      {item.category}
                    </span>
                    <span>{item.title}</span>
                  </div>
                  {item.shortcut && (
                    <kbd
                      style={{
                        padding: '2px 6px',
                        fontSize: '11px',
                        background: isSelected ? 'rgba(255,255,255,0.25)' : 'var(--color-paper-sunken)',
                        borderRadius: '3px',
                        border: '1px solid var(--color-rule)',
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
    </div>
  );
};

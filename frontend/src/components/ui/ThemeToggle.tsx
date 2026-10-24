import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';

interface ThemeToggleProps {
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = '' }) => {
  const theme = useDashboardStore((s) => s.theme);
  const setTheme = useDashboardStore((s) => s.setTheme);

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  const isLight = theme === 'light';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`editorial-btn ${className}`}
      title={isLight ? 'Switch to Graphite Dark Mode (T)' : 'Switch to Alabaster Light Mode (T)'}
      aria-label={isLight ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: '28px',
        boxSizing: 'border-box',
        gap: '7px',
        background: 'transparent',
        border: '1px solid var(--color-rule)',
        borderRadius: 'var(--radius-xs)',
        padding: '0 10px',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-xs)',
        color: 'var(--color-ink-secondary)',
        userSelect: 'none',
      }}
    >
      <span
        style={{
          width: '7px',
          height: '7px',
          background: 'var(--color-ink)',
          display: 'inline-block',
        }}
      />
      <span style={{ fontWeight: 600, letterSpacing: '0.06em' }}>
        {isLight ? 'ALABASTER' : 'GRAPHITE'}
      </span>
    </button>
  );
};

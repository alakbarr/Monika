import React, { useEffect, useState } from 'react';

interface ThemeToggleProps {
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = '' }) => {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const current = document.documentElement.getAttribute('data-theme');
    if (current === 'light' || current === 'dark') return current;
    const saved = typeof window !== 'undefined' ? localStorage.getItem('monika_theme') : null;
    if (saved === 'light' || saved === 'dark') return saved;
    return 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('monika_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  const isLight = theme === 'light';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`win-btn ${className}`}
      title={isLight ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: '30px',
        boxSizing: 'border-box',
        gap: '8px',
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-md)',
        padding: '0 10px',
        cursor: 'pointer',
        fontFamily: 'var(--font-precision)',
        fontSize: 'var(--text-xs)',
        color: 'var(--color-ink)',
        boxShadow: '2px 2px 0 var(--color-rule)',
        userSelect: 'none',
      }}
    >
      {/* Retro slider track */}
      <span
        style={{
          width: '28px',
          height: '14px',
          background: 'var(--color-paper)',
          border: '1.5px solid var(--color-rule)',
          borderRadius: '3px',
          position: 'relative',
          display: 'inline-block',
        }}
      >
        {/* Retro knob */}
        <span
          style={{
            position: 'absolute',
            top: '0px',
            left: isLight ? '0px' : '13px',
            width: '11px',
            height: '11px',
            background: 'var(--color-win-yellow)',
            border: '1.5px solid var(--color-rule)',
            borderRadius: '2px',
            transition: 'left 120ms ease-out',
          }}
        />
      </span>
      <span style={{ fontWeight: 'var(--weight-bold)', letterSpacing: '0.04em' }}>
        {isLight ? 'LIGHT' : 'DARK'}
      </span>
    </button>
  );
};

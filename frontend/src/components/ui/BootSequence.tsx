import React, { useEffect, useState } from 'react';
import { MonikaInfiniteIcon } from './MonikaInfiniteIcon';

interface BootSequenceProps {
  onComplete?: () => void;
}

export const BootSequence: React.FC<BootSequenceProps> = ({ onComplete }) => {
  const [booting, setBooting] = useState<boolean>(() => {
    if (
      typeof window !== 'undefined' &&
      (window.location.search.includes('tab=') || window.location.search.includes('noboot=1'))
    ) {
      return false;
    }
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return false;
    }
    const booted = sessionStorage.getItem('monika_retro_booted');
    return !booted;
  });

  useEffect(() => {
    if (!booting) {
      onComplete?.();
      return;
    }
    const timer = setTimeout(() => {
      sessionStorage.setItem('monika_retro_booted', 'true');
      setBooting(false);
      onComplete?.();
    }, 450);

    return () => clearTimeout(timer);
  }, [booting, onComplete]);

  if (!booting) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        background: 'var(--color-canvas)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-mono)',
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '14px',
          padding: '32px',
        }}
      >
        <MonikaInfiniteIcon size={32} />
        <div
          style={{
            fontFamily: 'var(--font-editorial)',
            fontSize: 'var(--text-display-sm)',
            color: 'var(--color-ink)',
            letterSpacing: '-0.02em',
          }}
        >
          Monika Autonomous Desk
        </div>
        <div
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
          }}
        >
          Synchronizing Quantitative Telemetry…
        </div>
      </div>
    </div>
  );
};

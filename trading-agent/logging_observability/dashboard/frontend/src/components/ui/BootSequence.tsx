import React, { useEffect, useState } from 'react';

interface BootSequenceProps {
  onComplete?: () => void;
}

export const BootSequence: React.FC<BootSequenceProps> = ({ onComplete }) => {
  const [booting, setBooting] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && (window.location.search.includes('tab=') || window.location.search.includes('noboot=1'))) {
      return false;
    }
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return false;
    }
    const booted = sessionStorage.getItem('monika_retro_booted');
    return !booted;
  });

  const [progress, setProgress] = useState(1);

  const BOOT_LOGS = [
    'BIOS DATE 04/18/95 14:22:01 VER 2.5',
    'RAM CHECK 640KB BASE + 15360KB EXT .. OK',
    'MT5 IPC CONNECTOR AT 127.0.0.1 ...... OK',
    'LANGGRAPH MULTI-AGENT PIPELINE ..... OK',
    'AUTONOMOUS RISK GATE INITIALIZED ... OK',
    'READY FOR QUANTITATIVE DISPATCH .... OK',
  ];

  useEffect(() => {
    if (!booting) {
      onComplete?.();
      return;
    }

    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 8) {
          clearInterval(interval);
          return 8;
        }
        return p + 1;
      });
    }, 90);

    const timer = setTimeout(() => {
      sessionStorage.setItem('monika_retro_booted', 'true');
      setBooting(false);
      onComplete?.();
    }, 1100);

    return () => {
      clearInterval(interval);
      clearTimeout(timer);
    };
  }, [booting, onComplete]);

  if (!booting) return null;

  const currentLog = BOOT_LOGS[Math.min(progress - 1, BOOT_LOGS.length - 1)];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        background: 'rgba(28, 25, 23, 0.92)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-precision)',
        pointerEvents: 'none',
      }}
    >
      <div
        className="win-window console-scanline"
        style={{
          width: '440px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: '4px 4px 0 var(--color-rule)',
          overflow: 'hidden',
        }}
      >
        {/* Title bar */}
        <div
          className="win-titlebar"
          style={{
            background: 'var(--color-win-blue)',
            color: 'var(--color-titlebar-text)',
            padding: '6px 10px',
            borderBottom: '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 'var(--text-body-sm)',
            fontWeight: 'bold',
          }}
        >
          <span>Monika OS / BIOS POST Bootloader</span>
          <div className="win-controls">
            <span className="win-control-btn">_</span>
            <span className="win-control-btn">□</span>
            <span className="win-control-btn">×</span>
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                background: 'var(--color-win-yellow)',
                border: '2px solid var(--color-rule)',
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 900,
                fontSize: '20px',
                color: 'var(--color-ink)',
                boxShadow: '2px 2px 0 var(--color-rule)',
              }}
            >
              M
            </div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 'var(--text-body-md)', color: 'var(--color-ink)', letterSpacing: '0.04em' }}>
                MONIKA QUANT STATION v2.5
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                Energy & Capital Management Architecture
              </div>
            </div>
          </div>

          {/* BIOS POST log stream */}
          <div
            style={{
              padding: '8px 10px',
              background: 'var(--color-console-bg)',
              color: 'var(--color-console-phosphor)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              lineHeight: 1.4,
              minHeight: '34px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <span>&gt; {currentLog}</span>
          </div>

          {/* Chunky Segmented Progress Bar (from vintage-ui.jpg) */}
          <div
            style={{
              height: '24px',
              background: 'var(--color-paper)',
              border: '2px solid var(--color-rule)',
              borderRadius: '4px',
              padding: '2px',
              display: 'flex',
              gap: '3px',
            }}
          >
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  background: i < progress ? 'var(--color-win-salmon)' : 'transparent',
                  border: i < progress ? '1px solid var(--color-rule)' : 'none',
                  borderRadius: '2px',
                  transition: 'background-color 60ms',
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

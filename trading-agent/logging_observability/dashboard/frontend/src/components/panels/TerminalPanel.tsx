import React, { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

interface TerminalPanelProps {
  className?: string;
  style?: React.CSSProperties;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ className, style }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'Consolas, "Fira Code", Monaco, monospace',
      fontSize: 13,
      lineHeight: 1.2,
      theme: {
        background: '#131722',
        foreground: '#d1d4dc',
        cursor: '#ffb300',
        cursorAccent: '#131722',
        selectionBackground: 'rgba(255, 179, 0, 0.3)',
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    try {
      fitAddon.fit();
    } catch {
      // Container might not be visible immediately
    }

    termRef.current = term;
    fitAddonRef.current = fitAddon;

    term.writeln('\x1b[1;33mMonika Institutional PTY Terminal Bridge\x1b[0m');
    term.writeln('Connecting to gateway terminal socket...\r\n');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8000';
    const wsUrl = `${protocol}//${host}/ws/terminal`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      term.writeln('\x1b[1;32m[CONNECTED] OS Terminal Subprocess Ready.\x1b[0m\r\n');
      try {
        fitAddon.fit();
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      } catch {}
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onerror = () => {
      term.writeln('\r\n\x1b[1;31m[ERROR] Terminal connection interrupted.\x1b[0m');
    };

    ws.onclose = () => {
      term.writeln('\r\n\x1b[1;33m[DISCONNECTED] Terminal session closed.\x1b[0m');
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    const handleResize = () => {
      try {
        fitAddon.fit();
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
        }
      } catch {}
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      term.dispose();
    };
  }, []);

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '520px',
        background: '#131722',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        overflow: 'hidden',
        boxShadow: 'var(--shadow-card)',
        ...style,
      }}
    >
      <div
        className="win-titlebar"
        style={{
          padding: '6px 12px',
          background: 'var(--color-paper-raised)',
          borderBottom: '2px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontFamily: 'var(--font-precision)',
          fontSize: 'var(--text-body-sm)',
          fontWeight: 'bold',
        }}
      >
        <span>🖥️ System Terminal PTY</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
          Direct OS Shell Subprocess
        </span>
      </div>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          padding: '8px',
          overflow: 'hidden',
        }}
      />
    </div>
  );
};

import React, { useEffect, useRef } from 'react';
import { Terminal, type ITheme } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api, getStoredToken } from '../../lib/api';
import { useDashboardStore } from '../../store/dashboardStore';

const DARK_TERMINAL_THEME: ITheme = {
  background: '#0B0906',
  foreground: '#E8B94A',
  cursor: '#F5BD38',
  cursorAccent: '#0B0906',
  selectionBackground: 'rgba(232, 185, 74, 0.3)',
  selectionForeground: '#FAF7F2',
  black: '#0B0906',
  red: '#E25B45',
  green: '#4CAF50',
  yellow: '#F5BD38',
  blue: '#3BA4C4',
  magenta: '#D3869B',
  cyan: '#48A9A6',
  white: '#FAF7F2',
  brightBlack: '#5C544C',
  brightRed: '#F46A6A',
  brightGreen: '#66BB6A',
  brightYellow: '#F5BD38',
  brightBlue: '#5BC3E0',
  brightMagenta: '#E5A4B8',
  brightCyan: '#64C5B1',
  brightWhite: '#FFFFFF',
};

const LIGHT_TERMINAL_THEME: ITheme = {
  background: '#FAF7F2',
  foreground: '#1C1917',
  cursor: '#1C1917',
  cursorAccent: '#FAF7F2',
  selectionBackground: 'rgba(59, 164, 196, 0.3)',
  selectionForeground: '#1C1917',
  black: '#1C1917',
  red: '#B71C1C',
  green: '#1B5E20',
  yellow: '#92400E',
  blue: '#1B365D',
  magenta: '#7B1FA2',
  cyan: '#0F5E77',
  white: '#EFE9DF',
  brightBlack: '#5C544C',
  brightRed: '#D32F2F',
  brightGreen: '#2E7D32',
  brightYellow: '#A16207',
  brightBlue: '#2A7991',
  brightMagenta: '#8E24AA',
  brightCyan: '#00897B',
  brightWhite: '#FFFFFF',
};

interface TerminalPanelProps {
  className?: string;
  style?: React.CSSProperties;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ className, style }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const { theme } = useDashboardStore();
  const isLight = theme === 'light';

  useEffect(() => {
    if (!containerRef.current) return;
    let isCancelled = false;

    const initialIsLight = useDashboardStore.getState().theme === 'light';
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'var(--font-precision), Consolas, "Fira Code", monospace',
      fontSize: 13,
      lineHeight: 1.2,
      theme: initialIsLight ? LIGHT_TERMINAL_THEME : DARK_TERMINAL_THEME,
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
    term.writeln('Authenticating and connecting to terminal socket...\r\n');

    const initWs = async () => {
      let authParam = '';
      try {
        const ticketRes = await api.createWsTicket();
        if (ticketRes?.role && ticketRes.role.toLowerCase() !== 'admin') {
          term.writeln('\x1b[33m[RBAC] Terminal shell requires ADMIN role (configure DASHBOARD_API_KEY).\x1b[0m\r\n');
          return;
        }
        if (ticketRes?.ticket) {
          authParam = `?ticket=${encodeURIComponent(ticketRes.ticket)}`;
        }
      } catch {
        const token = getStoredToken();
        if (token) authParam = `?token=${encodeURIComponent(token)}`;
      }

      if (isCancelled) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host || '127.0.0.1:8000';
      const wsUrl = `${protocol}//${host}/ws/terminal${authParam}`;

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

      ws.onclose = (event) => {
        if (event.code === 1008) {
          term.writeln('\r\n\x1b[1;31m[ACCESS DENIED] Admin role required to access terminal shell.\x1b[0m');
        } else {
          term.writeln('\r\n\x1b[1;33m[DISCONNECTED] Terminal session closed.\x1b[0m');
        }
      };

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });
    };

    initWs();

    const handleResize = () => {
      try {
        fitAddon.fit();
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
        }
      } catch {}
    };

    window.addEventListener('resize', handleResize);

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      isCancelled = true;
      resizeObserver.disconnect();
      window.removeEventListener('resize', handleResize);
      if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
        wsRef.current.close();
      }
      term.dispose();
    };
  }, []);

  useEffect(() => {
    if (termRef.current) {
      termRef.current.options.theme = isLight ? LIGHT_TERMINAL_THEME : DARK_TERMINAL_THEME;
      try {
        termRef.current.refresh(0, termRef.current.rows - 1);
      } catch {}
    }
  }, [isLight]);

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '520px',
        background: isLight ? 'var(--color-paper-raised)' : 'var(--color-console-bg)',
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
          background: isLight ? 'var(--color-paper)' : 'var(--color-paper-raised)',
          borderBottom: '2px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontFamily: 'var(--font-precision)',
          fontSize: 'var(--text-body-sm)',
          fontWeight: 'bold',
          color: 'var(--color-ink)',
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
          background: isLight ? 'var(--color-paper-raised)' : 'var(--color-console-bg)',
        }}
      />
    </div>
  );
};

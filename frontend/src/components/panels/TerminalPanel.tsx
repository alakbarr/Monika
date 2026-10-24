import React, { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api, getStoredToken } from '../../lib/api';
import { useDashboardStore } from '../../store/dashboardStore';
import { DARK_TERMINAL_THEME, LIGHT_TERMINAL_THEME } from '../../theme/tokens';

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
    <section
      className={`editorial-section ${className ?? ''}`.trim()}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '520px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: '2px',
        overflow: 'hidden',
        ...style,
      }}
    >
      <div
        style={{
          padding: '8px 14px',
          background: 'var(--color-surface-well)',
          borderBottom: '1px solid var(--color-border)',
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
        <span>SYSTEM TERMINAL PTY</span>
        <span style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
          DIRECT OS SHELL SUBPROCESS
        </span>
      </div>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          padding: '10px',
          overflow: 'hidden',
          background: isLight ? 'var(--color-surface-well)' : 'var(--color-console-bg)',
        }}
      />
    </section>
  );
};

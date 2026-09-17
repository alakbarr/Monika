import { useEffect, useRef, useCallback } from 'react';
import { useDashboardStore } from '../store/dashboardStore';
import { getStoredToken } from '../lib/api';

interface LiveEvent {
  type:
    | 'tick'
    | 'cycle_triggered'
    | 'position_closed'
    | 'trade_approved'
    | 'risk_override_updated'
    | 'order_state_change'
    | 'connection_established'
    | string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

export const useWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pingTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return;

    // Clean up any existing connection
    if (ws.current) {
      try {
        ws.current.close();
      } catch {
        // ignore
      }
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/live-feed`;

    try {
      const socket = new WebSocket(url);

      socket.onopen = () => {
        useDashboardStore.getState().setWsConnected(true);

        // Authenticate via initial handshake message (H-13)
        const apiKey = getStoredToken();
        if (apiKey) {
          socket.send(JSON.stringify({ type: 'authenticate', token: apiKey }));
        }

        // Keep-alive heartbeat ping every 25 seconds
        if (pingTimer.current) clearInterval(pingTimer.current);
        pingTimer.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send('ping');
          }
        }, 25_000);
      };

      socket.onmessage = (e) => {
        try {
          if (e.data === 'pong') return;

          const event: LiveEvent = JSON.parse(e.data);
          const state = useDashboardStore.getState();

          switch (event.type) {
            case 'tick':
              if (event.payload) {
                state.updateTickPrice(event.payload);
              }
              break;
            case 'cycle_triggered':
            case 'position_closed':
            case 'order_state_change':
              state.fetchQuick();
              break;
            case 'risk_override_updated':
              state.fetchAll();
              break;
            case 'trade_approved':
              if (event.payload) {
                state.addActivity(event.payload);
              }
              state.fetchQuick();
              break;
            default:
              break;
          }
        } catch {
          // ignore non-JSON or malformed messages
        }
      };

      socket.onclose = (ev) => {
        useDashboardStore.getState().setWsConnected(false);
        if (pingTimer.current) clearInterval(pingTimer.current);

        // If unauthorized / policy violation (1008), back off reconnect to 15s
        const delay = ev.code === 1008 ? 15000 : 3000;
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        useDashboardStore.getState().setWsConnected(false);
        try {
          socket.close();
        } catch {
          // ignore
        }
      };

      ws.current = socket;
    } catch {
      useDashboardStore.getState().setWsConnected(false);
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(connect, 5000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (ws.current) {
        ws.current.onclose = null; // Prevent reconnect trigger on deliberate unmount
        ws.current.close();
      }
      useDashboardStore.getState().setWsConnected(false);
    };
  }, [connect]);

  return ws;
};

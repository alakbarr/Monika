import { useEffect, useRef, useCallback } from 'react';
import { useDashboardStore } from '../store/dashboardStore';
import { api, getStoredToken } from '../lib/api';

interface LiveEvent {
  type:
    | 'tick'
    | 'cycle_triggered'
    | 'position_closed'
    | 'trade_approved'
    | 'risk_override_updated'
    | 'order_state_change'
    | 'connection_established'
    | 'open_approvals'
    | string;
  payload?: Record<string, unknown>;
  timestamp?: string;
  seq?: number;
  as_of_seq?: number;
  requests?: any[];
}

export const useWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectAttempts = useRef<number>(0);
  const pingTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const lastSeq = useRef<number>(0);

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
    const seqQuery = lastSeq.current > 0 ? `?since_seq=${lastSeq.current}` : '';
    const url = `${protocol}//${host}/ws/live-feed${seqQuery}`;

    try {
      const socket = new WebSocket(url);

      socket.onopen = () => {
        reconnectAttempts.current = 0;
        useDashboardStore.getState().setWsConnected(true);

        // Authenticate via ephemeral ticket with API key fallback (H-13)
        api.createWsTicket()
          .then((res) => {
            if (res?.ticket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'authenticate', ticket: res.ticket }));
            } else {
              const apiKey = getStoredToken();
              if (apiKey && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: 'authenticate', token: apiKey }));
              }
            }
          })
          .catch(() => {
            const apiKey = getStoredToken();
            if (apiKey && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'authenticate', token: apiKey }));
            }
          });

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

          if (event.seq != null) {
            lastSeq.current = Math.max(lastSeq.current, event.seq);
          } else if (event.as_of_seq != null) {
            lastSeq.current = Math.max(lastSeq.current, event.as_of_seq);
          }

          switch (event.type) {
            case 'open_approvals':
              state.fetchQuick();
              break;
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
            case 'config_updated':
              state.fetchAll();
              break;
            case 'kill_switch_activated':
            case 'circuit_breaker':
            case 'risk_breach':
              if (event.payload) {
                state.addActivity(event.payload);
              }
              state.fetchAll();
              break;
            case 'approval_requested':
            case 'approval_resolved':
            case 'trade_approved':
            case 'steer_injected':
              if (event.payload) {
                state.addActivity(event.payload);
              }
              state.fetchQuick();
              break;
            case 'analysis_cycle_start':
            case 'analysis_step_start':
              if (event.payload) {
                state.addActivity(event.payload);
              }
              state.fetchQuick();
              break;
            case 'analysis_step_complete':
            case 'analysis_cycle_complete':
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

        reconnectAttempts.current += 1;
        const baseDelay =
          ev.code === 1008
            ? 15000
            : Math.min(30000, 1000 * Math.pow(1.5, Math.min(reconnectAttempts.current, 8)));
        const jitter = Math.random() * 800;
        const delay = Math.round(baseDelay + jitter);
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
      reconnectAttempts.current += 1;
      const delay = Math.min(30000, 2000 * Math.pow(1.5, Math.min(reconnectAttempts.current, 6)));
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(connect, Math.round(delay));
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

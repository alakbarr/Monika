// ==============================================================================
// File: src/hooks/useAgentChatWs.ts
// Description: Custom hook encapsulating Agent Chat WebSocket connection & lifecycle
// ==============================================================================

import { useState, useRef, useEffect, useCallback } from 'react';
import { getStoredToken } from '../lib/api';
import type { ChatMessage, ChatToolEvent, ChatProposedAction } from '../types/api';

const DEFAULT_WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: 'Hello! I am Monika, your autonomous MT5 Trading Agent. You can instruct me to analyze instruments (e.g., "analyze EURUSD"), review open positions, inspect active trade triggers, or audit risk exposure.',
  timestamp: new Date().toISOString(),
};

export function useAgentChatWs() {
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_WELCOME]);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [activeToolEvents, setActiveToolEvents] = useState<ChatToolEvent[]>([]);

  const socketRef = useRef<WebSocket | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const connect = useCallback(() => {
    if (!isMountedRef.current) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.host;
    const apiKey = getStoredToken();
    const url = `${protocol}//${host}/ws/agent-chat`;

    if (socketRef.current) {
      try {
        socketRef.current.onclose = null;
        socketRef.current.close();
      } catch {
        // ignore
      }
    }

    const ws = new WebSocket(url);

    ws.onopen = () => {
      if (!isMountedRef.current) {
        ws.close();
        return;
      }
      setWsConnected(true);

      if (apiKey) {
        ws.send(JSON.stringify({ type: 'authenticate', token: apiKey }));
      }

      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 25_000);
    };

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return;
      try {
        if (event.data === 'pong') return;
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'connection_established':
            break;

          case 'history':
            if (Array.isArray(data.messages) && data.messages.length > 0) {
              setMessages(data.messages);
            }
            break;

          case 'tool_start':
            setActiveToolEvents((prev) => [
              ...prev,
              { type: 'tool_start', tool: data.tool, input: data.input, timestamp: data.timestamp },
            ]);
            break;

          case 'tool_result':
            setActiveToolEvents((prev) => [
              ...prev.filter((t) => t.tool !== data.tool || t.type !== 'tool_start'),
              { type: 'tool_result', tool: data.tool, summary: data.summary, timestamp: data.timestamp },
            ]);
            break;

          case 'delta':
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === 'assistant' && last.isStreaming) {
                return [
                  ...prev.slice(0, -1),
                  { ...last, text: last.text + data.text },
                ];
              } else {
                return [
                  ...prev,
                  {
                    id: String(Date.now()),
                    role: 'assistant',
                    text: data.text,
                    timestamp: new Date().toISOString(),
                    isStreaming: true,
                  },
                ];
              }
            });
            break;

          case 'complete':
            setIsProcessing(false);
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === 'assistant' && last.isStreaming) {
                return [
                  ...prev.slice(0, -1),
                  {
                    ...last,
                    text: data.text || last.text,
                    isStreaming: false,
                    toolsUsed: data.tools_used,
                  },
                ];
              } else {
                return [
                  ...prev,
                  {
                    id: String(Date.now()),
                    role: 'assistant',
                    text: data.text,
                    timestamp: new Date().toISOString(),
                    isStreaming: false,
                    toolsUsed: data.tools_used,
                  },
                ];
              }
            });
            break;

          case 'approval_request':
            setMessages((prev) => [
              ...prev,
              {
                id: String(Date.now()),
                role: 'assistant',
                text: `📋 Proposed Trade Action: ${data.action.description || 'Order approval required'}`,
                timestamp: new Date().toISOString(),
                pendingAction: data.action as ChatProposedAction,
              },
            ]);
            break;

          case 'interrupted':
            setIsProcessing(false);
            setMessages((prev) => [
              ...prev,
              {
                id: String(Date.now()),
                role: 'system',
                text: '⚠️ Turn was interrupted by user.',
                timestamp: new Date().toISOString(),
              },
            ]);
            break;

          case 'error':
            setIsProcessing(false);
            setMessages((prev) => [
              ...prev,
              {
                id: String(Date.now()),
                role: 'system',
                text: `❌ ${data.message || 'An error occurred during chat turn.'}`,
                timestamp: new Date().toISOString(),
              },
            ]);
            break;
        }
      } catch (err) {
        console.error('Failed processing WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (!isMountedRef.current) return;
      setWsConnected(false);
      setIsProcessing(false);
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          connect();
        }
      }, 3000);
    };

    socketRef.current = ws;
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    connect();
    return () => {
      isMountedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
      setWsConnected(false);
      setIsProcessing(false);
    };
  }, [connect]);

  const sendMessage = useCallback((text: string, model: string = 'auto') => {
    if (!text.trim() || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      text: text.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);
    setActiveToolEvents([]);

    socketRef.current.send(
      JSON.stringify({
        type: 'message',
        text: text.trim(),
        model,
      })
    );
  }, []);

  const interrupt = useCallback(() => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'interrupt' }));
    }
  }, []);

  const respondApproval = useCallback(
    (actionId: string, decision: 'allow_once' | 'allow_session' | 'deny') => {
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

      socketRef.current.send(
        JSON.stringify({
          type: 'approval_response',
          action_id: actionId,
          decision,
        })
      );

      setMessages((prev) =>
        prev.map((m) =>
          m.pendingAction?.action_id === actionId
            ? { ...m, pendingAction: undefined, text: `${m.text} [Decision: ${decision.toUpperCase()}]` }
            : m
        )
      );
    },
    []
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    wsConnected,
    isProcessing,
    activeToolEvents,
    sendMessage,
    interrupt,
    respondApproval,
    clearMessages,
  };
}

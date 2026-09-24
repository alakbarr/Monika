import React, { useEffect, useState, useRef } from 'react';
import { Badge } from '../ui/Badge';
import { TypewriterButton } from '../ui/TypewriterButton';
import { ApprovalModal, type TradeApprovalRequest } from '../ui/ApprovalModal';
import { useDashboardStore } from '../../store/dashboardStore';
import { useAgentChatWs } from '../../hooks/useAgentChatWs';
import {
  Bot,
  User,
  Send,
  Square,
  Wrench,
  Check,
  X,
  ShieldCheck,
  Maximize2,
} from 'lucide-react';

export const AgentChatPanel: React.FC = () => {
  const { userRole, fetchUserRole } = useDashboardStore();
  const {
    messages,
    wsConnected,
    isProcessing,
    activeToolEvents,
    sendMessage,
    interrupt,
    respondApproval,
    clearMessages,
  } = useAgentChatWs();

  const [inputText, setInputText] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [modalRequest, setModalRequest] = useState<TradeApprovalRequest | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const isOperatorOrAdmin = userRole === 'operator' || userRole === 'admin';

  const createApprovalRequest = (action: { action_id: string; action_type: string; params?: Record<string, any> }): TradeApprovalRequest => {
    const p = action.params || {};
    return {
      id: action.action_id,
      symbol: (p.symbol || 'XAUUSD').toUpperCase(),
      direction: (p.direction?.toLowerCase() === 'sell' ? 'sell' : 'buy') as 'buy' | 'sell',
      volume: Number(p.volume || p.lot_size || 0.01),
      entry_price: p.entry_price || p.price,
      sl: p.sl || p.stop_loss,
      tp: p.tp || p.take_profit,
      risk_usd: p.risk_usd,
      risk_pct: p.risk_pct,
      confluence_score: p.confluence_score,
      debate_verdict: p.debate_verdict,
      reason: p.reason || `Execute ${action.action_type}`,
      ttl_seconds: 90,
    };
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeToolEvents]);

  useEffect(() => {
    fetchUserRole();
  }, [fetchUserRole]);

  const handleSendMessage = () => {
    if (!inputText.trim() || !wsConnected || isProcessing) return;
    sendMessage(inputText.trim(), selectedModel);
    setInputText('');
  };

  const handleInterrupt = () => {
    interrupt();
  };

  const handleApproval = (actionId: string, decision: 'allow_once' | 'allow_session' | 'deny') => {
    if (!isOperatorOrAdmin) return;
    respondApproval(actionId, decision);
  };

  return (
    <div
      className="win-window"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 145px)',
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        overflow: 'hidden',
      }}
    >
      {/* 1. Categorical Titlebar — Institutional Telegraph Desk & Dispatch Terminal */}
      <div
        className="win-titlebar win-titlebar--salmon"
        style={{
          padding: '6px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '2px solid var(--color-rule)',
          userSelect: 'none',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: 22,
              height: 22,
              borderRadius: '3px',
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--color-ink)',
            }}
          >
            <Bot size={14} />
          </div>
          <span
            style={{
              fontWeight: 800,
              letterSpacing: '0.04em',
              fontSize: 'var(--text-title-xs)',
              textTransform: 'uppercase',
              color: 'var(--color-titlebar-text)',
              fontFamily: 'var(--font-precision)',
            }}
          >
            INSTITUTIONAL TELEGRAPH DESK // AI DISPATCH CONSOLE
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '10px',
              fontWeight: 800,
              padding: '2px 7px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              color: wsConnected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '1px',
                background: wsConnected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
              }}
            />
            {wsConnected ? '[ ONLINE ]' : '[ DISCONNECTED ]'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                fontSize: '10px',
                fontWeight: 800,
                color: 'var(--color-titlebar-text)',
                textTransform: 'uppercase',
                fontFamily: 'var(--font-precision)',
              }}
            >
              ROUTER:
            </span>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                height: '24px',
                background: 'var(--color-paper)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-ink)',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                padding: '0 6px',
                outline: 'none',
                cursor: 'pointer',
                fontWeight: 700,
              }}
            >
              <option value="auto">Auto (Smart Routing)</option>
              <option value="fast">Gemini Flash (Low Latency)</option>
              <option value="medium">Groq / Medium</option>
              <option value="complex">Claude 3.5 Sonnet (In-Depth)</option>
              <option value="deep_research">Deep Quantitative Research</option>
            </select>
          </div>

          <Badge variant={isOperatorOrAdmin ? 'active' : 'neutral'}>
            {(userRole || 'VIEWER').toUpperCase()}
          </Badge>

          <button
            type="button"
            onClick={clearMessages}
            title="Clear console transcript"
            style={{
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 8px',
              fontSize: '10.5px',
              fontWeight: 800,
              fontFamily: 'var(--font-precision)',
              color: 'var(--color-ink)',
              cursor: 'pointer',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
            }}
          >
            [ CLEAR ]
          </button>
        </div>
      </div>

      {/* 2. Teletype Ribbon Status Bar */}
      <div
        style={{
          padding: '4px 14px',
          background: 'var(--color-paper)',
          borderBottom: '2px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '10px',
          fontFamily: 'var(--font-precision)',
          color: 'var(--color-ink-soft)',
          fontWeight: 700,
          letterSpacing: '0.04em',
          userSelect: 'none',
        }}
      >
        <span>TELEGRAPH PROTOCOL: WS/JSON-RPC // BAUD: 9600 · 8-N-1 · FULL DUPLEX</span>
        <span>CHANNEL: AI-DISPATCH-MAIN · OPERATOR SESSION: {(userRole || 'VIEWER').toUpperCase()}</span>
      </div>

      {/* 3. Transcript Viewport (Vintage Teletype Paper Ledger) */}
      <div
        className="telegraph-viewport"
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          padding: '16px',
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              gap: '4px',
            }}
          >
            {/* Sender & Timestamp */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '10.5px',
                fontWeight: 800,
                color: msg.role === 'user' ? 'var(--color-ink-soft)' : 'var(--color-win-blue)',
                fontFamily: 'var(--font-precision)',
                letterSpacing: '0.04em',
              }}
            >
              {msg.role === 'user' ? (
                <>
                  <span>[ OPERATOR DISPATCH ]</span>
                  <User size={12} />
                </>
              ) : (
                <>
                  <Bot size={13} />
                  <span>[ MONIKA AI // TELEGRAPH DISPATCH ]</span>
                </>
              )}
            </div>

            {/* Message Bubble Card */}
            <div
              style={{
                maxWidth: msg.role === 'user' ? '82%' : '85%',
                padding: '12px 16px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--color-paper-raised)',
                border: '2px solid var(--color-rule)',
                borderLeft: msg.role !== 'user' && msg.role !== 'system'
                  ? '5px solid var(--color-win-blue)'
                  : undefined,
                boxShadow: '2px 2px 0 var(--color-rule)',
                color: 'var(--color-ink)',
                fontFamily: 'var(--font-precision)',
                fontSize: 'var(--text-body-sm)',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                ...(msg.role === 'system'
                  ? {
                      background: 'var(--color-loss-bg)',
                      border: '2px solid var(--color-ledger-red)',
                      color: 'var(--color-ledger-red)',
                    }
                  : {}),
              }}
            >
              {msg.text}
              {msg.isStreaming && (
                <span className="typewriter-cursor" style={{ marginLeft: '4px' }} />
              )}

              {/* HITL 3-Tier Approval Slip */}
              {msg.pendingAction && (
                <div
                  style={{
                    marginTop: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'var(--color-paper)',
                    border: '2px dashed var(--color-rule)',
                    color: 'var(--color-ink)',
                    fontFamily: 'var(--font-precision)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span
                      className="stamp-badge"
                      style={{
                        color: 'var(--color-brass)',
                        background: 'var(--color-warn-dim)',
                        border: '1.5px solid var(--color-brass)',
                      }}
                    >
                      [ HITL // ORDER AUTHORIZATION SLIP ]
                    </span>
                    <Badge variant="warn">EXPIRES 90S</Badge>
                  </div>

                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink)', fontFamily: 'var(--font-precision)', lineHeight: 1.5 }}>
                    <strong>ACTION:</strong> {msg.pendingAction.action_type.toUpperCase()}
                    <br />
                    <strong>PARAMETERS:</strong> {JSON.stringify(msg.pendingAction.params)}
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginTop: '6px', flexWrap: 'wrap' }}>
                    <TypewriterButton
                      size="sm"
                      variant="primary"
                      onClick={() => handleApproval(msg.pendingAction!.action_id, 'allow_once')}
                      disabled={!isOperatorOrAdmin}
                    >
                      <Check size={12} /> [ AUTHORIZE ONCE ]
                    </TypewriterButton>

                    <TypewriterButton
                      size="sm"
                      onClick={() => handleApproval(msg.pendingAction!.action_id, 'allow_session')}
                      disabled={!isOperatorOrAdmin}
                    >
                      <ShieldCheck size={12} /> [ 4H SESSION PERMIT ]
                    </TypewriterButton>

                    <TypewriterButton
                      size="sm"
                      onClick={() => setModalRequest(createApprovalRequest(msg.pendingAction!))}
                      title="Open interactive R:R ladder and order review modal"
                    >
                      <Maximize2 size={12} /> [ EXPAND ORDER LADDER ]
                    </TypewriterButton>

                    <TypewriterButton
                      size="sm"
                      variant="danger"
                      onClick={() => handleApproval(msg.pendingAction!.action_id, 'deny')}
                      disabled={!isOperatorOrAdmin}
                    >
                      <X size={12} /> [ REJECT PROPOSAL ]
                    </TypewriterButton>
                  </div>

                  {!isOperatorOrAdmin && (
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ledger-red)' }}>
                      * Operator or Admin privileges required to authorize trade execution.
                    </span>
                  )}
                </div>
              )}

              {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {msg.toolsUsed.map((t) => (
                    <span
                      key={t}
                      style={{
                        fontSize: '10px',
                        padding: '2px 8px',
                        background: 'var(--color-paper)',
                        border: '1.5px solid var(--color-rule)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--color-ink-soft)',
                        fontFamily: 'var(--font-precision)',
                        fontWeight: 700,
                      }}
                    >
                      🔧 {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Active Tool Calling Indicators */}
        {activeToolEvents.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '4px 0' }}>
            {activeToolEvents.map((evt, idx) => (
              <div
                key={evt.tool + idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 700,
                  color: evt.type === 'tool_start' ? 'var(--color-win-blue)' : 'var(--color-ledger-green)',
                  background: 'var(--color-paper-raised)',
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1.5px solid var(--color-rule)',
                  boxShadow: '1.5px 1.5px 0 var(--color-rule)',
                  width: 'fit-content',
                }}
              >
                <Wrench size={12} />
                <span>
                  {evt.type === 'tool_start' ? `Executing tool '${evt.tool}'...` : `Tool '${evt.tool}' → ${evt.summary}`}
                </span>
              </div>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 4. Typewriter Ribbon Input Bar */}
      <div
        style={{
          padding: '12px 16px',
          background: 'var(--color-paper-raised)',
          borderTop: '2px solid var(--color-rule)',
          display: 'flex',
          gap: '12px',
          alignItems: 'stretch',
        }}
      >
        <textarea
          value={inputText}
          disabled={!wsConnected}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
          placeholder={
            wsConnected
              ? "Enter trade instruction or analysis query (e.g., 'analyze EURUSD')... [Press Enter to dispatch]"
              : "Connecting to trading desk gateway..."
          }
          rows={2}
          style={{
            flex: 1,
            padding: '10px 14px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--color-paper)',
            border: '2px solid var(--color-rule)',
            color: 'var(--color-ink)',
            fontSize: 'var(--text-body-sm)',
            outline: 'none',
            resize: 'none',
            fontFamily: 'var(--font-precision)',
            boxShadow: 'inset 1.5px 1.5px 0 rgba(0,0,0,0.06)',
          }}
        />

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {isProcessing ? (
            <TypewriterButton
              variant="danger"
              onClick={handleInterrupt}
              title="Interrupt AI Execution"
              style={{ height: '100%' }}
            >
              <Square size={14} /> [ HALT ]
            </TypewriterButton>
          ) : (
            <TypewriterButton
              variant="primary"
              onClick={handleSendMessage}
              disabled={!inputText.trim() || !wsConnected}
              style={{ height: '100%' }}
            >
              <Send size={14} /> [ DISPATCH ]
            </TypewriterButton>
          )}
        </div>
      </div>

      {/* HITL Visual Approval Modal */}
      <ApprovalModal
        isOpen={!!modalRequest}
        request={modalRequest}
        onAllowOnce={(id) => {
          handleApproval(id, 'allow_once');
          setModalRequest(null);
        }}
        onAllowSession={(id) => {
          handleApproval(id, 'allow_session');
          setModalRequest(null);
        }}
        onDeny={(id) => {
          handleApproval(id, 'deny');
          setModalRequest(null);
        }}
        onClose={() => setModalRequest(null)}
      />
    </div>
  );
};

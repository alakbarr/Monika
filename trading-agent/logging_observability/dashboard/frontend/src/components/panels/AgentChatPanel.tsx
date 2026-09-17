import React, { useEffect, useState, useRef } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { TypewriterButton } from '../ui/TypewriterButton';
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
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const isOperatorOrAdmin = userRole === 'operator' || userRole === 'admin';

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
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 150px)', gap: '14px' }}>
      {/* Top Header Card */}
      <Card padding="12px 16px" variant="yellow">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: 34,
              height: 34,
              borderRadius: '4px',
              background: 'var(--color-win-yellow)',
              border: '1.5px solid var(--color-rule)',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#1C1917',
            }}>
              <Bot size={20} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h3 style={{
                  fontSize: 'var(--text-title-sm)',
                  fontWeight: 800,
                  color: 'var(--color-ink)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  margin: 0,
                  fontFamily: 'var(--font-precision)',
                }}>
                  INSTITUTIONAL AI DESK CONSOLE
                </h3>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: 'var(--text-xs)',
                  color: wsConnected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 'bold',
                }}>
                  <span style={{
                    width: 7,
                    height: 7,
                    borderRadius: 2,
                    background: wsConnected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                  }} />
                  {wsConnected ? '[ CONSOLE ONLINE ]' : '[ DISCONNECTED ]'}
                </span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>MODEL:</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={{
                  height: '26px',
                  boxSizing: 'border-box',
                  display: 'inline-flex',
                  alignItems: 'center',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-precision)',
                  padding: '0 8px',
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="auto">Auto (Smart Routing)</option>
                <option value="fast">Gemini Flash (Fast / Low Latency)</option>
                <option value="medium">Groq / Medium</option>
                <option value="complex">Claude 3.5 Sonnet (In-Depth)</option>
                <option value="deep_research">Deep Quantitative Research</option>
              </select>
            </div>

            <Badge variant={isOperatorOrAdmin ? 'active' : 'neutral'}>
              {(userRole || 'VIEWER').toUpperCase()}
            </Badge>

            <TypewriterButton
              size="sm"
              onClick={clearMessages}
              title="Clear console transcript"
            >
              [ CLEAR ]
            </TypewriterButton>
          </div>
        </div>
      </Card>

      {/* Transcript Area — THE MACHINE'S CONSOLE (Vintage CRT Chassis) */}
      <div className="crt-chassis" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-ledger-green)', boxShadow: '0 0 4px var(--color-ledger-green)', display: 'inline-block' }} />
            <span style={{ fontSize: '10px', fontWeight: 800, color: 'var(--color-ink-soft)', letterSpacing: '0.08em' }}>
              PHOSPHOR TERMINAL // MODEL CRT-286
            </span>
          </div>
          <span style={{ fontSize: '9px', color: 'var(--color-ink-soft)', textTransform: 'uppercase' }}>
            BAUD: 9600 · 8-N-1
          </span>
        </div>

        <div
          className="win-window console-panel console-scanline crt-bezel"
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            padding: '16px',
            background: 'var(--color-console-bg)',
            color: 'var(--color-console-phosphor)',
            border: '2px solid var(--color-rule)',
            borderRadius: 'var(--radius-card)',
            boxShadow: 'inset 0 0 10px rgba(0,0,0,0.8)',
          }}
        >
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px', paddingRight: '6px' }}>
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
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: 'var(--text-xs)',
                color: msg.role === 'user' ? 'var(--color-brass)' : 'var(--color-console-dim)',
                fontFamily: 'var(--font-precision)',
              }}>
                {msg.role === 'user' ? (
                  <>
                    <span>OPERATOR</span>
                    <User size={12} />
                  </>
                ) : (
                  <>
                    <Bot size={12} color="var(--color-console-phosphor)" />
                    <span>MONIKA AI // CONSOLE</span>
                  </>
                )}
              </div>

              {/* Message Bubble */}
              <div
                style={{
                  maxWidth: '85%',
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-card)',
                  background: msg.role === 'user'
                    ? 'var(--color-paper-raised)'
                    : msg.role === 'system'
                      ? 'rgba(122, 46, 39, 0.2)'
                      : 'rgba(232, 185, 74, 0.05)',
                  border: `1px solid ${
                    msg.role === 'user'
                      ? 'var(--color-brass)'
                      : msg.role === 'system'
                        ? 'var(--color-ledger-red)'
                        : 'var(--color-console-border)'
                  }`,
                  color: msg.role === 'user' ? 'var(--color-ink)' : 'var(--color-console-phosphor)',
                  fontFamily: 'var(--font-precision)',
                  letterSpacing: '0.01em',
                  fontSize: 'var(--text-body-sm)',
                  lineHeight: '1.6',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  boxShadow: '1px 1px 0 rgba(0,0,0,0.3)',
                }}
              >
                {msg.text}
                {msg.isStreaming && (
                  <span className="typewriter-cursor" style={{ marginLeft: '4px' }} />
                )}

                {/* HITL 3-Tier Approval Card */}
                {msg.pendingAction && (
                  <div style={{
                    marginTop: '12px',
                    padding: '12px',
                    borderRadius: 'var(--radius-card)',
                    background: 'var(--color-paper-raised)',
                    border: '1px solid var(--color-brass)',
                    color: 'var(--color-ink)',
                    fontFamily: 'var(--font-precision)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span className="stamp-badge" style={{ color: 'var(--color-brass)', background: 'var(--color-primary-dim)' }}>
                        [ HITL // ORDER AUTHORIZATION ]
                      </span>
                      <Badge variant="warn">EXPIRES 90S</Badge>
                    </div>

                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink)', fontFamily: 'var(--font-precision)' }}>
                      Action: {msg.pendingAction.action_type}
                      <br />
                      Parameters: {JSON.stringify(msg.pendingAction.params)}
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
                      <span key={t} style={{
                        fontSize: '10px',
                        padding: '2px 8px',
                        background: 'rgba(255,255,255,0.06)',
                        borderRadius: 'var(--radius-pill)',
                        color: 'var(--color-text-muted)',
                        fontFamily: 'var(--font-mono)',
                      }}>
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
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    color: evt.type === 'tool_start' ? 'var(--color-primary)' : 'var(--color-profit)',
                    background: 'rgba(0,0,0,0.3)',
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    width: 'fit-content',
                  }}
                >
                  <Wrench size={12} />
                  <span>
                    {evt.type === 'tool_start' ? `Running tool '${evt.tool}'...` : `Tool '${evt.tool}' → ${evt.summary}`}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div style={{
          marginTop: '16px',
          paddingTop: '12px',
          borderTop: '1px solid var(--color-console-border)',
          display: 'flex',
          gap: '12px',
        }}>
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
            placeholder={wsConnected ? "Enter trade instruction or analysis query (e.g., 'analyze EURUSD')... [Press Enter to submit]" : "Connecting to trading desk gateway..."}
            rows={2}
            style={{
              flex: 1,
              padding: '10px 14px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--color-paper-raised)',
              border: '2px solid var(--color-rule)',
              color: 'var(--color-ink)',
              fontSize: 'var(--text-body-sm)',
              outline: 'none',
              resize: 'none',
              fontFamily: 'var(--font-precision)',
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
                <Send size={14} /> [ SUBMIT ]
              </TypewriterButton>
            )}
          </div>
        </div>
      </div>
    </div>
  </div>
  );
};

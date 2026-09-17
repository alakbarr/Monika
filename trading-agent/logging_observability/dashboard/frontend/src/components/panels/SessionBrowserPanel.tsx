import React, { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { api } from '../../lib/api';
import type { ConversationSession, ConversationMessage } from '../../types/api';
import {
  History,
  MessageSquare,
  Bot,
  User,
  Search,
  RefreshCw,
  Clock,
} from 'lucide-react';

export const SessionBrowserPanel: React.FC = () => {
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loadingSessions, setLoadingSessions] = useState<boolean>(false);
  const [loadingMessages, setLoadingMessages] = useState<boolean>(false);
  const [filterSource, setFilterSource] = useState<'all' | 'dashboard' | 'telegram'>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    setError(null);
    try {
      const data = await api.sessions(filterSource === 'all' ? undefined : filterSource, 100);
      setSessions(data || []);
      if (data && data.length > 0 && !selectedSessionId) {
        setSelectedSessionId(data[0].session_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Failed to load sessions: ${msg}`);
    } finally {
      setLoadingSessions(false);
    }
  }, [filterSource, selectedSessionId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    if (!selectedSessionId) {
      setMessages([]);
      return;
    }

    let isMounted = true;
    const fetchMessages = async () => {
      setLoadingMessages(true);
      try {
        const msgs = await api.sessionMessages(selectedSessionId, 200);
        if (isMounted) {
          setMessages(msgs || []);
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(`Failed to load messages for session ${selectedSessionId}: ${msg}`);
        }
      } finally {
        if (isMounted) setLoadingMessages(false);
      }
    };

    fetchMessages();
    return () => {
      isMounted = false;
    };
  }, [selectedSessionId]);

  const filteredSessions = sessions.filter(s => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.session_id.toLowerCase().includes(q) ||
      (s.last_message && s.last_message.toLowerCase().includes(q))
    );
  });

  const selectedSession = sessions.find(s => s.session_id === selectedSessionId);

  const formatTimestamp = (ts: string | null) => {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleString('en-US', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', height: 'calc(100vh - 120px)' }}>
      {/* Top Header Card */}
      <Card className="ledger-card" padding="14px 20px" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: '2px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-brass)',
          }}>
            <History size={18} />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Session History & Transcript Archive
            </h2>
            <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '2px', fontFamily: 'var(--font-precision)' }}>
              Inspect Telegram dispatch logs, interactive terminal sessions, and executed transcripts.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Filter Source buttons */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: '28px',
            boxSizing: 'border-box',
            background: 'var(--color-surface)',
            borderRadius: 'var(--radius-sm)',
            padding: '2px',
            border: '1px solid var(--color-border)',
            gap: '2px',
          }}>
            {(['all', 'dashboard', 'telegram'] as const).map(src => (
              <button
                key={src}
                onClick={() => setFilterSource(src)}
                style={{
                  height: '100%',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 10px',
                  borderRadius: '1px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  background: filterSource === src ? 'var(--color-brass)' : 'transparent',
                  color: filterSource === src ? 'var(--color-paper-dark)' : 'var(--color-ink-muted)',
                  fontFamily: 'var(--font-precision)',
                }}
              >
                {src}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchSessions()}
            disabled={loadingSessions}
            title="Refresh sessions"
            className="typewriter-btn"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              height: '28px',
              boxSizing: 'border-box',
              padding: '0 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-ink)',
              cursor: loadingSessions ? 'not-allowed' : 'pointer',
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <RefreshCw size={12} className={loadingSessions ? 'spin-anim' : ''} />
            REFRESH
          </button>
        </div>
      </Card>

      {error && (
        <div style={{
          padding: '10px 14px',
          borderRadius: '2px',
          background: 'var(--color-surface-card)',
          border: '1px solid var(--color-loss)',
          borderLeft: '3px solid var(--color-loss)',
          color: 'var(--color-loss)',
          fontSize: '12px',
          fontFamily: 'var(--font-precision)',
        }}>
          {error}
        </div>
      )}

      {/* Main Content: Split Pane */}
      <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: '16px', flex: 1, minHeight: 0 }}>
        {/* Left Pane: Sessions List */}
        <Card className="ledger-card" padding="14px" style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* Search Box */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'var(--color-surface)',
            borderRadius: '2px',
            padding: '6px 10px',
            border: '1px solid var(--color-border)',
            marginBottom: '10px',
          }}>
            <Search size={13} color="var(--color-ink-muted)" />
            <input
              type="text"
              placeholder="Search session or dossier..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--color-ink)',
                fontSize: '11px',
                width: '100%',
                fontFamily: 'var(--font-precision)',
              }}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-ink-muted)',
                  cursor: 'pointer',
                  fontSize: '11px',
                }}
              >
                ✕
              </button>
            )}
          </div>

          <div style={{
            fontSize: '10px',
            fontWeight: 700,
            color: 'var(--color-ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: '8px',
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-precision)',
          }}>
            <span>Sessions ({filteredSessions.length})</span>
            {loadingSessions && <span>Loading...</span>}
          </div>

          {/* Session Cards Scrollable List */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {filteredSessions.length === 0 && !loadingSessions && (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-ink-muted)', fontSize: '12px' }}>
                No sessions recorded matching filter.
              </div>
            )}

            {filteredSessions.map(sess => {
              const isSelected = sess.session_id === selectedSessionId;
              const isDash = sess.source === 'dashboard';

              return (
                <div
                  key={sess.session_id}
                  onClick={() => setSelectedSessionId(sess.session_id)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '2px',
                    border: isSelected ? '1px solid var(--color-brass)' : '1px solid var(--color-border)',
                    borderLeft: isSelected ? '3px solid var(--color-brass)' : '1px solid var(--color-border)',
                    background: isSelected ? 'var(--color-surface-card)' : 'var(--color-surface)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        display: 'inline-block',
                        width: '6px',
                        height: '6px',
                        borderRadius: '1px',
                        background: isDash ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                      }} />
                      <span style={{
                        fontSize: '12px',
                        fontWeight: 700,
                        color: isSelected ? 'var(--color-brass)' : 'var(--color-ink)',
                        fontFamily: 'var(--font-precision)',
                      }}>
                        {sess.session_id}
                      </span>
                    </div>

                    <span style={{
                      fontSize: '9px',
                      padding: '2px 5px',
                      borderRadius: '1px',
                      border: '1px solid var(--color-border)',
                      background: 'var(--color-surface)',
                      color: 'var(--color-ink-muted)',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      fontFamily: 'var(--font-precision)',
                    }}>
                      {sess.source}
                    </span>
                  </div>

                  {sess.last_message && (
                    <div style={{
                      fontSize: '11px',
                      color: 'var(--color-ink-muted)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {sess.last_role === 'user' ? '» ' : '• '}
                      {sess.last_message}
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={10} />
                      <span>{formatTimestamp(sess.last_active || sess.first_active)}</span>
                    </div>
                    <span style={{
                      background: 'var(--color-surface)',
                      padding: '1px 4px',
                      borderRadius: '1px',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-ink-muted)',
                    }}>
                      {sess.message_count} msgs
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Right Pane: Transcript & Message Timeline */}
        <Card className="ledger-card" padding="0" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          {selectedSession ? (
            <>
              {/* Transcript Header */}
              <div style={{
                padding: '12px 16px',
                borderBottom: '1px solid var(--color-border)',
                background: 'var(--color-surface-card)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexShrink: 0,
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Docket: {selectedSession.session_id}
                    </span>
                    <Badge variant={selectedSession.source === 'dashboard' ? 'warn' : 'neutral'} size="sm">
                      {selectedSession.source}
                    </Badge>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-muted)', marginTop: '2px', fontFamily: 'var(--font-precision)' }}>
                    Opened: {formatTimestamp(selectedSession.first_active)} · Last Entry: {formatTimestamp(selectedSession.last_active)} · Recorded Items: {messages.length}
                  </div>
                </div>
              </div>

              {/* Message List */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {loadingMessages && (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)', fontSize: '12px' }}>
                    Loading transcript dossier...
                  </div>
                )}

                {messages.length === 0 && !loadingMessages && (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-ink-muted)', fontSize: '12px' }}>
                    No entries recorded in this session.
                  </div>
                )}

                {messages.map((m) => {
                  const isUser = m.role === 'user';

                  return (
                    <div
                      key={m.id}
                      style={{
                        display: 'flex',
                        gap: '10px',
                        alignSelf: isUser ? 'flex-end' : 'flex-start',
                        maxWidth: isUser ? '85%' : '90%',
                      }}
                    >
                      {!isUser && (
                        <div style={{
                          width: 28,
                          height: 28,
                          borderRadius: '2px',
                          background: 'var(--color-surface-card)',
                          border: '1px solid var(--color-border)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'var(--color-brass)',
                          flexShrink: 0,
                        }}>
                          <Bot size={14} />
                        </div>
                      )}

                      <div style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                        alignItems: isUser ? 'flex-end' : 'flex-start',
                        width: '100%',
                      }}>
                        {/* Slip / Memo Card */}
                        <div style={{
                          padding: '10px 14px',
                          borderRadius: '2px',
                          background: isUser ? 'var(--color-surface-card)' : 'var(--color-surface)',
                          color: 'var(--color-ink)',
                          border: isUser ? '1px solid var(--color-border)' : '1px solid var(--color-border)',
                          borderLeft: isUser ? '3px solid var(--color-brass)' : '3px solid var(--color-ink-muted)',
                          fontSize: '12px',
                          lineHeight: 1.5,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'var(--font-precision)',
                        }}>
                          {m.message}
                        </div>

                        {/* Meta info: Timestamp */}
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          fontSize: '10px',
                          color: 'var(--color-ink-muted)',
                          fontFamily: 'var(--font-precision)',
                        }}>
                          <span>{formatTimestamp(m.timestamp)}</span>
                        </div>
                      </div>

                      {isUser && (
                        <div style={{
                          width: 28,
                          height: 28,
                          borderRadius: '2px',
                          background: 'var(--color-surface-card)',
                          border: '1px solid var(--color-border)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'var(--color-ink)',
                          flexShrink: 0,
                        }}>
                          <User size={14} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: 'var(--color-ink-muted)',
              gap: '10px',
              padding: '32px',
            }}>
              <MessageSquare size={36} strokeWidth={1.5} />
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                No Session Selected
              </div>
              <div style={{ fontSize: '11px', maxWidth: '320px', textAlign: 'center', fontFamily: 'var(--font-precision)' }}>
                Select an entry from the dossier index on the left to review its transcript.
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

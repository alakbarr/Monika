import React, { useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { TelegraphDeskIcon } from '../ui/Icons';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

import { EmptyState } from '../ui/EmptyState';

const FILTER_TABS = ['all', 'trading', 'analysis', 'risk', 'system'];

function parseLogDescription(raw: string) {
  if (!raw) return { text: '', json: null };
  const jsonMatch = raw.match(/(\{[\s\S]*\}|\[[\s\S]*\])/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      const prefix = raw.slice(0, jsonMatch.index).trim();
      return {
        text: prefix || 'Structured system payload',
        json: JSON.stringify(parsed, null, 2),
      };
    } catch {
      // fallback if not valid JSON
    }
  }
  return { text: raw, json: null };
}

export const ActivityFeed: React.FC = () => {
  const { activity, loading } = useDashboardStore();
  const [filter, setFilter] = useState('all');
  const [isPaused, setIsPaused] = useState(false);
  const [frozenActivity, setFrozenActivity] = useState<typeof activity>([]);

  const activeSource = isPaused ? frozenActivity : activity;
  const filtered = filter === 'all' ? activeSource : activeSource.filter((a) => a.category === filter);
  const displayedRecords = filtered.slice(0, 200);
  const pendingCount = isPaused ? Math.max(0, activity.length - frozenActivity.length) : 0;

  const togglePause = () => {
    if (isPaused) {
      setIsPaused(false);
      setFrozenActivity([]);
    } else {
      setFrozenActivity([...activity]);
      setIsPaused(true);
    }
  };

  return (
    <WindowFrame
      title="DISPATCH TELEGRAPH LOG"
      icon={<TelegraphDeskIcon size={18} />}
      variant="yellow"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, padding: 0 }}
      toolbar={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '8px', overflowX: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <div style={{ display: 'flex', gap: '4px' }}>
              {FILTER_TABS.map((tab) => {
                const isActive = filter === tab;
                return (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setFilter(tab)}
                    className="typewriter-btn"
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      fontFamily: 'var(--font-precision)',
                      fontWeight: isActive ? 800 : 600,
                      background: isActive ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                      color: isActive ? 'var(--color-on-win-yellow)' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: 'var(--radius-sm)',
                      boxShadow: isActive ? 'none' : '1px 1px 0 var(--color-rule)',
                      cursor: 'pointer',
                    }}
                  >
                    {tab.toUpperCase()}
                  </button>
                );
              })}
            </div>

            {/* Stream Pause / Resume Control (WCAG 2.2.2 / UX-007) */}
            <button
              type="button"
              onClick={togglePause}
              aria-label={isPaused ? "Resume live telegraph dispatches" : "Pause live telegraph stream to read dispatches"}
              style={{
                padding: '3px 8px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 800,
                background: isPaused ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: isPaused ? 'var(--color-on-win-yellow)' : 'var(--color-ink)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                boxShadow: '1px 1px 0 var(--color-rule)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
              title="Pause or resume live incoming dispatch stream (WCAG 2.2.2)"
            >
              {isPaused ? `▶ RESUME (${pendingCount > 0 ? `+${pendingCount}` : 'LIVE'})` : '⏸ PAUSE'}
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {isPaused && (
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 800,
                  fontFamily: 'var(--font-precision)',
                  color: 'var(--color-on-win-yellow)',
                  background: 'var(--color-win-yellow)',
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-xs)',
                  border: '1px solid var(--color-rule)',
                }}
              >
                ⏸ STREAM FROZEN
              </span>
            )}
            <Badge variant="neutral">
              {displayedRecords.length} RECORDS {filtered.length > 200 ? `(OF ${filtered.length})` : ''}
            </Badge>
          </div>
        </div>
      }
      padding="0"
    >
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', fontFamily: 'var(--font-precision)', minHeight: '300px' }}>
        {loading ? (
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} height="40px" />
            ))}
          </div>
        ) : displayedRecords.length === 0 ? (
          <EmptyState
            title="NO TELEGRAM DISPATCHES"
            message={filter === 'all' ? 'No activity records archived.' : `No activity records archived for category "${filter.toUpperCase()}".`}
            icon={<TelegraphDeskIcon size={22} />}
          />
        ) : (
          displayedRecords.map((item, idx) => (
            <ActivityRow key={item.id || idx} item={item} idx={idx} />
          ))
        )}
      </div>
    </WindowFrame>
  );
};

const ActivityRow: React.FC<{ item: any; idx: number }> = ({ item, idx }) => {
  const [showJson, setShowJson] = useState(false);
  const { text, json } = parseLogDescription(item.description);

  return (
    <div
      style={{
        display: 'flex',
        gap: '12px',
        padding: '10px 16px',
        borderBottom: '1px solid var(--color-rule)',
        background: idx % 2 === 1 ? 'var(--color-surface-hover)' : 'transparent',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Badge variant={item.category as any} size="sm">
              {item.category}
            </Badge>
            {json && (
              <button
                type="button"
                onClick={() => setShowJson(!showJson)}
                style={{
                  padding: '1px 5px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 800,
                  background: showJson ? 'var(--color-win-yellow)' : 'var(--color-paper)',
                  color: showJson ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  cursor: 'pointer',
                }}
              >
                {showJson ? '[HIDE RAW]' : '[PAYLOAD]'}
              </button>
            )}
          </div>
          <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            {fmt.time(item.timestamp)}
          </span>
        </div>
        <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: 1.5, margin: 0, wordBreak: 'break-word' }}>
          {text}
        </p>
        {showJson && json && (
          <pre
            style={{
              marginTop: '8px',
              padding: '8px 10px',
              background: 'var(--color-paper-sunken)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              lineHeight: 1.4,
              overflowX: 'auto',
              maxHeight: '180px',
              color: 'var(--color-ink)',
            }}
          >
            {json}
          </pre>
        )}
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { TelegraphDeskIcon } from '../ui/RetroIcons';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

import { EmptyState } from '../ui/EmptyState';

const FILTER_TABS = ['all', 'trading', 'analysis', 'risk', 'system'];

export const ActivityFeed: React.FC = () => {
  const { activity, loading } = useDashboardStore();
  const [filter, setFilter] = useState('all');
  const filtered = filter === 'all' ? activity : activity.filter((a) => a.category === filter);

  return (
    <WindowFrame
      title="DISPATCH TELEGRAPH LOG"
      icon={<TelegraphDeskIcon size={18} />}
      variant="yellow"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, padding: 0 }}
      actions={
        <Badge variant="neutral">
          {filtered.length} RECORDS
        </Badge>
      }
      padding="0"
    >
      {/* Sub-toolbar: Category Filter Buttons */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          padding: '6px 10px',
          background: 'var(--color-paper-subtle)',
          borderBottom: '1.5px solid var(--color-rule)',
          overflowX: 'auto',
          flexShrink: 0,
        }}
      >
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
                fontSize: '10px',
                fontWeight: isActive ? 800 : 600,
                background: isActive ? 'var(--color-ink)' : 'var(--color-paper-raised)',
                color: isActive ? 'var(--color-paper-raised)' : 'var(--color-ink)',
                border: '1px solid var(--color-rule)',
                borderRadius: '3px',
                boxShadow: isActive ? 'none' : '1px 1px 0 var(--color-rule)',
                cursor: 'pointer',
              }}
            >
              {tab.toUpperCase()}
            </button>
          );
        })}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', fontFamily: 'var(--font-precision)', minHeight: '300px' }}>
        {loading ? (
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} height="40px" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="NO TELEGRAM DISPATCHES"
            message={filter === 'all' ? 'No activity records archived.' : `No activity records archived for category "${filter.toUpperCase()}".`}
            icon={<TelegraphDeskIcon size={22} />}
          />
        ) : (
          filtered.map((item, idx) => (
            <div
              key={item.id || idx}
              style={{
                display: 'flex',
                gap: '12px',
                padding: '10px 16px',
                borderBottom: '1px solid var(--color-rule)',
                background: idx % 2 === 1 ? 'color-mix(in srgb, var(--color-paper-raised) 95%, var(--color-ink))' : 'transparent',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <Badge variant={item.category as any} size="sm">
                    {item.category}
                  </Badge>
                  <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                    {fmt.time(item.timestamp)}
                  </span>
                </div>
                <p style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: 1.5, margin: 0, wordBreak: 'break-word' }}>
                  {item.description}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </WindowFrame>
  );
};

import React, { useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { FloppyDiskIcon } from '../ui/RetroIcons';
import { ConfirmModal } from '../ui/ConfirmModal';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { api } from '../../lib/api';
import type { Position } from '../../types/api';

import { sounds } from '../../lib/soundEffects';

type SortField = 'symbol' | 'direction' | 'volume' | 'entry_price' | 'sl' | 'tp' | 'pnl' | 'opened_at';

interface ColumnDef {
  key: SortField;
  label: string;
}

const COLUMNS: ColumnDef[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'direction', label: 'Side' },
  { key: 'volume', label: 'Volume' },
  { key: 'entry_price', label: 'Entry Price' },
  { key: 'sl', label: 'Stop Loss' },
  { key: 'tp', label: 'Take Profit' },
  { key: 'pnl', label: 'P&L' },
  { key: 'opened_at', label: 'Opened' },
];

import { EmptyState } from '../ui/EmptyState';

export const PositionsTable: React.FC = () => {
  const { positions, loading, fetchAll } = useDashboardStore();
  const [showClosed, setShowClosed] = useState(false);
  const [sortField, setSortField] = useState<SortField>('opened_at');
  const [sortAsc, setSortAsc] = useState(false);
  const [closingPos, setClosingPos] = useState<Position | null>(null);
  const [isClosing, setIsClosing] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const open = positions.filter((p) => p.status === 'open');
  const closed = positions.filter((p) => p.status === 'closed');
  const displayed = showClosed ? closed : open;

  const handleSort = (field: SortField) => {
    sounds.playClick('typewriter');
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const handleConfirmClose = async () => {
    if (!closingPos) return;
    setIsClosing(true);
    setActionMsg(null);
    try {
      sounds.playClick('toggle');
      await api.closePosition({
        ticket: closingPos.mt5_ticket ?? undefined,
        position_id: closingPos.id,
        reason: 'Manual close from Dashboard',
      });
      setActionMsg(`Closed position ${closingPos.symbol} (#${closingPos.mt5_ticket || closingPos.id}) successfully.`);
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Failed to close position: ${err.message}`);
    } finally {
      setIsClosing(false);
      setClosingPos(null);
    }
  };

  const sorted = [...displayed].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    if (aVal === null || aVal === undefined) return 1;
    if (bVal === null || bVal === undefined) return -1;
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    return sortAsc ? (Number(aVal) - Number(bVal)) : (Number(bVal) - Number(aVal));
  });

  return (
    <WindowFrame
      title="POSITION LEDGER"
      icon={<FloppyDiskIcon size={18} />}
      variant="blue"
      actions={
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Badge variant={open.length > 0 ? 'active' : 'neutral'}>
            {open.length} POSITIONS
          </Badge>
          <div style={{ display: 'inline-flex', border: '1.5px solid var(--color-rule)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', boxShadow: '1px 1px 0 var(--color-rule)' }}>
            <button
              type="button"
              onClick={() => setShowClosed(false)}
              style={{
                padding: '3px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: !showClosed ? 700 : 500,
                background: !showClosed ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: !showClosed ? '#1C1917' : 'var(--color-ink-soft)',
                border: 'none',
                borderRight: '1.5px solid var(--color-rule)',
                cursor: 'pointer',
              }}
            >
              ACTIVE
            </button>
            <button
              type="button"
              onClick={() => setShowClosed(true)}
              style={{
                padding: '3px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: showClosed ? 700 : 500,
                background: showClosed ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: showClosed ? '#1C1917' : 'var(--color-ink-soft)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              HISTORICAL
            </button>
          </div>
        </div>
      }
      padding="0"
    >
      {actionMsg && (
        <div
          style={{
            padding: '8px 14px',
            background: 'var(--color-paper)',
            borderBottom: '1.5px solid var(--color-rule)',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-precision)',
          }}
        >
          ℹ {actionMsg}
        </div>
      )}
      {loading ? (
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} height="36px" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <EmptyState
          title="LEDGER CLEAR"
          message={showClosed ? "No closed historical positions in MT5." : "No active market positions in MT5."}
          icon={<FloppyDiskIcon size={24} />}
        />
      ) : (
        <div className="table-responsive" style={{ maxHeight: '520px', overflowY: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: 'var(--font-precision)',
              fontSize: 'var(--text-body-sm)',
            }}
          >
            <thead
              style={{
                position: 'sticky',
                top: 0,
                zIndex: 10,
                background: 'color-mix(in srgb, var(--color-paper-raised) 90%, var(--color-ink))',
                borderBottom: '2px solid var(--color-rule)',
              }}
            >
              <tr>
                {COLUMNS.map((col) => {
                  const isSorted = sortField === col.key;
                  return (
                    <th
                      key={col.key}
                      onClick={() => handleSort(col.key)}
                      style={{
                        padding: '8px 12px',
                        textAlign: 'left',
                        fontSize: 'var(--text-xs)',
                        fontWeight: 'bold',
                        color: isSorted ? 'var(--color-win-yellow)' : 'var(--color-ink)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        whiteSpace: 'nowrap',
                        borderRight: '1px solid var(--color-rule)',
                        cursor: 'pointer',
                        userSelect: 'none',
                      }}
                      title={`Sort by ${col.label}`}
                    >
                      <span>{col.label}</span>
                      <span style={{ marginLeft: '4px', fontSize: '10px' }}>
                        {isSorted ? (sortAsc ? '▲' : '▼') : '▿'}
                      </span>
                    </th>
                  );
                })}
                {!showClosed && (
                  <th
                    style={{
                      padding: '8px 12px',
                      textAlign: 'center',
                      fontSize: 'var(--text-xs)',
                      fontWeight: 'bold',
                      color: 'var(--color-ink)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Action
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {sorted.map((pos, i) => (
                <PositionRow
                  key={pos.id}
                  pos={pos}
                  isEven={i % 2 === 1}
                  showClosed={showClosed}
                  onCloseClick={(target) => setClosingPos(target)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Close Position Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(closingPos)}
        title="CLOSE POSITION ORDER"
        actionSummary={`CLOSE: ${closingPos?.symbol} (${closingPos?.direction?.toUpperCase()})`}
        details={
          closingPos && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: 'var(--text-body-sm)' }}>
              <div><strong>Ticket:</strong> #{closingPos.mt5_ticket || closingPos.id}</div>
              <div><strong>Volume:</strong> {fmt.lots(closingPos.volume)} lots</div>
              <div><strong>Entry:</strong> {fmt.price(closingPos.entry_price, closingPos.symbol)}</div>
              <div><strong>Current Floating P&L:</strong> {closingPos.pnl !== null ? fmt.usd(closingPos.pnl) : '—'}</div>
              <p style={{ margin: '8px 0 0', color: 'var(--color-ledger-red)', fontSize: 'var(--text-xs)' }}>
                This will submit a market close order to MT5 and liquidate this ticket immediately.
              </p>
            </div>
          )
        }
        confirmLabel={isClosing ? "CLOSING..." : "CONFIRM CLOSE"}
        cancelLabel="KEEP OPEN"
        danger={true}
        onConfirm={handleConfirmClose}
        onCancel={() => setClosingPos(null)}
      />
    </WindowFrame>
  );
};

const PositionRow: React.FC<{
  pos: Position;
  isEven: boolean;
  showClosed: boolean;
  onCloseClick: (pos: Position) => void;
}> = ({ pos, isEven, showClosed, onCloseClick }) => {
  const slDist = pos.entry_price && pos.sl ? Math.abs(pos.entry_price - pos.sl) : null;
  const tpDist = pos.entry_price && pos.tp ? Math.abs(pos.entry_price - pos.tp) : null;
  const rr = slDist && tpDist && slDist > 0 ? (tpDist / slDist).toFixed(2) : null;
  const pnlIsPositive = pos.pnl !== null && pos.pnl >= 0;

  return (
    <tr
      className={isEven ? 'greenbar-row' : ''}
      style={{
        background: isEven
          ? 'color-mix(in srgb, var(--color-paper-raised) 92%, var(--color-ledger-green))'
          : 'var(--color-paper-raised)',
        borderBottom: '1px solid var(--color-rule)',
        transition: 'background var(--transition-fast)',
      }}
    >
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
        <div style={{ fontWeight: 'bold', color: 'var(--color-ink)' }}>{pos.symbol}</div>
        {pos.mt5_ticket && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            #{pos.mt5_ticket}
          </div>
        )}
      </td>
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
        <Badge variant={pos.direction === 'buy' ? 'buy' : 'sell'}>
          {pos.direction.toUpperCase()}
        </Badge>
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink)' }}>
        {fmt.lots(pos.volume)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink)' }}>
        {fmt.price(pos.entry_price, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ledger-red)' }}>
        {fmt.price(pos.sl, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ledger-green)' }}>
        {fmt.price(pos.tp, pos.symbol)}
      </td>
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
        <div
          className="tabular-nums"
          style={{
            fontWeight: 'bold',
            color: pos.pnl !== null ? (pnlIsPositive ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)') : 'var(--color-ink-soft)',
          }}
        >
          {pos.pnl !== null ? (
            <>
              {pnlIsPositive ? '▲ +' : '▼ '}
              {fmt.usd(Math.abs(pos.pnl))}
            </>
          ) : (
            '—'
          )}
        </div>
        {rr && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
            R:R {rr}
          </div>
        )}
      </td>
      <td style={{ padding: '8px 12px', borderRight: !showClosed ? '1px solid var(--color-rule)' : 'none', whiteSpace: 'nowrap', color: 'var(--color-ink-soft)', fontSize: 'var(--text-xs)' }}>
        {fmt.datetime(pos.opened_at)}
      </td>
      {!showClosed && (
        <td style={{ padding: '6px 12px', textAlign: 'center' }}>
          <button
            type="button"
            onClick={() => onCloseClick(pos)}
            style={{
              padding: '2px 8px',
              fontSize: '11px',
              fontFamily: 'var(--font-precision)',
              fontWeight: 'bold',
              background: 'var(--color-loss-dim)',
              color: 'var(--color-ledger-red)',
              border: '1px solid var(--color-ledger-red)',
              borderRadius: '2px',
              cursor: 'pointer',
            }}
            title="Liquidate this open position immediately in MT5"
          >
            CLOSE
          </button>
        </td>
      )}
    </tr>
  );
};

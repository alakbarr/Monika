import React, { useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { FloppyDiskIcon } from '../ui/Icons';
import { ConfirmModal } from '../ui/ConfirmModal';
import { ManualOrderDrawer } from '../ui/ManualOrderDrawer';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { api } from '../../lib/api';
import type { Position } from '../../types/api';

import { sounds } from '../../lib/soundEffects';
import { DecisionDossierModal } from './DecisionDossierModal';

type SortField = 'symbol' | 'direction' | 'volume' | 'entry_price' | 'price_current' | 'sl' | 'tp' | 'swap' | 'pnl' | 'opened_at';

interface ColumnDef {
  key: SortField;
  label: string;
  align?: 'left' | 'right' | 'center';
}

const COLUMNS: ColumnDef[] = [
  { key: 'symbol', label: 'Symbol', align: 'left' },
  { key: 'direction', label: 'Side', align: 'left' },
  { key: 'volume', label: 'Volume', align: 'right' },
  { key: 'entry_price', label: 'Entry', align: 'right' },
  { key: 'price_current', label: 'Market', align: 'right' },
  { key: 'sl', label: 'Stop Loss', align: 'right' },
  { key: 'tp', label: 'Take Profit', align: 'right' },
  { key: 'swap', label: 'Swap', align: 'right' },
  { key: 'pnl', label: 'P&L', align: 'right' },
  { key: 'opened_at', label: 'Opened', align: 'left' },
];

import { EmptyState } from '../ui/EmptyState';

export const PositionsTable: React.FC = () => {
  const { positions, loading, fetchAll, wsConnected } = useDashboardStore();
  const [showClosed, setShowClosed] = useState(false);
  const [sortField, setSortField] = useState<SortField>('opened_at');
  const [sortAsc, setSortAsc] = useState(false);
  const [pnlUnit, setPnlUnit] = useState<'usd' | 'pips' | 'r'>('usd');
  const [closingPos, setClosingPos] = useState<Position | null>(null);
  const [closePercentage, setClosePercentage] = useState<number>(100);
  const [closeVolume, setCloseVolume] = useState<string>('');
  const [isClosing, setIsClosing] = useState(false);
  const [isBulkBeRunning, setIsBulkBeRunning] = useState(false);
  const [editingPos, setEditingPos] = useState<Position | null>(null);
  const [editSl, setEditSl] = useState('');
  const [editTp, setEditTp] = useState('');
  const [isModifying, setIsModifying] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [isOrderDrawerOpen, setIsOrderDrawerOpen] = useState(false);
  const [orderDrawerSymbol, setOrderDrawerSymbol] = useState('EURUSD');
  const [isBatchClosing, setIsBatchClosing] = useState(false);
  const [batchCloseConfirmOpen, setBatchCloseConfirmOpen] = useState(false);
  const [dossierPos, setDossierPos] = useState<Position | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

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

  const handleOpenEdit = (pos: Position) => {
    sounds.playClick('typewriter');
    setEditingPos(pos);
    setEditSl(pos.sl !== null && pos.sl !== undefined ? String(pos.sl) : '');
    setEditTp(pos.tp !== null && pos.tp !== undefined ? String(pos.tp) : '');
  };

  const handleConfirmModify = async () => {
    if (!editingPos) return;
    const ticket = editingPos.mt5_ticket;
    if (!ticket) {
      setActionMsg(`Position #${editingPos.id} has no MT5 ticket.`);
      setEditingPos(null);
      return;
    }
    setIsModifying(true);
    setActionMsg(null);
    try {
      sounds.playClick('toggle');
      const slVal = editSl.trim() === '' ? undefined : Number(editSl);
      const tpVal = editTp.trim() === '' ? undefined : Number(editTp);
      await api.positionModify(ticket, {
        sl: slVal !== undefined && !isNaN(slVal) ? slVal : undefined,
        tp: tpVal !== undefined && !isNaN(tpVal) ? tpVal : undefined,
      });
      setActionMsg(`Modified SL/TP for ${editingPos.symbol} (#${ticket}) successfully.`);
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Failed to modify position: ${err.message}`);
    } finally {
      setIsModifying(false);
      setEditingPos(null);
    }
  };

  const handleBreakeven = async (pos: Position) => {
    const ticket = pos.mt5_ticket;
    if (!ticket) {
      setActionMsg(`Position #${pos.id} has no MT5 ticket.`);
      return;
    }
    sounds.playClick('toggle');
    try {
      await api.breakevenPosition(ticket);
      setActionMsg(`Moved SL to Break-Even for ${pos.symbol} (#${ticket}).`);
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Failed to set Break-Even: ${err.message}`);
    }
  };

  const handleBulkBreakeven = async () => {
    setIsBulkBeRunning(true);
    sounds.playClick('toggle');
    try {
      const res = await api.bulkBreakeven(true);
      setActionMsg(res.message || 'Set Break-Even on profitable positions.');
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Bulk Break-Even failed: ${err.message}`);
    } finally {
      setIsBulkBeRunning(false);
    }
  };

  const handleOpenClose = (pos: Position) => {
    sounds.playClick('typewriter');
    setClosingPos(pos);
    setClosePercentage(100);
    setCloseVolume(String(pos.volume));
  };

  const handleConfirmClose = async () => {
    if (!closingPos) return;
    setIsClosing(true);
    setActionMsg(null);
    try {
      sounds.playClick('toggle');
      const volNum = closeVolume ? Number(closeVolume) : undefined;
      await api.closePosition({
        ticket: closingPos.mt5_ticket ?? undefined,
        position_id: closingPos.id,
        percentage: closePercentage < 100 ? closePercentage : undefined,
        volume: volNum && volNum < closingPos.volume ? volNum : undefined,
        reason: closePercentage < 100 ? `Manual partial close (${closePercentage}%)` : 'Manual close from Dashboard',
      });
      setActionMsg(`Closed ${closePercentage}% of position ${closingPos.symbol} (#${closingPos.mt5_ticket || closingPos.id}) successfully.`);
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Failed to close position: ${err.message}`);
    } finally {
      setIsClosing(false);
      setClosingPos(null);
    }
  };

  const handleConfirmBatchClose = async () => {
    setIsBatchClosing(true);
    setActionMsg(null);
    sounds.playClick('toggle');
    try {
      const res = await api.closeBatchPositions({
        filter_type: 'all',
        reason: 'Emergency Close All from Dashboard',
      });
      setActionMsg(`Closed ${(res as any).result?.closed_count ?? res.closed_count ?? 0} positions successfully.`);
      await fetchAll();
    } catch (err: any) {
      setActionMsg(`Batch close failed: ${err.message}`);
    } finally {
      setIsBatchClosing(false);
      setBatchCloseConfirmOpen(false);
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

  const totalLots = displayed.reduce((acc, p) => acc + (p.volume || 0), 0);
  const totalSwap = displayed.reduce((acc, p) => acc + (p.swap || 0), 0);
  const totalPnlUsd = displayed.reduce((acc, p) => acc + (p.pnl ?? 0), 0);

  const handleTableKeyDown = (e: React.KeyboardEvent) => {
    if (sorted.length === 0) return;
    const currentIndex = sorted.findIndex((p) => p.id === selectedId);

    if (e.key === 'j' || e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = currentIndex < sorted.length - 1 ? currentIndex + 1 : 0;
      setSelectedId(sorted[nextIndex].id);
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = currentIndex > 0 ? currentIndex - 1 : sorted.length - 1;
      setSelectedId(sorted[prevIndex].id);
    } else if (e.key === 'Escape') {
      setSelectedId(null);
    }
  };

  return (
    <WindowFrame
      title="POSITION LEDGER"
      icon={<FloppyDiskIcon size={18} />}
      variant="blue"
      toolbar={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', flexWrap: 'wrap', gap: '8px' }}>
          {/* Left: View & Unit Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Active vs Historical */}
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
                  color: !showClosed ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
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
                  color: showClosed ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                HISTORICAL
              </button>
            </div>

            {/* P&L Unit Selector */}
            <div style={{ display: 'inline-flex', border: '1.5px solid var(--color-rule)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', boxShadow: '1px 1px 0 var(--color-rule)' }}>
              {(['usd', 'pips', 'r'] as const).map((u) => (
                <button
                  key={u}
                  type="button"
                  onClick={() => {
                    sounds.playClick('toggle');
                    setPnlUnit(u);
                  }}
                  style={{
                    padding: '3px 8px',
                    fontSize: '11px',
                    fontFamily: 'var(--font-precision)',
                    fontWeight: pnlUnit === u ? 700 : 500,
                    background: pnlUnit === u ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                    color: pnlUnit === u ? 'var(--color-on-win-yellow)' : 'var(--color-ink-soft)',
                    border: 'none',
                    borderRight: u !== 'r' ? '1.5px solid var(--color-rule)' : 'none',
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                  }}
                >
                  {u === 'usd' ? '$ USD' : u.toUpperCase()}
                </button>
              ))}
            </div>

            <Badge variant={open.length > 0 ? 'active' : 'neutral'}>
              {open.length} OPEN
            </Badge>

            {!wsConnected && (
              <span
                style={{
                  padding: '2px 8px',
                  fontSize: '11px',
                  fontWeight: 800,
                  fontFamily: 'var(--font-precision)',
                  background: 'repeating-linear-gradient(45deg, var(--color-loss-dim) 0px, var(--color-loss-dim) 3px, transparent 3px, transparent 6px)',
                  color: 'var(--color-ledger-red)',
                  border: '1.5px solid var(--color-ledger-red)',
                  borderRadius: 'var(--radius-xs)',
                  letterSpacing: '0.04em',
                }}
                title="WebSocket disconnected. Live prices and unbooked P&L show last known recorded values."
              >
                ⚠ STALE (OFFLINE)
              </span>
            )}
          </div>

          {/* Right: Operational Action Triggers */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              onClick={() => {
                sounds.playClick('typewriter');
                setOrderDrawerSymbol(open[0]?.symbol || 'EURUSD');
                setIsOrderDrawerOpen(true);
              }}
              style={{
                padding: '3px 10px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 800,
                background: 'var(--color-ledger-green)',
                color: 'var(--color-on-win-green)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                boxShadow: '1px 1px 0 var(--color-rule)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
              title="Create and execute a new manual market or limit trade order"
            >
              ⚡ NEW ORDER
            </button>

            {/* Bulk Break-Even */}
            {open.length > 0 && (
              <button
                type="button"
                disabled={isBulkBeRunning}
                onClick={handleBulkBreakeven}
                style={{
                  padding: '3px 9px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 700,
                  background: 'var(--color-paper-raised)',
                  color: 'var(--color-ink)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  boxShadow: '1px 1px 0 var(--color-rule)',
                  cursor: 'pointer',
                }}
                title="Set Break-Even on all currently profitable positions"
              >
                {isBulkBeRunning ? 'SETTING...' : '🛡️ BULK BE'}
              </button>
            )}

            {open.length > 0 && (
              <button
                type="button"
                disabled={isBatchClosing}
                onClick={() => {
                  sounds.playClick('toggle');
                  setBatchCloseConfirmOpen(true);
                }}
                style={{
                  padding: '3px 10px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 800,
                  background: 'var(--color-ledger-red)',
                  color: 'var(--color-on-win-coral)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  boxShadow: '1px 1px 0 var(--color-rule)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                title="Liquidate all open positions across all instruments immediately"
              >
                {isBatchClosing ? 'CLOSING...' : '🚨 CLOSE ALL'}
              </button>
            )}
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
          compact
          title="LEDGER CLEAR"
          message={showClosed ? "No closed historical positions in MT5." : "No active market positions in MT5 — watching target symbols."}
          icon={<FloppyDiskIcon size={16} />}
        />
      ) : (
        <div
          className="table-responsive"
          tabIndex={0}
          onKeyDown={handleTableKeyDown}
          aria-label="Positions ledger. Press J and K or arrow keys to navigate rows."
          style={{ maxHeight: '520px', overflowY: 'auto', outline: 'none' }}
        >
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
                background: 'var(--color-table-header)',
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
                      aria-sort={isSorted ? (sortAsc ? 'ascending' : 'descending') : 'none'}
                      style={{
                        padding: '8px 12px',
                        textAlign: col.align || 'left',
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
                      <span style={{ marginLeft: '4px', fontSize: '11px' }}>
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
                  isSelected={selectedId === pos.id}
                  showClosed={showClosed}
                  pnlUnit={pnlUnit}
                  onSelect={() => setSelectedId(pos.id)}
                  onCloseClick={(target) => handleOpenClose(target)}
                  onEditClick={(target) => handleOpenEdit(target)}
                  onBreakevenClick={(target) => handleBreakeven(target)}
                  onDossierClick={(target) => setDossierPos(target)}
                />
              ))}
            </tbody>
            <tfoot
              style={{
                position: 'sticky',
                bottom: 0,
                zIndex: 8,
                background: 'var(--color-paper-raised)',
                borderTop: '2px solid var(--color-rule)',
              }}
            >
              <tr style={{ background: 'var(--color-paper-raised)', fontWeight: 'bold' }}>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', fontWeight: 800 }}>
                  TOTAL ({displayed.length})
                </td>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
                  —
                </td>
                <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right' }}>
                  {fmt.lots(totalLots)}
                </td>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right', color: 'var(--color-ink-soft)' }}>
                  —
                </td>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right', color: 'var(--color-ink-soft)' }}>
                  —
                </td>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right', color: 'var(--color-ink-soft)' }}>
                  —
                </td>
                <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right', color: 'var(--color-ink-soft)' }}>
                  —
                </td>
                <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right', fontSize: 'var(--text-xs)' }}>
                  {fmt.usd(totalSwap)}
                </td>
                <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right' }}>
                  <span style={{ color: totalPnlUsd >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
                    {totalPnlUsd >= 0 ? '▲ +' : '▼ '}
                    {fmt.usd(Math.abs(totalPnlUsd))}
                  </span>
                </td>
                <td style={{ padding: '8px 12px', borderRight: !showClosed ? '1px solid var(--color-rule)' : 'none', color: 'var(--color-ink-soft)', fontSize: 'var(--text-xs)' }}>
                  —
                </td>
                {!showClosed && (
                  <td style={{ padding: '6px 10px', textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                    —
                  </td>
                )}
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Modify SL/TP Modal */}
      <ConfirmModal
        isOpen={Boolean(editingPos)}
        title="MODIFY POSITION SL / TP"
        actionSummary={`MODIFY: ${editingPos?.symbol} (#${editingPos?.mt5_ticket || editingPos?.id})`}
        details={
          editingPos && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: 'var(--text-body-sm)' }}>
              <div><strong>Symbol:</strong> {editingPos.symbol} ({editingPos.direction.toUpperCase()})</div>
              <div><strong>Entry:</strong> {fmt.price(editingPos.entry_price, editingPos.symbol)}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>STOP LOSS (SL):</label>
                <input
                  type="number"
                  step="any"
                  value={editSl}
                  onChange={(e) => setEditSl(e.target.value)}
                  placeholder="Leave empty or set 0 to remove"
                  style={{
                    padding: '6px 8px',
                    fontFamily: 'var(--font-precision)',
                    fontSize: 'var(--text-xs)',
                    border: '1.5px solid var(--color-rule)',
                    borderRadius: '2px',
                    background: 'var(--color-paper)',
                    color: 'var(--color-ink)',
                  }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>TAKE PROFIT (TP):</label>
                <input
                  type="number"
                  step="any"
                  value={editTp}
                  onChange={(e) => setEditTp(e.target.value)}
                  placeholder="Leave empty or set 0 to remove"
                  style={{
                    padding: '6px 8px',
                    fontFamily: 'var(--font-precision)',
                    fontSize: 'var(--text-xs)',
                    border: '1.5px solid var(--color-rule)',
                    borderRadius: '2px',
                    background: 'var(--color-paper)',
                    color: 'var(--color-ink)',
                  }}
                />
              </div>
            </div>
          )
        }
        confirmLabel={isModifying ? "UPDATING..." : "UPDATE SL/TP"}
        cancelLabel="CANCEL"
        danger={false}
        onConfirm={handleConfirmModify}
        onCancel={() => setEditingPos(null)}
      />

      {/* Close Position Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(closingPos)}
        title={closePercentage < 100 ? `PARTIAL CLOSE (${closePercentage}%)` : "CLOSE POSITION ORDER"}
        actionSummary={`CLOSE: ${closingPos?.symbol} (${closingPos?.direction?.toUpperCase()})`}
        details={
          closingPos && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: 'var(--text-body-sm)' }}>
              <div><strong>Ticket:</strong> #{closingPos.mt5_ticket || closingPos.id}</div>
              <div><strong>Total Open Volume:</strong> {fmt.lots(closingPos.volume)} lots</div>
              <div><strong>Entry:</strong> {fmt.price(closingPos.entry_price, closingPos.symbol)}</div>
              <div><strong>Current Floating P&L:</strong> {closingPos.pnl !== null ? fmt.usd(closingPos.pnl) : '—'}</div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '4px 0' }}>
                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>PORTION:</span>
                {[25, 50, 100].map((pct) => (
                  <button
                    key={pct}
                    type="button"
                    onClick={() => {
                      setClosePercentage(pct);
                      setCloseVolume(((closingPos.volume * pct) / 100).toFixed(2));
                    }}
                    style={{
                      padding: '3px 8px',
                      fontSize: '11px',
                      fontFamily: 'var(--font-precision)',
                      fontWeight: closePercentage === pct ? 700 : 500,
                      background: closePercentage === pct ? 'var(--color-win-yellow)' : 'var(--color-paper)',
                      color: closePercentage === pct ? 'var(--color-on-win-yellow)' : 'var(--color-ink)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: '2px',
                      cursor: 'pointer',
                    }}
                  >
                    {pct}%
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>VOLUME TO CLOSE (LOTS):</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={closingPos.volume}
                  value={closeVolume}
                  onChange={(e) => setCloseVolume(e.target.value)}
                  style={{
                    padding: '6px 8px',
                    fontFamily: 'var(--font-precision)',
                    fontSize: 'var(--text-xs)',
                    border: '1.5px solid var(--color-rule)',
                    borderRadius: '2px',
                    background: 'var(--color-paper)',
                    color: 'var(--color-ink)',
                  }}
                />
              </div>

              <p style={{ margin: '4px 0 0', color: 'var(--color-ledger-red)', fontSize: 'var(--text-xs)' }}>
                {closePercentage < 100
                  ? `Submitting partial liquidation order for ${closeVolume || ((closingPos.volume * closePercentage) / 100).toFixed(2)} lots to MT5.`
                  : 'This will submit a market close order to MT5 and liquidate this ticket immediately.'}
              </p>
            </div>
          )
        }
        confirmLabel={isClosing ? "CLOSING..." : (closePercentage < 100 ? `CLOSE ${closePercentage}%` : "CONFIRM CLOSE")}
        cancelLabel="KEEP OPEN"
        danger={true}
        onConfirm={handleConfirmClose}
        onCancel={() => setClosingPos(null)}
      />

      {/* Emergency Batch Close All Confirmation Modal */}
      <ConfirmModal
        isOpen={batchCloseConfirmOpen}
        title="EMERGENCY CLOSE ALL POSITIONS"
        actionSummary={`LIQUIDATE ALL ${open.length} ACTIVE POSITIONS NOW`}
        details={
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: 'var(--text-body-sm)' }}>
            <p style={{ margin: 0, color: 'var(--color-ledger-red)', fontWeight: 700 }}>
              Are you sure you want to execute a batch market liquidation on all {open.length} open tickets?
            </p>
            <div style={{ background: 'var(--color-paper)', padding: '8px', border: '1px solid var(--color-rule)', maxHeight: '120px', overflowY: 'auto' }}>
              {open.map((p) => (
                <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '2px 0' }}>
                  <span>#{p.mt5_ticket || p.id} {p.symbol} ({p.direction.toUpperCase()}) {p.volume}L</span>
                  <span className="tabular-nums">{p.pnl !== null && p.pnl !== undefined ? fmt.usd(p.pnl) : '—'}</span>
                </div>
              ))}
            </div>
            <p style={{ margin: 0, fontSize: '11px', color: 'var(--color-ink-soft)' }}>
              This action calls the broker liquidation gateway to cleanly close all positions.
            </p>
          </div>
        }
        confirmLabel={isBatchClosing ? "LIQUIDATING..." : "CONFIRM EMERGENCY CLOSE ALL"}
        cancelLabel="ABORT"
        danger={true}
        onConfirm={handleConfirmBatchClose}
        onCancel={() => setBatchCloseConfirmOpen(false)}
      />

      {/* Manual Order Entry Drawer */}
      <ManualOrderDrawer
        isOpen={isOrderDrawerOpen}
        initialSymbol={orderDrawerSymbol}
        onClose={() => setIsOrderDrawerOpen(false)}
        onOrderSuccess={fetchAll}
      />

      {/* 1-Click Decision Dossier Modal */}
      <DecisionDossierModal
        isOpen={Boolean(dossierPos)}
        onClose={() => setDossierPos(null)}
        analysisId={dossierPos?.analysis_id}
        symbol={dossierPos?.symbol}
        ticket={dossierPos?.mt5_ticket}
      />
    </WindowFrame>
  );
};

const renderPnl = (pos: Position, unit: 'usd' | 'pips' | 'r') => {
  const pnlVal = pos.pnl ?? pos.floating_pnl ?? 0;
  const isPos = pnlVal >= 0;

  if (unit === 'usd') {
    return (
      <span style={{ color: isPos ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
        {isPos ? '▲ +' : '▼ '}
        {fmt.usd(Math.abs(pnlVal))}
      </span>
    );
  }

  const isJpy = pos.symbol.toUpperCase().includes('JPY');
  const isGold = pos.symbol.toUpperCase().includes('XAU');
  const pipMultiplier = isJpy ? 100 : (isGold ? 10 : 10000);
  const currentPrice = pos.price_current ?? pos.current_price ?? pos.entry_price;
  const priceDiff = pos.direction === 'buy' ? (currentPrice - pos.entry_price) : (pos.entry_price - currentPrice);
  const pips = priceDiff * pipMultiplier;

  if (unit === 'pips') {
    const pipsPositive = pips >= 0;
    return (
      <span style={{ color: pipsPositive ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
        {pipsPositive ? '▲ +' : '▼ '}
        {Math.abs(pips).toFixed(1)} pips
      </span>
    );
  }

  // unit === 'r'
  if (pos.sl && Math.abs(pos.entry_price - pos.sl) > 0) {
    const riskDistance = Math.abs(pos.entry_price - pos.sl);
    const rMultiple = priceDiff / riskDistance;
    const rPos = rMultiple >= 0;
    return (
      <span style={{ color: rPos ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
        {rPos ? '▲ +' : '▼ '}
        {Math.abs(rMultiple).toFixed(2)} R
      </span>
    );
  }

  return (
    <span style={{ color: isPos ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)' }}>
      {isPos ? '▲ +' : '▼ '}
      {fmt.usd(Math.abs(pnlVal))}
    </span>
  );
};

const PositionRow: React.FC<{
  pos: Position;
  isEven: boolean;
  isSelected: boolean;
  showClosed: boolean;
  pnlUnit: 'usd' | 'pips' | 'r';
  onSelect: () => void;
  onCloseClick: (pos: Position) => void;
  onEditClick: (pos: Position) => void;
  onBreakevenClick: (pos: Position) => void;
  onDossierClick: (pos: Position) => void;
}> = ({ pos, isEven, isSelected, showClosed, pnlUnit, onSelect, onCloseClick, onEditClick, onBreakevenClick, onDossierClick }) => {
  const slDist = pos.entry_price && pos.sl ? Math.abs(pos.entry_price - pos.sl) : null;
  const tpDist = pos.entry_price && pos.tp ? Math.abs(pos.entry_price - pos.tp) : null;
  const rr = slDist && tpDist && slDist > 0 ? (tpDist / slDist).toFixed(2) : null;
  const marketPrice = pos.price_current ?? pos.current_price ?? pos.entry_price;

  return (
    <tr
      className={isSelected ? 'retro-row-selected' : (isEven ? 'greenbar-row' : '')}
      aria-selected={isSelected}
      onClick={onSelect}
      style={{
        background: isSelected
          ? 'var(--color-ink)'
          : isEven
            ? 'var(--color-profit-dim)'
            : 'var(--color-paper-raised)',
        color: isSelected ? 'var(--color-paper-raised)' : 'inherit',
        borderBottom: '1px solid var(--color-rule)',
        transition: 'background var(--transition-fast)',
        cursor: 'pointer',
      }}
    >
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontWeight: 'bold', color: 'var(--color-ink)' }}>{pos.symbol}</span>
          <Badge variant={pos.is_paper ? 'neutral' : 'active'}>
            {pos.is_paper ? 'PAPER' : 'LIVE'}
          </Badge>
        </div>
        {pos.mt5_ticket && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', display: 'flex', alignItems: 'center', marginTop: '4px' }}>
            <span>#{pos.mt5_ticket}</span>
            <button
              type="button"
              className="table-action-btn"
              onClick={(e) => { e.stopPropagation(); onDossierClick(pos); }}
              style={{
                marginLeft: '8px',
                padding: '3px 8px',
                minHeight: '26px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-info-dim)',
                color: 'var(--color-text-info)',
                border: '1px solid var(--color-rule)',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
              title="Inspect 1-Click Decision Dossier (Why was this trade taken?)"
            >
              🔍 DOSSIER
            </button>
          </div>
        )}
      </td>
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)' }}>
        <Badge variant={pos.direction === 'buy' ? 'buy' : 'sell'}>
          {pos.direction.toUpperCase()}
        </Badge>
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink)', textAlign: 'right' }}>
        {fmt.lots(pos.volume)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink)', textAlign: 'right' }}>
        {fmt.price(pos.entry_price, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink)', textAlign: 'right' }}>
        {fmt.price(marketPrice, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-text-loss)', textAlign: 'right' }}>
        {fmt.price(pos.sl, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-text-profit)', textAlign: 'right' }}>
        {fmt.price(pos.tp, pos.symbol)}
      </td>
      <td className="tabular-nums" style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', color: 'var(--color-ink-soft)', fontSize: 'var(--text-xs)', textAlign: 'right' }}>
        {pos.swap !== undefined && pos.swap !== null ? fmt.usd(pos.swap) : '—'}
      </td>
      <td style={{ padding: '8px 12px', borderRight: '1px solid var(--color-rule)', textAlign: 'right' }}>
        <div className="tabular-nums" style={{ fontWeight: 'bold' }}>
          {renderPnl(pos, pnlUnit)}
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
        <td style={{ padding: '6px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <button
              type="button"
              className="table-action-btn"
              onClick={() => onDossierClick(pos)}
              aria-label={`Buka decision dossier untuk ${pos.symbol}`}
              style={{
                padding: '4px 8px',
                minHeight: '32px',
                minWidth: '32px',
                fontSize: '12px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-info-dim)',
                color: 'var(--color-text-info)',
                border: '1px solid var(--color-rule)',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Inspect 1-Click Decision Dossier"
            >
              🔍
            </button>
            <button
              type="button"
              className="table-action-btn"
              onClick={() => onBreakevenClick(pos)}
              aria-label={`Break even untuk ${pos.symbol}`}
              style={{
                padding: '4px 8px',
                minHeight: '32px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-warn-dim)',
                color: 'var(--color-text-warn)',
                border: '1px solid var(--color-rule)',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Set Stop Loss to Break-Even (entry price)"
            >
              BE
            </button>
            <button
              type="button"
              className="table-action-btn"
              onClick={() => onEditClick(pos)}
              aria-label={`Edit SL/TP untuk ${pos.symbol}`}
              style={{
                padding: '4px 8px',
                minHeight: '32px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-paper)',
                color: 'var(--color-ink)',
                border: '1px solid var(--color-rule)',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Modify Stop Loss and Take Profit in MT5"
            >
              EDIT
            </button>
            <button
              type="button"
              className="table-action-btn"
              onClick={() => onCloseClick(pos)}
              aria-label={`Tutup posisi ${pos.symbol}`}
              style={{
                padding: '4px 8px',
                minHeight: '32px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-loss-dim)',
                color: 'var(--color-text-loss)',
                border: '1px solid var(--color-ledger-red)',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Liquidate or partially close this position"
            >
              CLOSE
            </button>
          </div>
        </td>
      )}
    </tr>
  );
};

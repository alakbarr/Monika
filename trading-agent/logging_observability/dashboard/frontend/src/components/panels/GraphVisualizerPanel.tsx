import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Workflow,
  Sparkles,
  Loader2,
  Compass,
  Send,
  X,
} from 'lucide-react';
import { api } from '../../lib/api';
import type { GraphStateResponse, GraphNode, CycleItem } from '../../types/api';
import { GraphControls } from './graph/GraphControls';
import { GraphEdge } from './graph/GraphEdge';
import { GraphNodeComponent } from './graph/GraphNode';
import { GraphInspector } from './graph/GraphInspector';

// Visual canvas dimensions & node geometry
const NODE_WIDTH = 220;
const NODE_HEIGHT = 120;

// Coordinate layout for the 7 LangGraph nodes
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  fundamental_brief: { x: 50, y: 260 },
  prefetch_data: { x: 330, y: 260 },
  bull_advocate: { x: 650, y: 130 },
  bear_dissent: { x: 650, y: 390 },
  debate_judge: { x: 950, y: 260 },
  risk_gate: { x: 1250, y: 260 },
  execution: { x: 1510, y: 260 },
};

export const GraphVisualizerPanel: React.FC = () => {
  const [graphData, setGraphData] = useState<GraphStateResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedCycle, setSelectedCycle] = useState<string>('');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  // Steer Directive Modal State
  const [showSteerModal, setShowSteerModal] = useState<boolean>(false);
  const [steerMessage, setSteerMessage] = useState<string>('');
  const [steerMode, setSteerMode] = useState<string>('steer');
  const [steerSymbols, setSteerSymbols] = useState<string>('');
  const [steerLoading, setSteerLoading] = useState<boolean>(false);

  // Viewport transform state: scale and translation
  const [transform, setTransform] = useState<{ x: number; y: number; k: number }>({
    x: 30,
    y: 30,
    k: 0.60,
  });
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const panStartRef = useRef<{ startX: number; startY: number; initX: number; initY: number }>({
    startX: 0,
    startY: 0,
    initX: 0,
    initY: 0,
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const lastFetchedCycleRef = useRef<string | null>(null);

  // Load graph state from backend
  const loadGraphState = useCallback(async (cycleId?: string) => {
    try {
      setLoading(true);
      const res = await api.graphState(cycleId);
      setGraphData(res);
      lastFetchedCycleRef.current = res.cycle_id;
      setSelectedCycle(res.cycle_id);
      setSelectedNodeId(curr => curr || (res.nodes.length > 0 ? res.nodes[0].id : null));
    } catch (err) {
      console.error('Failed to load graph state:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraphState(selectedCycle || undefined);
  }, [selectedCycle, loadGraphState]);

  // Polling fallback
  useEffect(() => {
    const interval = setInterval(() => {
      loadGraphState(selectedCycle || undefined);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedCycle, loadGraphState]);

  // Viewport zoom & pan handlers
  const handleZoom = (factor: number) => {
    setTransform(curr => ({
      ...curr,
      k: Math.min(Math.max(curr.k * factor, 0.4), 2.2),
    }));
  };

  const handleReset = () => {
    setTransform({ x: 40, y: 20, k: 0.78 });
  };

  const handleFitScreen = () => {
    if (!containerRef.current) return;
    const { clientWidth } = containerRef.current;
    const scale = Math.min(Math.max(clientWidth / 1850, 0.45), 1.1);
    setTransform({
      x: 20,
      y: 40,
      k: scale,
    });
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('g[style*="cursor: pointer"]')) return;
    setIsPanning(true);
    panStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initX: transform.x,
      initY: transform.y,
    };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isPanning) return;
    const dx = e.clientX - panStartRef.current.startX;
    const dy = e.clientY - panStartRef.current.startY;
    setTransform(curr => ({
      ...curr,
      x: panStartRef.current.initX + dx,
      y: panStartRef.current.initY + dy,
    }));
  };

  const handleMouseUp = () => setIsPanning(false);

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.08 : 0.92;
    handleZoom(factor);
  };

  const handleTriggerCycle = async () => {
    try {
      setTriggering(true);
      setTriggerMsg(null);
      const res = await api.triggerCycle(true, 'Manual trigger from LangGraph Visualizer');
      setTriggerMsg(`Cycle triggered successfully (${res.status || 'dispatched'})`);
      setTimeout(() => loadGraphState(), 1000);
    } catch (err: any) {
      setTriggerMsg(`Trigger failed: ${err.message || String(err)}`);
    } finally {
      setTriggering(false);
      setTimeout(() => setTriggerMsg(null), 6000);
    }
  };

  const handleCopyPayload = () => {
    if (!selectedNode?.output_payload) return;
    navigator.clipboard.writeText(JSON.stringify(selectedNode.output_payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendSteer = async () => {
    if (!steerMessage.trim()) return;
    try {
      setSteerLoading(true);
      const symList = steerSymbols
        .split(',')
        .map(s => s.trim().toUpperCase())
        .filter(Boolean);
      await api.steer({
        message: steerMessage.trim(),
        mode: steerMode,
        symbols: symList.length > 0 ? symList : undefined,
      });
      setTriggerMsg(`Steer directive successfully dispatched (${steerMode})`);
      setShowSteerModal(false);
      setSteerMessage('');
      setSteerSymbols('');
    } catch (err: any) {
      alert(`Steer failed: ${err.message || String(err)}`);
    } finally {
      setSteerLoading(false);
    }
  };

  const selectedNode = graphData?.nodes.find((n: GraphNode) => n.id === selectedNodeId) || null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', height: '100%' }}>
      {/* 1. Header Toolbar */}
      <div
        className="win-window ledger-card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-paper-raised)',
          padding: '12px 16px',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
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
            <Workflow size={18} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{
                fontSize: 'var(--text-title-sm)',
                fontWeight: 800,
                margin: 0,
                color: 'var(--color-ink)',
                fontFamily: 'var(--font-precision)',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}>
                LANGGRAPH MULTI-AGENT PIPELINE
              </h2>
              {graphData && (
                <span
                  className="stamp-badge"
                  style={{
                    fontSize: '10px',
                    background: graphData.status === 'completed'
                      ? 'var(--color-profit-dim)'
                      : graphData.status === 'running'
                        ? 'var(--color-warn-dim)'
                        : 'var(--color-loss-dim)',
                    color: graphData.status === 'completed'
                      ? 'var(--color-ledger-green)'
                      : graphData.status === 'running'
                        ? 'var(--color-brass)'
                        : 'var(--color-ledger-red)',
                    border: `1.5px solid ${
                      graphData.status === 'completed'
                        ? 'var(--color-ledger-green)'
                        : graphData.status === 'running'
                          ? 'var(--color-brass)'
                          : 'var(--color-ledger-red)'
                    }`,
                  }}
                >
                  [{(graphData.status?.toUpperCase() || 'IDLE')}]
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 4 }}>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>
                EXECUTION CYCLE:
              </span>
              <select
                value={selectedCycle}
                onChange={(e) => setSelectedCycle(e.target.value)}
                style={{
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  color: 'var(--color-ink)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '3px 8px',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-precision)',
                  cursor: 'pointer',
                  outline: 'none',
                }}
              >
                {(graphData?.available_cycles || []).map((c: CycleItem) => (
                  <option key={c.cycle_id} value={c.cycle_id}>
                    {c.label || c.cycle_id} ({c.status})
                  </option>
                ))}
              </select>
              {loading && <Loader2 size={13} color="var(--color-brass)" style={{ animation: 'spin 1s linear infinite' }} />}
            </div>
          </div>
        </div>

        {/* Telemetry Summary Badges */}
        {graphData && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              padding: '4px 10px',
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
            }}>
              <span style={{ fontSize: '9px', color: 'var(--color-ink-soft)', textTransform: 'uppercase', fontWeight: 'bold' }}>DURATION</span>
              <span className="tabular-nums" style={{ fontSize: 'var(--text-body-sm)', fontWeight: 800, fontFamily: 'var(--font-precision)', color: 'var(--color-ink)' }}>
                {((graphData.total_duration_ms ?? 0) / 1000).toFixed(2)}s
              </span>
            </div>

            <div style={{
              display: 'flex',
              flexDirection: 'column',
              padding: '4px 10px',
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
            }}>
              <span style={{ fontSize: '9px', color: 'var(--color-ink-soft)', textTransform: 'uppercase', fontWeight: 'bold' }}>TOKENS</span>
              <span className="tabular-nums" style={{ fontSize: 'var(--text-body-sm)', fontWeight: 800, fontFamily: 'var(--font-precision)', color: 'var(--color-win-blue)' }}>
                {((graphData.total_tokens?.total ?? 0) / 1000).toFixed(1)}k
              </span>
            </div>

            <div style={{
              display: 'flex',
              flexDirection: 'column',
              padding: '4px 10px',
              background: 'var(--color-paper)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
            }}>
              <span style={{ fontSize: '9px', color: 'var(--color-ink-soft)', textTransform: 'uppercase', fontWeight: 'bold' }}>EST. COST</span>
              <span className="tabular-nums" style={{ fontSize: 'var(--text-body-sm)', fontWeight: 800, fontFamily: 'var(--font-precision)', color: 'var(--color-ledger-green)' }}>
                ${(graphData.total_tokens?.cost_usd ?? 0).toFixed(4)}
              </span>
            </div>
          </div>
        )}

        {/* Viewport controls & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => setShowSteerModal(true)}
            title="Inject operator directive into current or next cycle"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 12px',
              background: 'var(--color-surface)',
              color: 'var(--color-ink)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              fontWeight: 700,
              fontSize: 'var(--text-xs)',
              cursor: 'pointer',
              boxShadow: '1.5px 1.5px 0 var(--color-rule)',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <Compass size={14} color="var(--color-brass)" />
            <span>[ STEER DIRECTIVE ]</span>
          </button>
          <GraphControls
            onZoom={handleZoom}
            onFitScreen={handleFitScreen}
            onReset={handleReset}
            onTriggerCycle={handleTriggerCycle}
            triggering={triggering}
          />
        </div>
      </div>

      {triggerMsg && (
        <div
          className="win-window"
          style={{
            padding: '8px 14px',
            borderRadius: 'var(--radius-card)',
            background: 'var(--color-paper-raised)',
            border: '2px solid var(--color-win-yellow)',
            boxShadow: 'var(--shadow-card)',
            color: 'var(--color-ink)',
            fontSize: 'var(--text-body-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--font-precision)',
          }}
        >
          <Sparkles size={16} color="var(--color-brass)" />
          {triggerMsg}
        </div>
      )}

      {/* 2. Main Content: Interactive SVG Canvas + Side Inspector */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: selectedNode ? '1fr 380px' : '1fr',
        gap: '16px',
        height: '680px',
        transition: 'all 0.2s ease-out',
      }}>
        {/* Canvas Card */}
        <div
          ref={containerRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => setIsPanning(false)}
          onWheel={handleWheel}
          className="win-window console-scanline"
          style={{
            position: 'relative',
            background: 'var(--color-console-bg)',
            border: '2px solid var(--color-rule)',
            borderRadius: 'var(--radius-card)',
            boxShadow: 'var(--shadow-card)',
            overflow: 'hidden',
            cursor: isPanning ? 'grabbing' : 'grab',
            userSelect: 'none',
          }}
        >
          {/* Subtle grid background pattern */}
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `
              radial-gradient(circle, rgba(232, 185, 74, 0.08) 1px, transparent 1px)
            `,
            backgroundSize: '24px 24px',
            pointerEvents: 'none',
          }} />

          {/* Canvas SVG */}
          <svg
            width="100%"
            height="100%"
            style={{ display: 'block', overflow: 'visible' }}
          >
            <defs>
              <marker
                id="arrow-done"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#2D5A27" />
              </marker>
              <marker
                id="arrow-running"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#C49A45" />
              </marker>
              <marker
                id="arrow-pending"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#6C6558" />
              </marker>
            </defs>

            {/* Root SVG Transform Group */}
            <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
              {/* Subgraph container box: Per-Asset Subgraph */}
              <rect
                x="600"
                y="60"
                width="590"
                height="510"
                rx="2"
                fill="var(--color-surface)"
                stroke="var(--color-brass)"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
              <text
                x="620"
                y="92"
                fill="var(--color-brass)"
                fontSize="12"
                fontWeight="700"
                letterSpacing="0.08em"
                fontFamily="var(--font-precision)"
              >
                [ SUBGRAPH: PER-ASSET DIALECTIC ARBITRATION (BULL / BEAR / SYNTHESIS) ]
              </text>

              {/* Edge Bezier Connectors */}
              {graphData?.edges.map((edge, idx) => {
                const srcPos = NODE_POSITIONS[edge.from];
                const dstPos = NODE_POSITIONS[edge.to];
                if (!srcPos || !dstPos) return null;

                const srcNode = graphData.nodes.find(n => n.id === edge.from);
                const dstNode = graphData.nodes.find(n => n.id === edge.to);

                return (
                  <GraphEdge
                    key={`${edge.from}-${edge.to}-${idx}`}
                    fromId={edge.from}
                    toId={edge.to}
                    srcPos={srcPos}
                    dstPos={dstPos}
                    srcNode={srcNode}
                    dstNode={dstNode}
                    nodeWidth={NODE_WIDTH}
                    nodeHeight={NODE_HEIGHT}
                  />
                );
              })}

              {/* Interactive Graph Nodes */}
              {graphData?.nodes.map((node: GraphNode) => {
                const pos = NODE_POSITIONS[node.id] || { x: 100, y: 100 };
                const isSelected = selectedNodeId === node.id;

                return (
                  <GraphNodeComponent
                    key={node.id}
                    node={node}
                    isSelected={isSelected}
                    onSelect={setSelectedNodeId}
                    pos={pos}
                    nodeWidth={NODE_WIDTH}
                    nodeHeight={NODE_HEIGHT}
                  />
                );
              })}
            </g>
          </svg>

          {/* Minimap / Legend Badge */}
          <div style={{
            position: 'absolute',
            bottom: 16,
            left: 16,
            background: 'var(--color-paper-raised)',
            border: '1.5px solid var(--color-rule)',
            borderRadius: 'var(--radius-sm)',
            boxShadow: '1.5px 1.5px 0 var(--color-rule)',
            padding: '6px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            fontSize: 'var(--text-caption)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-precision)',
            pointerEvents: 'none',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 6, height: 6, borderRadius: '1px', background: 'var(--color-profit)' }} />
              <span>[ COMPLETED ]</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 6, height: 6, borderRadius: '1px', background: 'var(--color-brass)' }} />
              <span>[ RUNNING ]</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 6, height: 6, borderRadius: '1px', background: 'var(--color-loss)' }} />
              <span>[ FAILED ]</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 6, height: 6, borderRadius: '1px', background: 'var(--color-ink-muted)' }} />
              <span>[ PENDING ]</span>
            </div>
          </div>
        </div>

        {/* 3. Side Inspector Drawer */}
        {selectedNode && (
          <GraphInspector
            selectedNode={selectedNode}
            onClose={() => setSelectedNodeId(null)}
            copied={copied}
            onCopyPayload={handleCopyPayload}
          />
        )}
      </div>

      {showSteerModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowSteerModal(false)}
        >
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
              width: '520px',
              maxWidth: '90vw',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--color-rule)', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Compass size={18} color="var(--color-brass)" />
                <span style={{ fontSize: 'var(--text-body)', fontWeight: 800, fontFamily: 'var(--font-precision)', textTransform: 'uppercase' }}>
                  OPERATOR STEER DIRECTIVE
                </span>
              </div>
              <button
                onClick={() => setShowSteerModal(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--color-ink-muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-muted)', textTransform: 'uppercase' }}>
                Directive Instruction / Message
              </label>
              <textarea
                value={steerMessage}
                onChange={e => setSteerMessage(e.target.value)}
                placeholder="e.g. Prioritize risk containment on EURUSD. Invalidate bullish confluence if DXY breaks above 104.50."
                rows={4}
                style={{
                  width: '100%',
                  background: 'var(--color-paper)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px',
                  color: 'var(--color-ink)',
                  fontSize: 'var(--text-body-sm)',
                  fontFamily: 'var(--font-precision)',
                  resize: 'vertical',
                  outline: 'none',
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-muted)', textTransform: 'uppercase' }}>
                  Delivery Mode
                </label>
                <select
                  value={steerMode}
                  onChange={e => setSteerMode(e.target.value)}
                  style={{
                    background: 'var(--color-paper)',
                    border: '1.5px solid var(--color-rule)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px',
                    color: 'var(--color-ink)',
                    fontSize: 'var(--text-body-sm)',
                    fontFamily: 'var(--font-precision)',
                    outline: 'none',
                  }}
                >
                  <option value="steer">steer (Cycle State Injection)</option>
                  <option value="follow_up">follow_up (Direct Agent Follow-up)</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-muted)', textTransform: 'uppercase' }}>
                  Symbols (Optional comma-sep)
                </label>
                <input
                  type="text"
                  value={steerSymbols}
                  onChange={e => setSteerSymbols(e.target.value)}
                  placeholder="EURUSD, XAUUSD"
                  style={{
                    background: 'var(--color-paper)',
                    border: '1.5px solid var(--color-rule)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 10px',
                    color: 'var(--color-ink)',
                    fontSize: 'var(--text-body-sm)',
                    fontFamily: 'var(--font-precision)',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
              <button
                onClick={() => setShowSteerModal(false)}
                style={{
                  padding: '8px 16px',
                  background: 'transparent',
                  border: '1px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-body-sm)',
                  cursor: 'pointer',
                  color: 'var(--color-ink)',
                  fontFamily: 'var(--font-precision)',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSendSteer}
                disabled={steerLoading || !steerMessage.trim()}
                style={{
                  padding: '8px 20px',
                  background: 'var(--color-brass)',
                  border: '1.5px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-body-sm)',
                  fontWeight: 'bold',
                  cursor: steerLoading || !steerMessage.trim() ? 'not-allowed' : 'pointer',
                  color: '#000',
                  fontFamily: 'var(--font-precision)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  opacity: steerLoading || !steerMessage.trim() ? 0.6 : 1,
                }}
              >
                {steerLoading ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={14} />}
                <span>Dispatch Steer</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

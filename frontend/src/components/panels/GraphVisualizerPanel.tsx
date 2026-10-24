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
import { computeGraphLayout, COMPACT_POSITIONS, WIDE_POSITIONS } from './graph/graphUtils';

// Visual canvas dimensions & node geometry
const NODE_WIDTH = 220;
const NODE_HEIGHT = 120;

export const GraphVisualizerPanel: React.FC = () => {
  const [graphData, setGraphData] = useState<GraphStateResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedCycle, setSelectedCycle] = useState<string>('');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [layoutMode, setLayoutMode] = useState<'compact' | 'wide'>('compact');
  const [autoFit, setAutoFit] = useState<boolean>(true);

  const nodePositions = React.useMemo(() => {
    if (!graphData) return layoutMode === 'compact' ? COMPACT_POSITIONS : WIDE_POSITIONS;
    return computeGraphLayout(graphData.nodes, graphData.edges, layoutMode);
  }, [graphData, layoutMode]);
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

  // Cycle Telemetry & Token Cost State
  const [cycleTrace, setCycleTrace] = useState<any | null>(null);
  const [cycleTokens, setCycleTokens] = useState<any | null>(null);

  // Viewport transform state: scale and translation
  const [transform, setTransform] = useState<{ x: number; y: number; k: number }>({
    x: 40,
    y: 30,
    k: 0.85,
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

  // Dynamic Auto-Fit calculation
  const fitGraphToContainer = useCallback((mode: 'compact' | 'wide' = layoutMode) => {
    if (!containerRef.current) return;
    const containerWidth = containerRef.current.clientWidth;
    const containerHeight = containerRef.current.clientHeight;
    if (!containerWidth || !containerHeight) return;

    const positions = Object.values(
      graphData
        ? computeGraphLayout(graphData.nodes, graphData.edges, mode)
        : (mode === 'compact' ? COMPACT_POSITIONS : WIDE_POSITIONS)
    );
    if (positions.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    positions.forEach(p => {
      if (p.x < minX) minX = p.x;
      if (p.x + NODE_WIDTH > maxX) maxX = p.x + NODE_WIDTH;
      if (p.y < minY) minY = p.y;
      if (p.y + NODE_HEIGHT > maxY) maxY = p.y + NODE_HEIGHT;
    });

    if (mode === 'compact') {
      minX = Math.min(minX, 40);
      minY = Math.min(minY, 50);
      maxX = Math.max(maxX, 1275);
      maxY = Math.max(maxY, 550);
    }

    const padding = 28;
    const graphWidth = (maxX - minX) + padding * 2;
    const graphHeight = (maxY - minY) + padding * 2;

    const scaleX = containerWidth / graphWidth;
    const scaleY = containerHeight / graphHeight;
    const optimalScale = Math.min(scaleX, scaleY, 1.15);
    const clampedScale = Math.max(optimalScale, 0.35);

    const scaledGraphWidth = (maxX - minX) * clampedScale;
    const scaledGraphHeight = (maxY - minY) * clampedScale;
    const offsetX = (containerWidth - scaledGraphWidth) / 2 - minX * clampedScale;
    const offsetY = (containerHeight - scaledGraphHeight) / 2 - minY * clampedScale;

    setTransform({
      x: Math.round(offsetX),
      y: Math.round(offsetY),
      k: Number(clampedScale.toFixed(3)),
    });
  }, [graphData, layoutMode]);

  // Load graph state from backend
  const loadGraphState = useCallback(async (cycleId?: string, symbol?: string, isBackground: boolean = false) => {
    try {
      if (!isBackground) setLoading(true);
      const [res, traceRes, tokensRes] = await Promise.all([
        api.graphState(cycleId, symbol || undefined),
        cycleId ? api.cycleTraceSummary(cycleId).catch(() => null) : Promise.resolve(null),
        api.tokenCycles(cycleId).catch(() => null),
      ]);
      setGraphData(res);
      setCycleTrace(traceRes);
      setCycleTokens(tokensRes);
      lastFetchedCycleRef.current = res.cycle_id;
      if (res.cycle_id && res.cycle_id !== selectedCycle) {
        setSelectedCycle(res.cycle_id);
      }
      setSelectedNodeId(curr => curr || (res.nodes && res.nodes.length > 0 ? res.nodes[0].id : null));
    } catch (err) {
      console.error('Failed to load graph state:', err);
    } finally {
      if (!isBackground) setLoading(false);
    }
  }, [selectedCycle]);

  useEffect(() => {
    loadGraphState(selectedCycle || undefined, selectedSymbol || undefined, false);
  }, [selectedCycle, selectedSymbol, loadGraphState]);

  // Polling fallback without loading flash
  useEffect(() => {
    const interval = setInterval(() => {
      loadGraphState(selectedCycle || undefined, selectedSymbol || undefined, true);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedCycle, selectedSymbol, loadGraphState]);

  // Auto-fit on resize (window resize, sidebar toggle, or inspector open/close)
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => {
      if (autoFit) {
        fitGraphToContainer();
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [autoFit, fitGraphToContainer]);

  // Auto-fit when graphData arrives
  useEffect(() => {
    if (autoFit && graphData) {
      const timer = setTimeout(() => {
        fitGraphToContainer();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [graphData, autoFit, fitGraphToContainer]);

  // Viewport zoom & pan handlers
  const handleZoom = (factor: number) => {
    setAutoFit(false);
    setTransform(curr => ({
      ...curr,
      k: Math.min(Math.max(curr.k * factor, 0.35), 2.2),
    }));
  };

  const handleReset = () => {
    setAutoFit(false);
    setTransform({ x: 40, y: 20, k: 0.85 });
  };

  const handleToggleAutoFit = () => {
    const next = !autoFit;
    setAutoFit(next);
    if (next) {
      fitGraphToContainer();
    }
  };

  const handleLayoutModeChange = (mode: 'compact' | 'wide') => {
    setLayoutMode(mode);
    if (autoFit) {
      fitGraphToContainer(mode);
    }
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
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      setAutoFit(false);
    }
    setTransform(curr => ({
      ...curr,
      x: panStartRef.current.initX + dx,
      y: panStartRef.current.initY + dy,
    }));
  };

  const handleMouseUp = () => setIsPanning(false);

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', height: '100%' }}>
      {/* 1. Architectural Header Toolbar */}
      <div
        className="editorial-section swiss-crosshair"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--color-paper-raised)',
          padding: '14px 18px',
          border: '1px solid var(--color-rule)',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="editorial-kicker">I. ARCHITECTURAL TOPOLOGY</span>
            {graphData && (
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 600,
                  padding: '1px 6px',
                  letterSpacing: '0.06em',
                  color: graphData.status === 'completed'
                    ? 'var(--color-ledger-green)'
                    : graphData.status === 'running'
                      ? 'var(--color-brass)'
                      : 'var(--color-ink-muted)',
                  border: `1px solid ${
                    graphData.status === 'completed'
                      ? 'var(--color-ledger-green)'
                      : graphData.status === 'running'
                        ? 'var(--color-brass)'
                        : 'var(--color-rule)'
                  }`,
                }}
              >
                {graphData.status?.toUpperCase() || 'IDLE'}
              </span>
            )}
          </div>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '22px',
              fontWeight: 400,
              margin: '2px 0 0 0',
              color: 'var(--color-ink)',
            }}
          >
            LangGraph 5-Stage Architectural Pipeline
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 8, flexWrap: 'wrap' }}>
            <span className="editorial-kicker">CYCLE</span>
            <select
              value={selectedCycle}
              onChange={(e) => setSelectedCycle(e.target.value)}
              style={{
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
                color: 'var(--color-ink)',
                padding: '3px 8px',
                fontSize: '11px',
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

            <span className="editorial-kicker" style={{ marginLeft: '6px' }}>INSTRUMENT</span>
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              style={{
                background: 'var(--color-paper)',
                border: '1px solid var(--color-rule)',
                color: 'var(--color-ink)',
                padding: '3px 8px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="">ALL ASSETS (AGGREGATE)</option>
              {(graphData?.available_symbols || []).map((sym: string) => (
                <option key={sym} value={sym}>
                  {sym}
                </option>
              ))}
            </select>

            {loading && <Loader2 size={13} color="var(--color-ink-muted)" style={{ animation: 'spin 1s linear infinite' }} />}
          </div>
        </div>

        {/* Telemetry Summary Hairline Strip */}
        {graphData && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid var(--color-rule)',
              background: 'var(--color-paper)',
            }}
          >
            <div style={{ padding: '6px 12px', borderRight: '1px solid var(--color-rule)' }}>
              <span className="editorial-kicker" style={{ display: 'block' }}>DURATION</span>
              <span className="tabular-nums" style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-precision)', color: 'var(--color-ink)' }}>
                {((graphData.total_duration_ms ?? 0) / 1000).toFixed(2)}s
              </span>
            </div>

            <div style={{ padding: '6px 12px', borderRight: '1px solid var(--color-rule)' }}>
              <span className="editorial-kicker" style={{ display: 'block' }}>TOKENS</span>
              <span className="tabular-nums" style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-precision)', color: 'var(--color-ink)' }}>
                {((graphData.total_tokens?.total ?? 0) / 1000).toFixed(1)}k
              </span>
            </div>

            <div style={{ padding: '6px 12px' }}>
              <span className="editorial-kicker" style={{ display: 'block' }}>EST. COST</span>
              <span className="tabular-nums" style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-precision)', color: 'var(--color-ledger-green)' }}>
                ${(graphData.total_tokens?.cost_usd ?? 0).toFixed(4)}
              </span>
            </div>
          </div>
        )}

        {/* Viewport controls & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => setShowSteerModal(true)}
            title="Inject operator directive into current or next cycle"
            className="editorial-btn editorial-btn--ghost"
          >
            <Compass size={13} />
            <span>STEER DIRECTIVE</span>
          </button>
          <GraphControls
            onZoom={handleZoom}
            onReset={handleReset}
            onTriggerCycle={handleTriggerCycle}
            triggering={triggering}
            layoutMode={layoutMode}
            onChangeLayoutMode={handleLayoutModeChange}
            autoFit={autoFit}
            onToggleAutoFit={handleToggleAutoFit}
          />
        </div>
      </div>

      {triggerMsg && (
        <div
          style={{
            padding: '8px 14px',
            background: 'var(--color-paper-raised)',
            border: '1px solid var(--color-rule-strong)',
            color: 'var(--color-ink)',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--font-precision)',
          }}
        >
          <Sparkles size={14} color="var(--color-accent)" />
          {triggerMsg}
        </div>
      )}

      {/* 2. Main Content: Interactive SVG Architectural Schematic + Side Inspector */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: selectedNode ? '1fr 380px' : '1fr',
          gap: '14px',
          height: '680px',
          transition: 'all 0.2s ease-out',
        }}
      >
        {/* Architectural Drafting Canvas */}
        <div
          ref={containerRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => setIsPanning(false)}
          className="editorial-section swiss-crosshair dag-drafting-canvas"
          style={{
            position: 'relative',
            background: 'var(--color-paper)',
            border: '1px solid var(--color-rule)',
            overflow: 'hidden',
            cursor: isPanning ? 'grabbing' : (autoFit ? 'default' : 'grab'),
            userSelect: 'none',
          }}
        >
          {/* Architectural drafting grid background pattern */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: 'radial-gradient(circle, var(--color-dag-grid) 1px, transparent 1px)',
              backgroundSize: '24px 24px',
              pointerEvents: 'none',
            }}
          />

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
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--color-ledger-green)" />
              </marker>
              <marker
                id="arrow-running"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--color-brass)" />
              </marker>
              <marker
                id="arrow-pending"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--color-ink-soft)" opacity="0.6" />
              </marker>
              <marker
                id="arrow-skipped"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--color-ink-muted)" opacity="0.5" />
              </marker>
            </defs>

            {/* Root SVG Transform Group */}
            <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
              {/* Subgraph Zone III: Dialectic Arbitration */}
              {graphData && graphData.nodes && graphData.nodes.length > 0 && (
                <>
                  <rect
                    x={layoutMode === 'compact' ? '515' : '865'}
                    y={layoutMode === 'compact' ? '45' : '75'}
                    width={layoutMode === 'compact' ? '495' : '555'}
                    height={layoutMode === 'compact' ? '400' : '440'}
                    rx="0"
                    fill="var(--color-subgraph-bg)"
                    stroke="var(--color-rule-strong)"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={layoutMode === 'compact' ? '528' : '878'}
                    y={layoutMode === 'compact' ? '64' : '96'}
                    fill="var(--color-ink-muted)"
                    fontSize="10"
                    fontWeight="600"
                    letterSpacing="0.12em"
                    fontFamily="var(--font-precision)"
                  >
                    STAGE III — DIALECTIC ARBITRATION (BULL / BEAR / JUDGE)
                  </text>
                </>
              )}

              {/* Subgraph Zone IV & V: Fortress & Execution Waterfall (compact mode) */}
              {graphData && graphData.nodes && graphData.nodes.length > 0 && layoutMode === 'compact' && (
                <>
                  <rect
                    x="1025"
                    y="45"
                    width="255"
                    height="505"
                    rx="0"
                    fill="transparent"
                    stroke="var(--color-rule-strong)"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                  <text
                    x="1038"
                    y="64"
                    fill="var(--color-ink-muted)"
                    fontSize="10"
                    fontWeight="600"
                    letterSpacing="0.12em"
                    fontFamily="var(--font-precision)"
                  >
                    STAGE IV–V — FORTRESS & EXECUTION
                  </text>
                </>
              )}

              {/* Edge Bezier Connectors */}
              {graphData?.edges.map((edge, idx) => {
                const srcPos = nodePositions[edge.from];
                const dstPos = nodePositions[edge.to];
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
                const pos = nodePositions[node.id] || { x: 100, y: 100 };
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

          {/* Idle Empty State Overlay */}
          {(!graphData?.nodes || graphData.nodes.length === 0) && !loading && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                color: 'var(--color-ink-muted)',
                pointerEvents: 'none',
              }}
            >
              <Workflow size={28} color="var(--color-ink-muted)" />
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '20px', color: 'var(--color-ink)' }}>
                No Active Pipeline Cycle
              </div>
              <div style={{ fontSize: '12px', maxWidth: '340px', textAlign: 'center', lineHeight: 1.5 }}>
                The trading pipeline is currently idle. Trigger a manual cycle above or wait for the next scheduled 8-hour graph run.
              </div>
            </div>
          )}

          {/* Architectural Legend Hairline Strip */}
          <div
            style={{
              position: 'absolute',
              bottom: 14,
              left: 14,
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              padding: '6px 12px',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              fontSize: '11px',
              letterSpacing: '0.08em',
              color: 'var(--color-ink-soft)',
              fontFamily: 'var(--font-precision)',
              pointerEvents: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 6, height: 6, background: 'var(--color-profit)' }} />
              <span>COMPLETED</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 6, height: 6, background: 'var(--color-brass)' }} />
              <span>RUNNING</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 6, height: 6, background: 'var(--color-loss)' }} />
              <span>FAILED</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <span style={{ width: 6, height: 6, background: 'var(--color-ink-muted)' }} />
              <span>PENDING</span>
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
            cycleTrace={cycleTrace}
            cycleTokens={cycleTokens}
          />
        )}
      </div>

      {showSteerModal && (
        <div
          className="retro-modal-scrim"
          style={{ zIndex: 1000 }}
          onClick={() => setShowSteerModal(false)}
        >
          <div
            className="editorial-section swiss-crosshair"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule-strong)',
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
              <div>
                <div className="editorial-kicker">OPERATOR OVERRIDE</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: '20px', color: 'var(--color-ink)', marginTop: '2px' }}>
                  Steer Pipeline Directive
                </div>
              </div>
              <button
                onClick={() => setShowSteerModal(false)}
                className="editorial-btn editorial-btn--ghost"
                style={{ padding: '4px 8px' }}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label className="editorial-kicker">
                DIRECTIVE INSTRUCTION / MESSAGE
              </label>
              <textarea
                value={steerMessage}
                onChange={e => setSteerMessage(e.target.value)}
                placeholder="e.g. Prioritize risk containment on EURUSD. Invalidate bullish confluence if DXY breaks above 104.50."
                rows={4}
                style={{
                  width: '100%',
                  background: 'var(--color-paper)',
                  border: '1px solid var(--color-rule)',
                  padding: '10px',
                  color: 'var(--color-ink)',
                  fontSize: '12px',
                  fontFamily: 'var(--font-precision)',
                  resize: 'vertical',
                  outline: 'none',
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label className="editorial-kicker">
                  DELIVERY MODE
                </label>
                <select
                  value={steerMode}
                  onChange={e => setSteerMode(e.target.value)}
                  style={{
                    background: 'var(--color-paper)',
                    border: '1px solid var(--color-rule)',
                    padding: '8px',
                    color: 'var(--color-ink)',
                    fontSize: '12px',
                    fontFamily: 'var(--font-precision)',
                    outline: 'none',
                  }}
                >
                  <option value="steer">steer (Cycle State Injection)</option>
                  <option value="follow_up">follow_up (Direct Agent Follow-up)</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label className="editorial-kicker">
                  SYMBOLS (OPTIONAL COMMA-SEP)
                </label>
                <input
                  type="text"
                  value={steerSymbols}
                  onChange={e => setSteerSymbols(e.target.value)}
                  placeholder="EURUSD, XAUUSD"
                  style={{
                    background: 'var(--color-paper)',
                    border: '1px solid var(--color-rule)',
                    padding: '8px 10px',
                    color: 'var(--color-ink)',
                    fontSize: '12px',
                    fontFamily: 'var(--font-precision)',
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
              <button
                onClick={() => setShowSteerModal(false)}
                className="editorial-btn editorial-btn--ghost"
              >
                CANCEL
              </button>
              <button
                onClick={handleSendSteer}
                disabled={steerLoading || !steerMessage.trim()}
                className="editorial-btn editorial-btn--accent"
              >
                {steerLoading ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={13} />}
                <span>DISPATCH STEER</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

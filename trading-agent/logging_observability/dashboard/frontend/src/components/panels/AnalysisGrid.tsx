import React, { useState } from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { MagnifierDeskIcon } from '../ui/Icons';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { DecisionDossierModal } from './DecisionDossierModal';

export const AnalysisGrid: React.FC = () => {
  const { analyses, loading, setSelectedSymbol } = useDashboardStore();
  const [dossierTarget, setDossierTarget] = useState<any | null>(null);
  const [viewMode, setViewMode] = useState<'unique' | 'all'>('unique');

  // Deduplicate by symbol keeping newest
  const displayAnalyses = React.useMemo(() => {
    if (viewMode === 'all') return analyses;
    const map = new Map<string, any>();
    for (const item of analyses) {
      if (!map.has(item.symbol)) {
        map.set(item.symbol, item);
      } else {
        const existing = map.get(item.symbol);
        const existingTime = existing.generated_at ? new Date(existing.generated_at).getTime() : 0;
        const itemTime = item.generated_at ? new Date(item.generated_at).getTime() : 0;
        if (itemTime > existingTime) {
          map.set(item.symbol, item);
        }
      }
    }
    return Array.from(map.values());
  }, [analyses, viewMode]);

  return (
    <WindowFrame
      title="MARKET INTELLIGENCE DISPATCHES"
      icon={<MagnifierDeskIcon size={18} color="var(--color-titlebar-text)" />}
      variant="salmon"
      toolbar={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '8px' }}>
          <div style={{ display: 'inline-flex', border: '1.5px solid var(--color-rule)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', boxShadow: '1px 1px 0 var(--color-rule)' }}>
            <button
              type="button"
              onClick={() => setViewMode('unique')}
              style={{
                padding: '3px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: viewMode === 'unique' ? 700 : 500,
                background: viewMode === 'unique' ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: viewMode === 'unique' ? '#1C1917' : 'var(--color-ink-soft)',
                border: 'none',
                borderRight: '1.5px solid var(--color-rule)',
                cursor: 'pointer',
              }}
            >
              LATEST PER SYMBOL
            </button>
            <button
              type="button"
              onClick={() => setViewMode('all')}
              style={{
                padding: '3px 10px',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-precision)',
                fontWeight: viewMode === 'all' ? 700 : 500,
                background: viewMode === 'all' ? 'var(--color-win-yellow)' : 'var(--color-paper-raised)',
                color: viewMode === 'all' ? '#1C1917' : 'var(--color-ink-soft)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              ALL DISPATCHES ({analyses.length})
            </button>
          </div>

          <Badge variant="neutral">
            {displayAnalyses.length} SYMBOLS ACTIVE
          </Badge>
        </div>
      }
      padding="14px"
    >
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="ledger-card" style={{ padding: '16px' }}>
              <Skeleton height="20px" width="40%" />
              <div style={{ height: '10px' }} />
              <Skeleton height="14px" />
              <div style={{ height: '6px' }} />
              <Skeleton height="14px" width="80%" />
            </div>
          ))}
        </div>
      ) : displayAnalyses.length === 0 ? (
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>
          — No market intelligence dispatches archived —
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {displayAnalyses.map((a) => (
            <AnalysisCard
              key={a.id}
              analysis={a}
              onClick={() => setSelectedSymbol(a.symbol)}
              onDossierClick={(target) => setDossierTarget(target)}
            />
          ))}
        </div>
      )}

      {/* Decision Dossier Modal */}
      <DecisionDossierModal
        isOpen={Boolean(dossierTarget)}
        onClose={() => setDossierTarget(null)}
        analysisId={dossierTarget?.id}
        symbol={dossierTarget?.symbol}
      />
    </WindowFrame>
  );
};

const AnalysisCard: React.FC<{
  analysis: any;
  onClick: () => void;
  onDossierClick: (analysis: any) => void;
}> = ({ analysis, onClick, onDossierClick }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const rawConf = analysis.confidence;
  const conf = rawConf !== null && rawConf !== undefined
    ? (rawConf <= 1 && rawConf > 0 ? rawConf * 100 : rawConf)
    : null;
  const confColor = conf !== null && conf >= 80 ? 'var(--color-ledger-green)' : conf !== null && conf >= 60 ? 'var(--color-brass)' : 'var(--color-ink-soft)';
  const isStale = analysis.generated_at ? (Date.now() - new Date(analysis.generated_at).getTime() > 12 * 3600 * 1000) : false;

  return (
    <div
      className="ledger-card"
      onClick={onClick}
      style={{
        padding: '16px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        height: '100%',
        fontFamily: 'var(--font-precision)',
        opacity: isStale ? 0.82 : 1,
        background: isStale ? 'color-mix(in srgb, var(--color-paper-raised) 94%, var(--color-ink))' : 'var(--color-paper-raised)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 'bold', fontSize: 'var(--text-title-sm)', color: 'var(--color-ink)' }}>
            {analysis.symbol}
          </span>
          {isStale && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 5px',
                border: '1px dashed var(--color-text-warn)',
                color: 'var(--color-text-warn)',
                borderRadius: '2px',
                fontWeight: 800,
              }}
              title="Signal is older than 12 hours"
            >
              STALE
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Badge variant={(analysis.decision || 'wait') as any}>
            {(analysis.decision || 'WAIT').toUpperCase()}
          </Badge>
          {conf !== null && (
            <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: confColor }}>
              {conf.toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      <div>
        <p
          style={{
            fontSize: 'var(--text-body-sm)',
            color: 'var(--color-ink)',
            lineHeight: 1.5,
            margin: 0,
            ...(isExpanded ? {} : {
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }),
          }}
        >
          {analysis.rationale || 'No analytical rationale recorded.'}
        </p>
        {analysis.rationale && analysis.rationale.length > 100 && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            style={{
              background: 'none',
              border: 'none',
              padding: '4px 0 0 0',
              fontSize: '11px',
              fontFamily: 'var(--font-precision)',
              color: 'var(--color-win-blue)',
              cursor: 'pointer',
              textAlign: 'left',
              textDecoration: 'underline',
              fontWeight: 'bold',
            }}
          >
            {isExpanded ? '[COLLAPSE]' : '[EXPAND THESIS]'}
          </button>
        )}
      </div>

      {analysis.stop_loss || analysis.take_profit ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            marginTop: 'auto',
            paddingTop: '10px',
            borderTop: '1px solid var(--color-rule)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)' }} className="tabular-nums">
            <span style={{ color: 'var(--color-ledger-red)' }}>SL: {fmt.price(analysis.stop_loss, analysis.symbol)}</span>
            <span style={{ color: 'var(--color-ledger-green)' }}>TP: {fmt.price(analysis.take_profit, analysis.symbol)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
              {fmt.ago(analysis.generated_at)}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDossierClick(analysis);
              }}
              style={{
                padding: '2px 8px',
                fontSize: '11px',
                fontFamily: 'var(--font-precision)',
                fontWeight: 'bold',
                background: 'var(--color-paper)',
                color: 'var(--color-win-blue)',
                border: '1.5px solid var(--color-rule)',
                borderRadius: 'var(--radius-sm)',
                boxShadow: '1px 1px 0 var(--color-rule)',
                cursor: 'pointer',
              }}
              title="Inspect Decision Dossier (Why was this trade proposed?)"
            >
              🔍 DOSSIER
            </button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 'auto', paddingTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="tabular-nums" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            {fmt.ago(analysis.generated_at)}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDossierClick(analysis);
            }}
            style={{
              padding: '2px 8px',
              fontSize: '11px',
              fontFamily: 'var(--font-precision)',
              fontWeight: 'bold',
              background: 'var(--color-paper)',
              color: 'var(--color-win-blue)',
              border: '1.5px solid var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '1px 1px 0 var(--color-rule)',
              cursor: 'pointer',
            }}
            title="Inspect Decision Dossier (Why was this trade proposed?)"
          >
            🔍 DOSSIER
          </button>
        </div>
      )}
    </div>
  );
};

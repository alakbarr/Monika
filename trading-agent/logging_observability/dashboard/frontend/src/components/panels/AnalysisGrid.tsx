import React from 'react';
import { WindowFrame } from '../ui/WindowFrame';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { MagnifierDeskIcon } from '../ui/RetroIcons';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

export const AnalysisGrid: React.FC = () => {
  const { analyses, loading, setSelectedSymbol } = useDashboardStore();

  return (
    <WindowFrame
      title="LATEST MARKET INTELLIGENCE DISPATCHES"
      icon={<MagnifierDeskIcon size={18} color="var(--color-titlebar-text)" />}
      variant="salmon"
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
      ) : analyses.length === 0 ? (
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--color-ink-soft)', fontFamily: 'var(--font-precision)' }}>
          — No market intelligence dispatches archived —
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {analyses.map((a) => (
            <AnalysisCard key={a.id} analysis={a} onClick={() => setSelectedSymbol(a.symbol)} />
          ))}
        </div>
      )}
    </WindowFrame>
  );
};

const AnalysisCard: React.FC<{ analysis: any; onClick: () => void }> = ({ analysis, onClick }) => {
  const rawConf = analysis.confidence;
  const conf = rawConf !== null && rawConf !== undefined
    ? (rawConf <= 1 && rawConf > 0 ? rawConf * 100 : rawConf)
    : null;
  const confColor = conf !== null && conf >= 80 ? 'var(--color-ledger-green)' : conf !== null && conf >= 60 ? 'var(--color-brass)' : 'var(--color-ink-soft)';

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
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: 'bold', fontSize: 'var(--text-title-sm)', color: 'var(--color-ink)' }}>
            {analysis.symbol}
          </span>
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

      <p
        style={{
          fontSize: 'var(--text-body-sm)',
          color: 'var(--color-ink)',
          lineHeight: 1.5,
          margin: 0,
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {analysis.rationale || 'No analytical rationale recorded.'}
      </p>

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
          <div className="tabular-nums" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            {fmt.ago(analysis.generated_at)}
          </div>
        </div>
      ) : (
        <div className="tabular-nums" style={{ marginTop: 'auto', paddingTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
          {fmt.ago(analysis.generated_at)}
        </div>
      )}
    </div>
  );
};

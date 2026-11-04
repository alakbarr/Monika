// ==============================================================================
// File: src/components/charts/candlestick/ChartStatusBar.tsx
// Description: Status bar for SMC telemetry, order blocks, and AI model projections.
// ==============================================================================

import React from 'react';
import { Badge } from '../../ui/Badge';
import type { ActivePositionOverlay, AiProposalOverlay } from '../../../types/api';

interface ChartStatusBarProps {
  symbol: string;
  structureData: any;
  activePositions: ActivePositionOverlay[];
  latestAiProposal: AiProposalOverlay | null;
}

export const ChartStatusBar: React.FC<ChartStatusBarProps> = ({
  symbol,
  structureData,
  activePositions,
  latestAiProposal,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '8px',
        borderTop: '1px solid var(--color-border)',
        paddingTop: '8px',
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
        <span style={{ color: 'var(--color-ink-soft)', fontWeight: 700 }}>SMC TELEMETRY:</span>
        <Badge variant="neutral" size="sm">
          {structureData?.order_blocks?.length || 0} OBS
        </Badge>
        <Badge variant="neutral" size="sm">
          {structureData?.fair_value_gaps?.length || 0} FVGS
        </Badge>
        <Badge variant="neutral" size="sm">
          {structureData?.structure_breaks?.length || structureData?.breaks?.length || 0} BREAKS
        </Badge>
        {structureData?.liquidity_pools && (
          <Badge variant="neutral" size="sm">
            {structureData.liquidity_pools.length} LIQ POOLS
          </Badge>
        )}
        {structureData?.timesfm_cone && (
          <Badge variant="warn" size="sm">
            TIMESFM {structureData.timesfm_cone.drift >= 0 ? '▲ BULL' : '▼ BEAR'} (
            {((structureData.timesfm_cone.drift || 0) * 100).toFixed(2)}%)
          </Badge>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        {activePositions.filter((p) => p.symbol.toUpperCase() === symbol.toUpperCase()).length > 0 && (
          <Badge variant="profit" size="sm">
            {activePositions.filter((p) => p.symbol.toUpperCase() === symbol.toUpperCase()).length} POS ACTIVE
          </Badge>
        )}
        {latestAiProposal && latestAiProposal.symbol.toUpperCase() === symbol.toUpperCase() && (
          <Badge variant="warn" size="sm">
            AI {latestAiProposal.decision.toUpperCase()}
            {latestAiProposal.confidence ? ` (${(latestAiProposal.confidence * 100).toFixed(0)}%)` : ''}
          </Badge>
        )}
      </div>
    </div>
  );
};

-- Migration: Add SSVP context tracking fields
-- Run this ONCE after deploying new code

-- AssetAnalysis: context quality fields
ALTER TABLE asset_analysis 
    ADD COLUMN IF NOT EXISTS context_snapshot_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS brief_age_at_analysis_hours FLOAT,
    ADD COLUMN IF NOT EXISTS ssvp_cds_score_at_analysis FLOAT;

-- DecisionReflection: contamination tracking
ALTER TABLE decision_reflections
    ADD COLUMN IF NOT EXISTS context_cds_score FLOAT,
    ADD COLUMN IF NOT EXISTS context_snapshot_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS is_context_contaminated BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS contamination_reason VARCHAR(255);

-- Indexes untuk query performance
CREATE INDEX IF NOT EXISTS idx_asset_analysis_cds 
    ON asset_analysis(ssvp_cds_score_at_analysis) 
    WHERE ssvp_cds_score_at_analysis IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drefl_contaminated
    ON decision_reflections(is_context_contaminated, symbol);

CREATE INDEX IF NOT EXISTS idx_syscfg_ssvp
    ON system_config(key) WHERE key LIKE 'ssvp_cds_%';

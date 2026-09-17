-- Migration 002: Add Debate Columns to AssetAnalysis
ALTER TABLE asset_analysis ADD COLUMN debate_bull_thesis TEXT;
ALTER TABLE asset_analysis ADD COLUMN debate_bear_dissent TEXT;
ALTER TABLE asset_analysis ADD COLUMN debate_verdict VARCHAR(50);
ALTER TABLE asset_analysis ADD COLUMN debate_reason TEXT;

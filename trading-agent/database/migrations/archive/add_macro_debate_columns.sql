-- Add macro debate columns to fundamental_briefs
ALTER TABLE fundamental_briefs ADD COLUMN debate_bull_thesis TEXT;
ALTER TABLE fundamental_briefs ADD COLUMN debate_bear_thesis TEXT;
ALTER TABLE fundamental_briefs ADD COLUMN debate_winner VARCHAR(20);
ALTER TABLE fundamental_briefs ADD COLUMN debate_escalation_required BOOLEAN;

# ADR-004: Canonical SQLite Consolidation & External Runtime State Separation

## Status
Accepted

## Context
Multiple disparate SQLite databases (`trading_agent.db`, `universal_cron.db`, `monika.db.backup`, `monika.db.consolidated`) and ephemeral scratch files were scattered across the git-tracked python source tree (`src/monika/data/`, `src/monika/application/data/`), bloating repo size with over 2.3 GB of runtime churn and causing database locking conflicts.

## Decision
1. Consolidate operational storage into a single canonical SQLite database (`monika.db` in WAL mode) for desktop/single-instance mode, while supporting PostgreSQL for production deployments.
2. Relocate all runtime artifacts, logs, caches, and vault storage outside of source directories into `DATA_DIR` / `MONIKA_HOME`.
3. Eliminate all runtime state tracking in git via `.gitignore` rules.

## Consequences
- **Positive**: Clean working tree; zero git repository bloat from database commits; unified WAL connection pooling and zero cross-database locking conflicts.
- **Trade-offs**: Requires migration scripts (`scripts/migrate_sqlite_to_canonical.py`) for existing installations.

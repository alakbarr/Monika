---
name: database-analytics-and-reporting
description: "Direct SQL & Analytical Query Playbook: Schema inspection, safe read-only SQL queries, performance joins, debate transcript exports, and custom metric synthesis."
category: GENERAL
version: 1.0.0
platforms: [windows, linux, macos]
tags: [database, sql, postgresql, analytics, reporting, schema, query]
---

# Database Analytics & Structured Reporting Playbook

## 1. Overview & Data Schema Topology
Monika maintains a comprehensive relational database (PostgreSQL / SQLite) tracking market microstructure, trading decisions, risk evaluations, and execution records.

Key Tables:
- `trade_signals`: Generated AI trade opportunities with signal direction, confidence, and reasoning.
- `positions`: Real-time and historical MT5 positions, entry/exit prices, profit/loss, and commission.
- `asset_analyses`: Structured outputs from specialist agents with entry zones, stop losses, and take profits.
- `price_ohlcv`: Granular candlestick price data across multiple timeframes.
- `activity_logs`: Immutable audit trail of agent executions and system events.
- `risk_states`: Real-time risk gate tracking, daily drawdowns, and kill switch states.

## 2. Safety Guidelines for SQL Execution
1. **Read-Only Analytics**:
   - `SELECT` queries are freely executed via `query_database_sql` and `run_analytical_query`.
   - Complex aggregations (`GROUP BY`, `JOIN`, `HAVING`, window functions) are fully supported.
2. **Mutations Guardrail**:
   - Direct `UPDATE`, `INSERT`, or `DELETE` statements via `query_database_sql` are strictly blocked.
   - Any database mutation must be routed through `propose_action(action_type="db_mutation", ...)` with Admin privilege.
   - Immutable tables (`activity_logs`, `order_events`) cannot be mutated under any circumstances.

## 3. High-Frequency Analytical Query Patterns

### Win Rate by AI Confidence Decile
```sql
SELECT 
    ROUND(s.confidence, 1) AS conf_bucket,
    COUNT(*) AS total_trades,
    SUM(CASE WHEN p.pnl > 0 THEN 1 ELSE 0 END) AS wins,
    ROUND(SUM(CASE WHEN p.pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*), 3) AS win_rate,
    ROUND(AVG(p.pnl), 2) AS avg_pnl
FROM positions p
JOIN trade_signals s ON p.analysis_id = s.id
WHERE p.status = 'closed'
GROUP BY ROUND(s.confidence, 1)
ORDER BY conf_bucket DESC;
```

### Cumulative Slippage by Symbol
```sql
SELECT 
    symbol,
    COUNT(*) AS total_fills,
    ROUND(AVG(slippage_pips), 2) AS avg_slippage_pips,
    MAX(slippage_pips) AS max_slippage_pips
FROM order_logs
WHERE status = 'filled'
GROUP BY symbol
ORDER BY avg_slippage_pips DESC;
```

## 4. Analytical Tools in Monika
- `inspect_database_schema(table_name)`: Returns columns, data types, primary keys, and relationships.
- `query_database_sql(query, limit)`: Runs read-only SQL queries with automatic limit capping.
- `run_analytical_query(query_type, params)`: Runs pre-compiled institutional analytics (Sharpe, drawdown duration, edge decay).
- `export_dataset_file(table_name, format)`: Exports database records directly to CSV or Parquet for offline modeling.

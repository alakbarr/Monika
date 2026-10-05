# ==============================================================================
# File: analysis/tools/handlers/db_tools.py
# ==============================================================================

"""
Database inspection and query tool handlers for authorized Admin operator.
Provides schema discovery and bounded, read-only SELECT operations with
data masking and SQL injection immunity via SQLAlchemy ORM.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, date
from sqlalchemy import select, inspect, Integer, BigInteger
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Base
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool


def get_table_model_map() -> Dict[str, type]:
    """Return a mapping of table name -> SQLAlchemy declarative model class."""
    table_map = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        tablename = getattr(cls, "__tablename__", None)
        if tablename:
            table_map[tablename] = cls
    return table_map


def _serialize_row(row: Any, columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """Serialize an ORM row to a JSON-safe dictionary with sensitive values masked."""
    result: Dict[str, Any] = {}
    mapper = inspect(row.__class__)
    for col in mapper.columns:
        col_name = col.name
        if columns and col_name not in columns:
            continue
        val = getattr(row, col_name, None)
        # Datetime / date serialization
        if isinstance(val, (datetime, date)):
            val = val.isoformat()
        # Sensitive key masking
        lower_col = col_name.lower()
        if any(secret_kw in lower_col for secret_kw in ("password", "secret", "private_key")):
            val = "********"
        result[col_name] = val
    return result


import re
from sqlalchemy import text

TABLE_ALIASES = {
    "trade_signals": "mt5_signals",
    "signals": "mt5_signals",
    "paper_trades": "paper_trade_records",
    "paper_trade": "paper_trade_records",
    "paper_records": "paper_trade_records",
    "trades": "paper_trade_records",
    "position": "positions",
    "system_configs": "system_config",
    "risk_state": "system_config",
    "config": "system_config",
    "asset_analyses": "asset_analysis",
    "analyses": "asset_analysis",
    "reflections": "decision_reflections",
    "decision_reflection": "decision_reflections",
    "journal": "trader_journal_notes",
    "journal_notes": "trader_journal_notes",
}

FORBIDDEN_SQL_PATTERNS = [
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    r"\b(VACUUM|REINDEX|LOCK|SET|RESET)\b",
    r";\s*\S+",  # Multi-statement prevention
    r"--",        # SQL line comments (potential injection obfuscation)
    r"/\*.*?\*/", # SQL block comments
]


async def handle_inspect_database_schema(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Inspect database tables and column definitions. Admin only."""
    if executor is not None and not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "Akses Ditolak: Inspeksi database hanya diizinkan untuk Admin.",
            "is_admin": False,
        }

    table_map = get_table_model_map()
    raw_filter = args.get("table_name", "").strip().lower() if args.get("table_name") else None
    table_filter = TABLE_ALIASES.get(raw_filter, raw_filter) if raw_filter else None

    # Detailed inspection of single table
    if table_filter:
        if table_filter not in table_map:
            return {
                "status": "error",
                "error": f"Tabel '{table_filter}' tidak ditemukan dalam database schema.",
                "available_tables": sorted(list(table_map.keys())),
            }
        model_cls = table_map[table_filter]
        mapper = inspect(model_cls)
        cols_info = []
        for col in mapper.columns:
            cols_info.append({
                "name": col.name,
                "type": str(col.type),
                "primary_key": col.primary_key,
                "nullable": col.nullable,
                "default": str(col.default.arg) if col.default is not None else None,
            })
        return {
            "status": "success",
            "table": table_filter,
            "column_count": len(cols_info),
            "columns": cols_info,
        }

    # Summary overview of all tables
    summary = []
    for tablename in sorted(table_map.keys()):
        model_cls = table_map[tablename]
        mapper = inspect(model_cls)
        pks = [c.name for c in mapper.primary_key]
        col_names = [c.name for c in mapper.columns]
        summary.append({
            "table": tablename,
            "primary_key": pks,
            "column_count": len(col_names),
            "columns_preview": col_names[:6] + (["..."] if len(col_names) > 6 else []),
        })

    return {
        "status": "success",
        "total_tables": len(summary),
        "tables": summary,
    }


async def handle_read_database_records(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Query records from a specific table with filters and pagination. Admin only."""
    if executor is not None and not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "Akses Ditolak: Pembacaan data database hanya diizinkan untuk Admin.",
            "is_admin": False,
        }

    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "error": "Database session not available."}

    raw_table_name = str(args.get("table_name", "")).strip().lower()
    table_name = TABLE_ALIASES.get(raw_table_name, raw_table_name)
    table_map = get_table_model_map()

    if not table_name or table_name not in table_map:
        return {
            "status": "error",
            "error": f"Tabel '{table_name}' tidak valid. Gunakan 'inspect_database_schema' untuk melihat tabel yang tersedia.",
            "available_tables": sorted(list(table_map.keys())),
        }

    model_cls = table_map[table_name]
    query = select(model_cls)

    # 1. Apply equality and advanced filters safely (SQL injection proof via ORM binding)
    filters = args.get("filters") or {}
    if isinstance(filters, dict):
        for col_name, val in filters.items():
            # Translate column aliases if needed (e.g. pnl_usd on paper_trade_records)
            if col_name == "pnl_usd" and not hasattr(model_cls, "pnl_usd"):
                if hasattr(model_cls, "pnl_pct"):
                    col_name = "pnl_pct"
                    if isinstance(val, dict) and "gt" in val and float(val["gt"]) > 0:
                        val = {"gt": 0.0}
                elif hasattr(model_cls, "outcome_pnl_usd"):
                    col_name = "outcome_pnl_usd"
            elif col_name == "profit" and not hasattr(model_cls, "profit"):
                if hasattr(model_cls, "pnl_pct"):
                    col_name = "pnl_pct"

            if hasattr(model_cls, col_name):
                col_attr = getattr(model_cls, col_name)
                if val is None:
                    query = query.where(col_attr.is_(None))
                elif isinstance(val, dict):
                    # Advanced operators: is_null, search_text/ilike/like, gt, gte, lt, lte, neq, in
                    if "is_null" in val:
                        query = query.where(col_attr.is_(None) if val["is_null"] else col_attr.isnot(None))
                    if "search_text" in val or "ilike" in val:
                        txt = str(val.get("search_text") or val.get("ilike"))
                        query = query.where(col_attr.ilike(f"%{txt}%"))
                    if "like" in val:
                        query = query.where(col_attr.like(str(val["like"])))
                    if "gt" in val:
                        query = query.where(col_attr > val["gt"])
                    if "gte" in val:
                        query = query.where(col_attr >= val["gte"])
                    if "lt" in val:
                        query = query.where(col_attr < val["lt"])
                    if "lte" in val:
                        query = query.where(col_attr <= val["lte"])
                    if "neq" in val:
                        query = query.where(col_attr != val["neq"])
                    if "in" in val and isinstance(val["in"], (list, tuple)):
                        query = query.where(col_attr.in_(val["in"]))
                elif isinstance(val, (list, tuple)):
                    query = query.where(col_attr.in_(val))
                else:
                    query = query.where(col_attr == val)

    # 2. Sorting
    order_by = args.get("order_by")
    if order_by and isinstance(order_by, str):
        parts = order_by.strip().split()
        sort_col = parts[0]
        direction = parts[1].lower() if len(parts) > 1 else "asc"
        if hasattr(model_cls, sort_col):
            col_attr = getattr(model_cls, sort_col)
            query = query.order_by(col_attr.desc() if direction == "desc" else col_attr.asc())
    else:
        # Default order by primary key descending if exists
        mapper = inspect(model_cls)
        if mapper.primary_key:
            pk_col = mapper.primary_key[0]
            query = query.order_by(pk_col.desc())

    # 3. Bounded pagination (max 50 rows per turn to guard token budget)
    limit = min(max(int(args.get("limit") or 10), 1), 50)
    offset = max(int(args.get("offset") or 0), 0)
    query = query.limit(limit).offset(offset)

    # 4. Execute
    try:
        rows = (await effective_session.execute(query)).scalars().all()
        selected_cols = args.get("columns") if isinstance(args.get("columns"), list) else None
        serialized = [_serialize_row(r, columns=selected_cols) for r in rows]
        return {
            "status": "success",
            "table": table_name,
            "count": len(serialized),
            "limit": limit,
            "offset": offset,
            "records": serialized,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Gagal membaca data dari tabel '{table_name}': {str(e)}",
        }


async def handle_query_database_sql(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Execute a read-only SELECT SQL query with strict bounds and SQL injection/DDL protection. Admin only."""
    if executor is not None and not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "Akses Ditolak: Query database SQL hanya diizinkan untuk Admin.",
            "is_admin": False,
        }

    sql = str(args.get("sql") or args.get("query") or "").strip()
    if not sql:
        return {"status": "error", "error": "Parameter 'sql' query tidak boleh kosong."}

    # Remove trailing semicolon
    sql = sql.rstrip(";").strip()

    # 1. Enforce SELECT / CTE only
    if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
        return {
            "status": "error",
            "error": "Hanya query SELECT atau CTE (WITH) yang diizinkan demi keamanan database.",
        }

    # 2. Check forbidden modification keywords
    for pat in FORBIDDEN_SQL_PATTERNS:
        if re.search(pat, sql, re.IGNORECASE):
            return {
                "status": "error",
                "error": f"Query ditolak karena mengandung pola terlarang atau berbahaya: '{pat}'.",
            }

    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "error": "Database session not available."}

    # 3. Enforce / inject LIMIT 50
    has_limit = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if has_limit:
        lim = int(has_limit.group(1))
        if lim > 50:
            sql = re.sub(r"\bLIMIT\s+\d+", "LIMIT 50", sql, flags=re.IGNORECASE)
    else:
        sql = f"{sql} LIMIT 50"

    try:
        res = await effective_session.execute(text(sql))
        columns = list(res.keys())
        raw_rows = res.fetchall()

        rows = []
        for row in raw_rows:
            row_dict = {}
            for col_idx, col_name in enumerate(columns):
                val = row[col_idx]
                if isinstance(val, (datetime, date)):
                    val = val.isoformat()
                elif hasattr(val, "__str__") and not isinstance(val, (int, float, bool, type(None))):
                    val = str(val)
                # Sensitive key masking
                lower_col = col_name.lower()
                if any(secret_kw in lower_col for secret_kw in ("password", "secret", "private_key", "token")):
                    val = "********"
                row_dict[col_name] = val
            rows.append(row_dict)

        return {
            "status": "success",
            "sql_executed": sql,
            "row_count": len(rows),
            "columns": columns,
            "rows": rows,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"SQL execution error: {str(e)}",
            "sql": sql,
        }


# =============================================================================
# Tool Registry Bindings
# =============================================================================

@register_tool("inspect_database_schema", aliases=["db_schema", "inspect_schema"], category="DATABASE", parallel_safe=True)
class InspectDatabaseSchemaHandler(ToolHandler):
    name = "inspect_database_schema"
    category = "DATABASE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_inspect_database_schema(args, session=session, executor=executor, **kwargs)


@register_tool("read_database_records", aliases=["query_database", "read_db"], category="DATABASE", parallel_safe=True)
class ReadDatabaseRecordsHandler(ToolHandler):
    name = "read_database_records"
    category = "DATABASE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_read_database_records(args, session=session, executor=executor, **kwargs)


@register_tool("query_database_sql", aliases=["sql_query", "raw_query_sql"], category="DATABASE", parallel_safe=True)
class QueryDatabaseSqlHandler(ToolHandler):
    name = "query_database_sql"
    category = "DATABASE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_query_database_sql(args, session=session, executor=executor, **kwargs)


async def handle_backup_database(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Trigger an on-demand PostgreSQL database backup via pg_dump. Admin only."""
    if executor is not None and not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "Akses Ditolak: Backup database hanya diizinkan untuk Admin.",
            "is_admin": False,
        }
    try:
        from utils.infra.db_backup import create_backup
        from config.settings import load_settings
        settings = load_settings()
        force = bool(args.get("force", True))
        res = await create_backup(settings=settings, force=force)
        return {
            "status": "success" if res.get("success") else "error",
            **res
        }
    except Exception as e:
        return {"status": "error", "error": f"Database backup execution error: {str(e)}"}


@register_tool("backup_database", aliases=["create_db_backup", "dump_database"], category="DATABASE", parallel_safe=False)
class BackupDatabaseHandler(ToolHandler):
    name = "backup_database"
    category = "DATABASE"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_backup_database(args, session=session, executor=executor, **kwargs)


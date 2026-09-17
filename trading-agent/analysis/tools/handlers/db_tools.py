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


async def handle_inspect_database_schema(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Inspect database tables and column definitions. Admin only."""
    if not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "⛔ Akses Ditolak: Inspeksi database hanya diizinkan untuk Admin.",
            "is_admin": False,
        }

    table_map = get_table_model_map()
    table_filter = args.get("table_name", "").strip().lower() if args.get("table_name") else None

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
    if not getattr(executor, "is_admin", False):
        return {
            "status": "error",
            "error": "⛔ Akses Ditolak: Pembacaan data database hanya diizinkan untuk Admin.",
            "is_admin": False,
        }

    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "error", "error": "Database session not available."}

    table_name = str(args.get("table_name", "")).strip().lower()
    table_map = get_table_model_map()

    if not table_name or table_name not in table_map:
        return {
            "status": "error",
            "error": f"Tabel '{table_name}' tidak valid. Gunakan 'inspect_database_schema' untuk melihat tabel yang tersedia.",
            "available_tables": sorted(list(table_map.keys())),
        }

    model_cls = table_map[table_name]
    query = select(model_cls)

    # 1. Apply equality filters safely (SQL injection proof via ORM binding)
    filters = args.get("filters") or {}
    if isinstance(filters, dict):
        for col_name, val in filters.items():
            if hasattr(model_cls, col_name):
                col_attr = getattr(model_cls, col_name)
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

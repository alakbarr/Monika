"""Base SQLAlchemy declarative base and utilities."""

from datetime import datetime
from typing import Any
from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase

try:
    from sqlalchemy.dialects.postgresql import TSVECTOR

    TSVECTOR_TYPE = TSVECTOR().with_variant(Text, "sqlite")
except ImportError:
    TSVECTOR_TYPE = Text
TSVECTOR = TSVECTOR_TYPE

from monika.core.primitives.clock import now as _clock_now


def _utcnow() -> datetime:
    """Mengembalikan waktu saat ini dalam UTC (timezone-aware)."""
    return _clock_now()


class Base(DeclarativeBase):
    pass


__all__ = ["Base", "_utcnow", "TSVECTOR", "TSVECTOR_TYPE"]

"""Base SQLAlchemy declarative base and utilities (Phase 7)."""

from database.models import Base, _utcnow

__all__ = ["Base", "_utcnow"]

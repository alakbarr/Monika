"""
File: cli/doctor.py — Backward-compatible facade.

Canonical implementation has moved to `monika.core.telemetry.doctor`.
"""

from monika.core.telemetry.doctor import DiagnosticItem, SystemDoctor

__all__ = ["DiagnosticItem", "SystemDoctor"]

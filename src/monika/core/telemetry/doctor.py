# ==============================================================================
# Package: monika.core.telemetry
# File: doctor.py
# Description: Telemetry diagnostic facade. Canonical implementation in interfaces.cli.doctor.
# ==============================================================================

"""
Backward-compatible facade for Monika System Doctor.
Canonical CLI diagnostic engine lives in `monika.interfaces.cli.doctor`.
"""

from monika.interfaces.cli.doctor import DiagnosticItem, SystemDoctor

__all__ = ["DiagnosticItem", "SystemDoctor"]

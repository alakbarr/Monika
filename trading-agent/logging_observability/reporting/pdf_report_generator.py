"""
Compatibility facade shim for legacy pdf_report_generator.py.
Re-exports from canonical monika.core.telemetry.reporting.pdf_report_generator.
"""

from __future__ import annotations

import monika.core.telemetry.reporting.pdf_report_generator as _canonical

from monika.core.telemetry.reporting.pdf_report_generator import (
    PDFReportGenerator,
    logger,
)

__all__ = ['PDFReportGenerator', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

# ==============================================================================
# File: utils/analytics/pdf_report_generator.py
# ==============================================================================

"""
Backward-compatibility re-export shim for PDFReportGenerator.
Canonical location: logging_observability.reporting.pdf_report_generator
"""

from logging_observability.reporting.pdf_report_generator import (
    HAS_REPORTLAB,
    PDFReportGenerator,
)

__all__ = ["HAS_REPORTLAB", "PDFReportGenerator"]

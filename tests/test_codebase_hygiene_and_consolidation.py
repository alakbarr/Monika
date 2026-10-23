# ==============================================================================
# File: tests/test_fase8_hygiene_and_consolidation.py
# ==============================================================================

"""
Verification suite for Phase 8 architecture hygiene, utility relocation,
and canonical module re-export backward compatibility.
"""

import pytest


def test_pdf_report_generator_relocation(tmp_path):
    """Verify PDFReportGenerator canonical import and fallback functionality."""
    from monika.core.telemetry.reporting.pdf_report_generator import PDFReportGenerator as CanonicalPDF
    from monika.core.analytics.pdf_report_generator import PDFReportGenerator as ShimPDF

    assert CanonicalPDF is ShimPDF

    gen = CanonicalPDF(output_dir=str(tmp_path))
    metrics = {
        "total_trades": 12,
        "win_rate_pct": 58.3,
        "net_pnl": 1240.50,
        "profit_factor": 1.65,
        "sharpe_ratio": 1.82,
        "max_drawdown_pct": 2.15,
        "expectancy_usd": 103.37,
    }
    result = gen.generate_performance_pdf(metrics=metrics, report_title="Institutional Test Report")
    assert result["success"] is True
    assert "file_path" in result


def test_brent_yfinance_relocation():
    """Verify brent_yfinance canonical import in infrastructure and absence of domain hack."""
    import inspect
    from monika.infrastructure.data_ingestion.sources.brent_yfinance import get_brent_price as canonical_get

    assert inspect.iscoroutinefunction(canonical_get)

    import importlib.util

    domain_spec = importlib.util.find_spec("monika.domain.market.brent_yfinance")
    assert domain_spec is None


def test_security_guards_relocation():
    """Verify nt_guard and supply_chain_quarantine canonical imports in security."""
    from monika.core.security.nt_guard import (
        assert_safe_nt_path as canonical_nt,
        is_dangerous_nt_namespace,
        SecurityViolationError,
    )
    from monika.core.security.nt_guard import assert_safe_nt_path as shim_nt

    assert canonical_nt is shim_nt
    assert is_dangerous_nt_namespace("\\??\\C:\\danger") is True
    assert is_dangerous_nt_namespace("C:\\safe\\path") is False

    from monika.core.security.supply_chain_quarantine import SupplyChainQuarantine as CanonicalSCQ
    from monika.core.security.supply_chain_quarantine import SupplyChainQuarantine as ShimSCQ

    assert CanonicalSCQ is ShimSCQ
    scq = CanonicalSCQ()
    assert "metatrader5" in scq.allowlist or "metatrader5" in scq.critical_libraries

# ==============================================================================
# File: tests/evals/test_harness_audit.py
# ==============================================================================

"""Tests for the hermetic harness audit suite (Wave 0 measurement)."""

import json

import pytest

from monika.application.evals import harness_audit
from monika.application.evals.harness_audit import (
    CHECKS,
    AuditReport,
    AuditResult,
    count_macro_duplicate_headers,
    has_macro_duplication,
    report_to_json,
    run_harness_audit,
)


def test_count_macro_duplicate_headers_detects_duplicate_injection():
    text = (
        "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK\nbody\n"
        "## ACTIVATED SPECIALIZATION SKILL: EVENT-PROBABILITY-PLAYBOOK\nbody"
    )
    counts = count_macro_duplicate_headers(text)
    assert counts["authoritative_event"] == 1
    assert counts["activated_event"] == 1
    assert has_macro_duplication(text) is True


def test_count_macro_duplicate_headers_clean_prompt():
    text = "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK\nbody"
    assert has_macro_duplication(text) is False


def test_report_all_passed_property():
    report = AuditReport(
        generated_at="2026-01-01T00:00:00+00:00",
        duration_ms=1.0,
        checks=[
            AuditResult("a", "A", True, "ok"),
            AuditResult("b", "B", False, "bad"),
        ],
    )
    assert report.passed == 1
    assert report.failed == 1
    assert report.all_passed is False


@pytest.mark.asyncio
async def test_audit_runs_all_checks_and_serializes():
    report = await run_harness_audit()

    assert len(report.checks) == len(CHECKS)
    assert report.passed + report.failed == len(CHECKS)
    assert all(check.detail for check in report.checks)

    ids = [check.check_id for check in report.checks]
    assert len(ids) == len(set(ids))

    payload = report.to_dict()
    assert payload["version"] == harness_audit.AUDIT_VERSION
    assert payload["summary"]["total"] == len(CHECKS)
    assert json.loads(report_to_json(report))["summary"]["total"] == len(CHECKS)


@pytest.mark.asyncio
async def test_audit_outcomes_are_deterministic():
    first = await run_harness_audit()
    second = await run_harness_audit()
    assert [(c.check_id, c.passed) for c in first.checks] == [(c.check_id, c.passed) for c in second.checks]


@pytest.mark.asyncio
async def test_audit_check_exception_is_fail_closed(monkeypatch):
    async def _boom() -> AuditResult:
        raise RuntimeError("boom")

    async def _ok() -> AuditResult:
        return AuditResult("ok", "OK", True, "ok")

    monkeypatch.setattr(harness_audit, "CHECKS", (_boom, _ok))
    report = await harness_audit.run_harness_audit()

    assert report.checks[0].passed is False
    assert "boom" in report.checks[0].detail
    assert report.checks[1].passed is True

# ==============================================================================
# File: tests/security/test_phase9_supply_chain_and_win32.py
# ==============================================================================

"""
Unit tests for Phase 9: Managed uv Installer, Win32 Hardening & Supply-Chain Quarantine.
Tests 14-day quarantine delay, typosquatting prevention, hash integrity, and safe file locking.
"""

import hashlib
import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from utils.security.supply_chain_quarantine import (
    SupplyChainQuarantine,
    QuarantineVerdict,
)


def test_quarantine_blocks_fresh_release():
    """Verify package released within 14 days is quarantined."""
    quarantine = SupplyChainQuarantine(quarantine_days=14)
    fresh_date = datetime.now(timezone.utc) - timedelta(days=3)

    verdict = quarantine.evaluate_package(
        package_name="some-quant-indicator",
        version="1.0.4",
        release_date=fresh_date,
    )

    assert verdict.allowed is False
    assert verdict.status == "QUARANTINED"
    assert "quarantine" in verdict.reason.lower()
    assert verdict.release_age_days is not None
    assert round(verdict.release_age_days) == 3


def test_quarantine_passes_mature_release():
    """Verify package released 25 days ago passes quarantine cleanly."""
    quarantine = SupplyChainQuarantine(quarantine_days=14)
    mature_date = datetime.now(timezone.utc) - timedelta(days=25)

    verdict = quarantine.evaluate_package(
        package_name="stable-timeseries-lib",
        version="2.1.0",
        release_date=mature_date,
    )

    assert verdict.allowed is True
    assert verdict.status == "CLEAN"
    assert "passed all" in verdict.reason


def test_quarantine_allowlist_bypass():
    """Verify explicit operator allowlist permits immediate use of emergency hotfix."""
    quarantine = SupplyChainQuarantine(
        quarantine_days=14,
        allowlist={"urgent-patch-lib==0.1.1"},
    )
    fresh_date = datetime.now(timezone.utc) - timedelta(hours=2)

    verdict = quarantine.evaluate_package(
        package_name="urgent-patch-lib",
        version="0.1.1",
        release_date=fresh_date,
    )

    assert verdict.allowed is True
    assert verdict.status == "ALLOWLISTED"


def test_quarantine_detects_typosquatting():
    """Verify suspicious typosquatting package names trigger immediate blockade."""
    quarantine = SupplyChainQuarantine()

    # "anthroppic" vs "anthropic"
    verdict1 = quarantine.evaluate_package(package_name="anthroppic", version="0.45.0")
    assert verdict1.allowed is False
    assert verdict1.status == "TYPOSQUAT_SUSPECT"
    assert "anthropic" in verdict1.reason

    # "numpyy" vs "numpy"
    verdict2 = quarantine.evaluate_package(package_name="numpyy", version="1.26.4")
    assert verdict2.allowed is False
    assert verdict2.status == "TYPOSQUAT_SUSPECT"
    assert "numpy" in verdict2.reason


def test_quarantine_hash_verification():
    """Verify cryptographic digest mismatches are caught."""
    quarantine = SupplyChainQuarantine()
    content = b"print('Legitimate payload code')"
    legit_hash = hashlib.sha256(content).hexdigest()
    tampered_hash = hashlib.sha256(b"print('Altered payload')").hexdigest()

    # Legitimate
    verdict_good = quarantine.evaluate_package(
        package_name="verified-pkg",
        version="1.0.0",
        package_bytes=content,
        expected_sha256=legit_hash,
    )
    assert verdict_good.allowed is True

    # Tampered
    verdict_bad = quarantine.evaluate_package(
        package_name="verified-pkg",
        version="1.0.0",
        package_bytes=content,
        expected_sha256=tampered_hash,
    )
    assert verdict_bad.allowed is False
    assert verdict_bad.status == "HASH_MISMATCH"

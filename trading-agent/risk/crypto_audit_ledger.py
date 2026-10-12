# ==============================================================================
# File: risk/crypto_audit_ledger.py
# Description: Backward-compatibility shim for monika.domain.risk.crypto_audit_ledger
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.crypto_audit_ledger
"""

import sys
import monika.domain.risk.crypto_audit_ledger as _canonical

from monika.domain.risk.crypto_audit_ledger import (
    AuditRecord,
    CryptoAuditLedger,
    CryptographicAuditLedger,
    GENESIS_PREV_HASH,
    LedgerCorruptionError,
    LedgerTamperedError,
    annotations,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "AuditRecord",
    "CryptoAuditLedger",
    "CryptographicAuditLedger",
    "GENESIS_PREV_HASH",
    "LedgerCorruptionError",
    "LedgerTamperedError",
    "annotations",
    "logger",
]

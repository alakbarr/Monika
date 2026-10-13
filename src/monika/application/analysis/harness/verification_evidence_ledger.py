"""
Backward-compatibility facade for verification_evidence_ledger.
Canonical location: monika.application.agent.harness.verification_evidence_ledger
"""

import sys
import monika.application.agent.harness.verification_evidence_ledger as _canonical

from monika.application.agent.harness.verification_evidence_ledger import (
    VerificationEvidenceLedger,
    VerificationRecord,
)

__all__ = ["VerificationRecord", "VerificationEvidenceLedger"]

sys.modules[__name__] = _canonical

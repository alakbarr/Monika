"""Shim module: monika.application.analysis.harness.verification_evidence_ledger."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.verification_evidence_ledger import *

_canonical = _importlib.import_module("monika.application.analysis.harness.verification_evidence_ledger")
_sys.modules[__name__] = _canonical

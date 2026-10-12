"""Shim module: monika.application.evals.oracles.risk_compliance_oracle."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.oracles.risk_compliance_oracle import *

_canonical = _importlib.import_module("monika.application.evals.oracles.risk_compliance_oracle")
_sys.modules[__name__] = _canonical

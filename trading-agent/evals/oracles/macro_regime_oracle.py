"""Shim module: monika.application.evals.oracles.macro_regime_oracle."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.oracles.macro_regime_oracle import *

_canonical = _importlib.import_module("monika.application.evals.oracles.macro_regime_oracle")
_sys.modules[__name__] = _canonical

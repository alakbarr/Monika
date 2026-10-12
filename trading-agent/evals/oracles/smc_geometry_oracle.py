"""Shim module: monika.application.evals.oracles.smc_geometry_oracle."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.oracles.smc_geometry_oracle import *

_canonical = _importlib.import_module("monika.application.evals.oracles.smc_geometry_oracle")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.evals.oracles.trade_discipline_oracle."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.oracles.trade_discipline_oracle import *

_canonical = _importlib.import_module("monika.application.evals.oracles.trade_discipline_oracle")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.agent.auxiliary_model_router."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.auxiliary_model_router import *

_canonical = _importlib.import_module("monika.application.agent.auxiliary_model_router")
_sys.modules[__name__] = _canonical

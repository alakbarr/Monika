"""Shim module: monika.application.analysis.tools.quant_sandbox.rpc_server."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.quant_sandbox.rpc_server import *

_canonical = _importlib.import_module("monika.application.analysis.tools.quant_sandbox.rpc_server")
_sys.modules[__name__] = _canonical

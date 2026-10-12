"""Shim module: monika.application.analysis.tools.kernel.persistent_session_kernel."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.kernel.persistent_session_kernel import *

_canonical = _importlib.import_module("monika.application.analysis.tools.kernel.persistent_session_kernel")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.tools.environments.pty_query_responder."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.environments.pty_query_responder import *

_canonical = _importlib.import_module("monika.application.analysis.tools.environments.pty_query_responder")
_sys.modules[__name__] = _canonical

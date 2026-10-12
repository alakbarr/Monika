"""Shim module: monika.application.services.system_status_service."""

import sys as _sys
import importlib as _importlib

from monika.application.services.system_status_service import *

_canonical = _importlib.import_module("monika.application.services.system_status_service")
_sys.modules[__name__] = _canonical

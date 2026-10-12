"""Shim module: monika.application.scheduler.universal_cron_scheduler."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.universal_cron_scheduler import *

_canonical = _importlib.import_module("monika.application.scheduler.universal_cron_scheduler")
_sys.modules[__name__] = _canonical

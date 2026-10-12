"""Shim module: monika.application.scheduler.detached_cron_worker."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.detached_cron_worker import *

_canonical = _importlib.import_module("monika.application.scheduler.detached_cron_worker")
_sys.modules[__name__] = _canonical

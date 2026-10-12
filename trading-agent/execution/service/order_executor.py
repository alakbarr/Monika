"""Shim module: monika.application.execution.service.order_executor."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.order_executor import *
from monika.application.execution.service.order_executor import (
    _EXECUTION_LOCK,
    _EXECUTED_ANALYSIS_IDS,
    _LAST_CLEANUP_TIME,
)

_canonical = _importlib.import_module("monika.application.execution.service.order_executor")
_sys.modules[__name__] = _canonical

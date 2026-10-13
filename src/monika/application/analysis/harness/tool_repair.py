"""
Backward-compatibility facade for tool_repair.
Canonical location: monika.application.agent.harness.tool_repair
"""

import sys
import monika.application.agent.harness.tool_repair as _canonical

from monika.application.agent.harness.tool_repair import (
    TOOL_NAME_ALIASES,
    _parse_xml_parameters,
    coerce_tool_arguments,
    repair_tool_arguments,
    repair_tool_name,
)

__all__ = [
    "TOOL_NAME_ALIASES",
    "repair_tool_name",
    "_parse_xml_parameters",
    "repair_tool_arguments",
    "coerce_tool_arguments",
]

sys.modules[__name__] = _canonical

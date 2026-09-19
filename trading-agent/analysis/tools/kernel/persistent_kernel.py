# ==============================================================================
# File: analysis/tools/kernel/persistent_kernel.py
# Description: Persistent Programmatic Tool Calling (PTC) Execution Kernel
# ==============================================================================

"""
Persistent execution kernel for local Python analysis scripts.
Retains declared helper functions, imported packages, and in-memory variables
across multiple turns in an analysis cycle without sub-process cold-start overhead.
"""

import io
import sys
import time
import logging
import traceback
from typing import Dict, Any, Tuple
from analysis.tools.kernel.env_sanitizer import get_sanitized_environment
from analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.PersistentKernel")


class PersistentCodeKernel:
    """Isolated persistent Python execution session."""

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.namespace: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
        }
        self.execution_count: int = 0

    def execute(self, code_str: str, timeout_seconds: float = 30.0) -> Tuple[str, bool]:
        """
        Execute code string within the persistent namespace.
        Returns: (output_text, is_success)
        """
        self.execution_count += 1
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        is_success = True
        try:
            # Compile and execute within the persistent namespace
            compiled_code = compile(code_str, f"<ptc_session_{self.session_id}>", "exec")
            exec(compiled_code, self.namespace)
        except Exception as e:
            is_success = False
            traceback.print_exc(file=stderr_capture)
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

        stdout_val = stdout_capture.getvalue()
        stderr_val = stderr_capture.getvalue()

        output = stdout_val
        if stderr_val:
            output += f"\n[STDERR]:\n{stderr_val}" if output else stderr_val

        if not output and is_success:
            output = "[Execution succeeded with no stdout/stderr]"

        # Apply head/tail truncation and spilling
        processed_output, _ = truncate_and_spill_output(output, tool_name=f"ptc_{self.session_id}")
        return processed_output, is_success

    def reset(self) -> None:
        """Reset the namespace for a new session."""
        self.namespace = {
            "__name__": "__main__",
            "__doc__": None,
        }
        self.execution_count = 0

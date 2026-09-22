"""
Sandboxed Subprocess Code Execution Runner.
Executes quantitative analysis code inside an isolated Python subprocess
with sanitized environment variables, restricted execution timeouts, and AST validation.
"""

import ast
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

from analysis.tools.kernel.env_sanitizer import get_sanitized_environment
from analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.SandboxRunner")

DEFAULT_TIMEOUT_SECONDS: float = 30.0
MAX_OUTPUT_CHARS: int = 50_000

FORBIDDEN_MODULES = frozenset({
    "ctypes",
    "pty",
    "shutil",
    "signal",
    "subprocess",
    "webbrowser",
    "winreg",
    "_winapi",
})

FORBIDDEN_CALLS = frozenset({
    "compile",
    "eval",
    "exec",
    "__import__",
})


def validate_code_ast(code: str) -> Tuple[bool, str]:
    """
    Statically inspects Python code using AST to block dangerous system modules and calls.
    Returns: (is_safe, error_message)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError in code: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_root = alias.name.split(".")[0].lower()
                if mod_root in FORBIDDEN_MODULES:
                    return False, f"Security Violation: Import of restricted module '{mod_root}' is prohibited."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_root = node.module.split(".")[0].lower()
                if mod_root in FORBIDDEN_MODULES:
                    return False, f"Security Violation: Import from restricted module '{mod_root}' is prohibited."
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    return False, f"Security Violation: Invocation of built-in '{node.func.id}' is prohibited."

    return True, ""


class SandboxedKernel:
    """
    Subprocess sandbox runner ensuring that untrusted or generated Python code
    cannot access host memory, credentials, or live trading connections.
    """

    def __init__(
        self,
        session_id: str = "sandbox",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ):
        self.session_id = session_id
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.execution_count: int = 0

    def execute(
        self,
        code_str: str,
        timeout_seconds: Optional[float] = None,
        custom_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, bool]:
        """
        Executes code in an isolated Python subprocess.
        
        Args:
            code_str: Python code to execute.
            timeout_seconds: Timeout ceiling in seconds.
            custom_env: Optional custom environment (will be strictly sanitized).
            
        Returns:
            (processed_output, is_success)
        """
        self.execution_count += 1
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds

        # 1. AST Static Security Check
        is_safe, sec_error = validate_code_ast(code_str)
        if not is_safe:
            logger.warning(f"[SandboxRunner] Blocked dangerous code in session '{self.session_id}': {sec_error}")
            return f"[SANDBOX ERROR]: {sec_error}", False

        # 2. Prepare sanitized environment (stripped of API keys, DB DSNs, MT5 credentials)
        clean_env = get_sanitized_environment(custom_env)

        # 3. Write code to a secure temporary script file
        temp_file: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                encoding="utf-8",
                delete=False,
            ) as tmp:
                tmp.write(code_str)
                temp_file = Path(tmp.name)

            # 4. Execute in subprocess using system Python executable
            cmd = [sys.executable, "-I", str(temp_file)]  # -I: isolated mode (no user site, no env)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=clean_env,
                cwd=tempfile.gettempdir(),
            )

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            is_success = (proc.returncode == 0)

            output = stdout
            if stderr:
                output += f"\n[STDERR]:\n{stderr}" if output else stderr

            if not output and is_success:
                output = "[Execution succeeded with no stdout/stderr]"

        except subprocess.TimeoutExpired:
            logger.warning(f"[SandboxRunner] Subprocess execution timed out after {timeout}s in session '{self.session_id}'")
            return f"[SANDBOX TIMEOUT]: Execution exceeded deadline of {timeout}s.", False
        except Exception as e:
            logger.error(f"[SandboxRunner] Subprocess execution failed: {e}", exc_info=True)
            return f"[SANDBOX ERROR]: {str(e)}", False
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

        # 5. Output truncation and disk spillover
        processed_output, _ = truncate_and_spill_output(
            output,
            tool_name=f"sandbox_{self.session_id}",
        )
        return processed_output, is_success

"""
Unit tests for SandboxedKernel and secure code execution.
"""

import pytest
from analysis.tools.kernel.sandbox_runner import (
    SandboxedKernel,
    validate_code_ast,
)
from analysis.tools.kernel.persistent_kernel import PersistentCodeKernel


def test_validate_code_ast_clean():
    safe_code = """
import math
x = [1, 2, 3, 4, 5]
mean = sum(x) / len(x)
print(f"Mean: {mean}")
"""
    is_safe, err = validate_code_ast(safe_code)
    assert is_safe is True
    assert err == ""


def test_validate_code_ast_blocks_forbidden_import():
    evil_code = "import subprocess\nsubprocess.run(['ls'])"
    is_safe, err = validate_code_ast(evil_code)
    assert is_safe is False
    assert "Import of restricted module 'subprocess'" in err

    evil_from = "from ctypes import c_int\nx = c_int(10)"
    is_safe, err = validate_code_ast(evil_from)
    assert is_safe is False
    assert "Import from restricted module 'ctypes'" in err


def test_validate_code_ast_blocks_forbidden_call():
    evil_exec = "code = 'print(1)'\nexec(code)"
    is_safe, err = validate_code_ast(evil_exec)
    assert is_safe is False
    assert "Invocation of built-in 'exec'" in err

    evil_eval = "x = eval('2 + 2')"
    is_safe, err = validate_code_ast(evil_eval)
    assert is_safe is False
    assert "Invocation of built-in 'eval'" in err


def test_sandboxed_kernel_clean_execution():
    kernel = SandboxedKernel(session_id="test_clean")
    code = "result = 40 + 2\nprint(f'ANSWER:{result}')"
    output, success = kernel.execute(code, timeout_seconds=5.0)
    assert success is True
    assert "ANSWER:42" in output


def test_sandboxed_kernel_runtime_error():
    kernel = SandboxedKernel(session_id="test_error")
    code = "x = 10 / 0"
    output, success = kernel.execute(code, timeout_seconds=5.0)
    assert success is False
    assert "ZeroDivisionError" in output


def test_sandboxed_kernel_timeout():
    kernel = SandboxedKernel(session_id="test_timeout")
    code = "import time\ntime.sleep(5)"
    output, success = kernel.execute(code, timeout_seconds=0.5)
    assert success is False
    assert "[SANDBOX TIMEOUT]" in output


def test_persistent_kernel_sandbox_delegation():
    # Test sandboxed mode
    p_kernel = PersistentCodeKernel(session_id="p_test", sandbox_mode=True)
    out, ok = p_kernel.execute("print('Hello from sandboxed kernel')")
    assert ok is True
    assert "Hello from sandboxed kernel" in out

    # Test unsafe in-process mode
    p_unsafe = PersistentCodeKernel(session_id="p_unsafe", sandbox_mode=False)
    out_unsafe, ok_unsafe = p_unsafe.execute("print('In-process output')")
    assert ok_unsafe is True
    assert "In-process output" in out_unsafe

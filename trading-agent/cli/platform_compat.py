# ==============================================================================
# File: cli/platform_compat.py
# Description: Cross-Platform Hardening & Terminal Compatibility
# ==============================================================================

"""
Terminal compatibility layer for Monika AI Trading Agent.

Features:
- UTF-8 standard stream rebinding on Windows to prevent UnicodeEncodeError (cp1252).
- Terminal capability detection (color depth, unicode / braille glyph support).
- Windows Virtual Terminal (VT) processing enablement via kernel32.
"""

import os
import sys
from enum import Enum
from typing import Optional


class ColorDepth(str, Enum):
    MONO = "mono"
    BASIC_16 = "16"
    ANSI_256 = "256"
    TRUECOLOR = "truecolor"


def ensure_utf8_streams() -> None:
    """
    Rebind stdout/stderr/stdin to UTF-8 on Windows.
    Prevents UnicodeEncodeError on legacy consoles (cp1252/cp437).
    """
    if sys.platform != "win32":
        return

    import io

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        elif hasattr(stream, "buffer"):
            try:
                wrapper = io.TextIOWrapper(
                    stream.buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=getattr(stream, "line_buffering", False),
                )
                setattr(sys, stream_name, wrapper)
            except Exception:
                pass

    # For stdin, only call reconfigure if supported (do not wrap buffer to avoid pytest capture teardown issue)
    stdin_stream = getattr(sys, "stdin", None)
    if stdin_stream and hasattr(stdin_stream, "reconfigure"):
        try:
            stdin_stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def detect_color_depth() -> ColorDepth:
    """Detect terminal color support via environment variables and terminal emulators."""
    colorterm = os.environ.get("COLORTERM", "").strip().lower()
    if colorterm in ("truecolor", "24bit"):
        return ColorDepth.TRUECOLOR

    term = os.environ.get("TERM", "").strip().lower()
    if "256color" in term or "direct" in term:
        return ColorDepth.ANSI_256
    if term in ("dumb", ""):
        return ColorDepth.MONO

    # Windows Terminal and modern terminals default to truecolor
    if sys.platform == "win32":
        if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM") in ("vscode", "hyper", "wezterm", "alacritty"):
            return ColorDepth.TRUECOLOR
        return ColorDepth.ANSI_256

    return ColorDepth.ANSI_256


def detect_unicode_support() -> bool:
    """Check if terminal environment reliably supports UTF-8 and braille symbols."""
    if sys.platform == "win32":
        # Windows Terminal, VS Code, WezTerm, ConEmu have full UTF-8 Unicode support
        if (
            os.environ.get("WT_SESSION")
            or os.environ.get("TERM_PROGRAM") in ("vscode", "hyper", "wezterm")
            or os.environ.get("ConEmuPID")
        ):
            return True
        # Check console output code page
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            return kernel32.GetConsoleOutputCP() == 65001
        except Exception:
            return False

    # Unix-like systems (Linux / macOS / WSL)
    lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")
    return "utf-8" in lang.lower() or "utf8" in lang.lower()


def enable_windows_vt_mode() -> bool:
    """Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING on Windows console handles."""
    if sys.platform != "win32":
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.argtypes = [ctypes.c_long]
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetConsoleMode.restype = ctypes.c_bool
        kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.SetConsoleMode.restype = ctypes.c_bool

        for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(handle_id)
            if handle:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                    kernel32.SetConsoleMode(handle, mode)
        return True
    except Exception:
        return False


def apply_platform_fixes() -> None:
    """
    Execute platform hardening early in CLI bootstrap before Textual/Rich init.
    Safe to call multiple times.
    """
    ensure_utf8_streams()
    if sys.platform == "win32":
        enable_windows_vt_mode()

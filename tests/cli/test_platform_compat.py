# ==============================================================================
# File: tests/cli/test_platform_compat.py
# Description: Unit Tests for Platform Compatibility Layer
# ==============================================================================

import os
import sys
from unittest.mock import patch
import pytest

from cli.platform_compat import (
    ColorDepth,
    ensure_utf8_streams,
    detect_color_depth,
    detect_unicode_support,
    apply_platform_fixes,
)


def test_color_depth_detection():
    """Detects color depths based on environment variables."""
    with patch.dict(os.environ, {"COLORTERM": "truecolor"}):
        assert detect_color_depth() == ColorDepth.TRUECOLOR

    with patch.dict(os.environ, {"COLORTERM": "", "TERM": "xterm-256color"}):
        assert detect_color_depth() == ColorDepth.ANSI_256

    with patch.dict(os.environ, {"COLORTERM": "", "TERM": "dumb"}):
        assert detect_color_depth() == ColorDepth.MONO


def test_unicode_support_detection():
    """Unicode support detection returns boolean without throwing."""
    res = detect_unicode_support()
    assert isinstance(res, bool)


def test_ensure_utf8_streams_safe():
    """ensure_utf8_streams runs safely without raising exceptions."""
    ensure_utf8_streams()


def test_apply_platform_fixes_idempotent():
    """apply_platform_fixes can be called repeatedly."""
    apply_platform_fixes()
    apply_platform_fixes()

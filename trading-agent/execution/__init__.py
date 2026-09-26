# ==============================================================================
# File: execution/__init__.py
# ==============================================================================

"""Execution subsystem for Monika AI Trading Agent."""

# Auto-bootstrap MT5 cross-platform compatibility layer (native Windows or Linux RPC bridge)
try:
    from execution.mt5_compat import ensure_mt5_module
    ensure_mt5_module()
except Exception:
    pass

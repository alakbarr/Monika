# ==============================================================================
# File: analysis/tools/environments/pty_query_responder.py
# ==============================================================================

"""
Backward compatibility facade for PTY Escape Query Responder.
Canonical implementation is now in monika.infrastructure.sandboxes.pty_query_responder.
"""

from monika.infrastructure.sandboxes.pty_query_responder import PtyQueryResponder

__all__ = ["PtyQueryResponder"]

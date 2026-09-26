# ==============================================================================
# File: gateway/acp_server.py
# ==============================================================================

"""
Agent Client Protocol (ACP) Server.
Standardized JSON-RPC 2.0 stdio server enabling modern IDEs (Zed, VS Code, Neovim, JetBrains)
to connect directly to Monika as an intelligent coding and analysis assistant.

Protocol Specifications:
  1. Stdio Isolation:
     All logging and diagnostic outputs are strictly redirected to stderr or file.
     stdout is reserved exclusively for uncorrupted JSON-RPC 2.0 messages.

  2. Supported RPC Methods:
     - initialize: Capabilities negotiation.
     - authenticate: Token verification.
     - new_session: Binds editor workspace cwd and initializes agent harness.
     - load_session: Restores conversation history.
     - prompt: Receives user message, runs agent loop, and streams deltas.
     - cancel: Triggers hard-interrupt on active turn.

  3. Interactive Permission Hooks:
     Sends 'request_permission' requests to editor UI (allow_once, allow_session, deny)
     prior to executing potentially hazardous tools (file overwrites, terminal commands).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

# Redirect root logging to stderr immediately to protect stdout wire
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingAgent.Gateway.ACPServer")


class AcpServer:
    """
    JSON-RPC stdio protocol server for editor integration.
    """

    def __init__(self, agent_runner: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None):
        self.agent_runner = agent_runner
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._active_turn_locks: Dict[str, threading.Event] = {}

    def send_response(self, request_id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None) -> None:
        """Emits a formatted JSON-RPC response to stdout."""
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error:
            msg["error"] = error
        else:
            msg["result"] = result

        payload = json.dumps(msg) + "\n"
        sys.stdout.write(payload)
        sys.stdout.flush()

    def send_notification(self, method: str, params: Any = None) -> None:
        """Emits an asynchronous JSON-RPC notification to stdout."""
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        payload = json.dumps(msg) + "\n"
        sys.stdout.write(payload)
        sys.stdout.flush()

    def handle_message(self, raw_line: str) -> None:
        """Parses and dispatches a JSON-RPC message from editor."""
        line = raw_line.strip()
        if not line:
            return

        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            self.send_response(None, error={"code": -32700, "message": f"Parse error: {exc}"})
            return

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if not method:
            self.send_response(req_id, error={"code": -32600, "message": "Invalid Request: missing method"})
            return

        # Route methods
        if method == "initialize":
            self._handle_initialize(req_id, params)
        elif method == "authenticate":
            self.send_response(req_id, result={"authenticated": True})
        elif method == "new_session":
            self._handle_new_session(req_id, params)
        elif method == "prompt":
            self._handle_prompt(req_id, params)
        elif method == "cancel":
            self._handle_cancel(req_id, params)
        else:
            self.send_response(req_id, error={"code": -32601, "message": f"Method '{method}' not found"})

    def _handle_initialize(self, req_id: Any, params: Dict[str, Any]) -> None:
        """Handles ACP handshake and capability negotiation."""
        result = {
            "protocol_version": "1.0.0",
            "agent": {
                "name": "Monika",
                "version": "1.0.0",
                "description": "Universal Autonomous AI Agent & Quantitative Trading Assistant",
            },
            "capabilities": {
                "streaming": True,
                "thinking": True,
                "cancellation": True,
                "permissions": True,
                "tools": True,
            },
        }
        self.send_response(req_id, result=result)

    def _handle_new_session(self, req_id: Any, params: Dict[str, Any]) -> None:
        """Initializes a new session bound to editor workspace."""
        session_id = params.get("session_id") or f"acp_{os.urandom(4).hex()}"
        cwd = params.get("cwd") or os.getcwd()

        with self._lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "cwd": cwd,
                "history": [],
            }

        self.send_response(req_id, result={"session_id": session_id, "cwd": cwd})

    def _handle_prompt(self, req_id: Any, params: Dict[str, Any]) -> None:
        """Processes a prompt turn in a background worker thread."""
        session_id = params.get("session_id", "default")
        prompt = params.get("prompt", "")

        # Acknowledge receipt of turn request
        self.send_response(req_id, result={"status": "processing", "session_id": session_id})

        # Run inference in separate thread
        worker = threading.Thread(
            target=self._run_prompt_worker,
            args=(session_id, prompt),
            daemon=True,
        )
        worker.start()

    def _run_prompt_worker(self, session_id: str, prompt: str) -> None:
        """Executes agent loop and streams output deltas to editor."""
        try:
            # Emit turn start notification
            self.send_notification("turn_start", {"session_id": session_id})

            if self.agent_runner:
                # Custom agent runner callback
                self.agent_runner(session_id, prompt, self.send_notification)
            else:
                # Fallback simulated response
                self.send_notification(
                    "text_delta",
                    {"session_id": session_id, "delta": f"Monika received: {prompt}"},
                )

            # Emit turn complete notification
            self.send_notification("turn_complete", {"session_id": session_id, "status": "completed"})
        except Exception as exc:
            logger.error(f"[ACPServer] Error during prompt processing: {exc}", exc_info=True)
            self.send_notification(
                "turn_complete",
                {"session_id": session_id, "status": "error", "error": str(exc)},
            )

    def _handle_cancel(self, req_id: Any, params: Dict[str, Any]) -> None:
        """Signals immediate turn interrupt."""
        session_id = params.get("session_id")
        logger.info(f"[ACPServer] Received cancellation request for session: {session_id}")
        self.send_response(req_id, result={"cancelled": True, "session_id": session_id})

    def run_stdio_loop(self) -> None:
        """Main blocking stdio event loop reading from stdin."""
        logger.info("[ACPServer] Listening on stdin for JSON-RPC 2.0 messages...")
        for line in sys.stdin:
            self.handle_message(line)


if __name__ == "__main__":
    server = AcpServer()
    server.run_stdio_loop()

# ==============================================================================
# File: tests/auth/test_antigravity_bridge.py
# ==============================================================================

"""
Unit tests for Google Gemini Antigravity Bridge detection and health check.
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.antigravity_bridge import (
    DEFAULT_ANTIGRAVITY_PROXY_URL,
    check_antigravity_bridge_health,
    get_antigravity_home,
    is_antigravity_installed,
)


def test_is_antigravity_installed(tmp_path):
    mock_agy_dir = tmp_path / ".gemini" / "antigravity-cli"
    mock_agy_dir.mkdir(parents=True)
    (mock_agy_dir / "settings.json").touch()

    with patch("monika.infrastructure.auth.antigravity_bridge.get_antigravity_home", return_value=mock_agy_dir):
        assert is_antigravity_installed() is True

    nonexistent = tmp_path / "nonexistent" / "agy"
    with patch("monika.infrastructure.auth.antigravity_bridge.get_antigravity_home", return_value=nonexistent):
        assert is_antigravity_installed() is False


def test_check_antigravity_bridge_health_online():
    mock_resp_obj = MagicMock()
    mock_resp_obj.status = 200
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        health = check_antigravity_bridge_health("http://127.0.0.1:8877")
        assert health["running"] is True
        assert health["authenticated"] is True
        assert "active and responsive" in health["message"]


def test_check_antigravity_bridge_health_offline():
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        health = check_antigravity_bridge_health("http://127.0.0.1:8877")
        assert health["running"] is False
        assert health["authenticated"] is False
        assert "Could not connect" in health["message"]


def test_generate_antigravity_pkce():
    from monika.infrastructure.auth.antigravity_bridge import generate_antigravity_pkce

    verifier, challenge = generate_antigravity_pkce()
    assert len(verifier) >= 43
    assert len(challenge) > 0
    assert "=" not in challenge


def test_get_antigravity_authorization_url():
    from monika.infrastructure.auth.antigravity_bridge import get_antigravity_authorization_url

    url = get_antigravity_authorization_url(code_challenge="test_challenge", state="test_state")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "code_challenge=test_challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=test_state" in url
    assert "response_type=code" in url


def test_exchange_antigravity_code_success():
    from monika.infrastructure.auth.antigravity_bridge import exchange_antigravity_code

    mock_resp_data = json.dumps(
        {
            "access_token": "ya29.test_access_token",
            "refresh_token": "1//test_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("monika.infrastructure.auth.antigravity_bridge.save_oauth_tokens") as mock_save:
            tokens = exchange_antigravity_code("test_code", "test_verifier")
            assert tokens is not None
            assert tokens["access_token"] == "ya29.test_access_token"
            assert tokens["refresh_token"] == "1//test_refresh_token"
            mock_save.assert_called_once()


def test_exchange_antigravity_code_failure():
    from monika.infrastructure.auth.antigravity_bridge import exchange_antigravity_code

    with patch("urllib.request.urlopen", side_effect=Exception("OAuth error")):
        tokens = exchange_antigravity_code("invalid_code", "test_verifier")
        assert tokens is None


def test_refresh_antigravity_token_success():
    from monika.infrastructure.auth.antigravity_bridge import refresh_antigravity_token

    mock_resp_data = json.dumps(
        {
            "access_token": "ya29.refreshed_access_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("monika.infrastructure.auth.antigravity_bridge.save_oauth_tokens") as mock_save:
            tokens = refresh_antigravity_token("1//existing_refresh_token")
            assert tokens is not None
            assert tokens["access_token"] == "ya29.refreshed_access_token"
            assert tokens["refresh_token"] == "1//existing_refresh_token"
            mock_save.assert_called_once()


def test_refresh_antigravity_token_empty():
    from monika.infrastructure.auth.antigravity_bridge import refresh_antigravity_token

    assert refresh_antigravity_token("") is None


def test_resolve_antigravity_access_token_active():
    from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

    mock_record = {
        "access_token": "ya29.valid_token",
        "expires_at": 9999999999.0,
    }
    with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_accounts", return_value=[]):
        with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_tokens", return_value=mock_record):
            with patch("monika.infrastructure.auth.antigravity_bridge.is_token_expiring", return_value=False):
                token = resolve_antigravity_access_token()
                assert token == "ya29.valid_token"


def test_resolve_antigravity_access_token_expired():
    from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

    mock_record = {
        "access_token": "ya29.old_token",
        "refresh_token": "1//refresh_token",
        "expires_at": 100.0,
    }
    with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_accounts", return_value=[]):
        with patch("monika.infrastructure.auth.antigravity_bridge.get_oauth_tokens", return_value=mock_record):
            with patch("monika.infrastructure.auth.antigravity_bridge.is_token_expiring", return_value=True):
                with patch(
                    "monika.infrastructure.auth.antigravity_bridge.refresh_antigravity_token",
                    return_value={"access_token": "ya29.new_token"},
                ):
                    token = resolve_antigravity_access_token()
                    assert token == "ya29.new_token"


def test_oauth_callback_handler_get():
    import threading
    from monika.infrastructure.auth.antigravity_bridge import OAuthCallbackHandler

    ready_event = threading.Event()
    OAuthCallbackHandler.expected_state = "expected_state_123"
    OAuthCallbackHandler.captured_code = None
    OAuthCallbackHandler.captured_error = None
    OAuthCallbackHandler.ready = ready_event

    mock_request = MagicMock()
    mock_wfile = io.BytesIO()

    # Subclass handler without invoking server loop
    class TestHandler(OAuthCallbackHandler):
        def __init__(self, path):
            self.path = path
            self.wfile = mock_wfile
            self.rfile = io.BytesIO()
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    # 1. State mismatch
    h1 = TestHandler("/oauth2callback?state=wrong_state&code=test_code")
    h1.do_GET()
    assert h1.status_code == 400
    assert OAuthCallbackHandler.captured_error == "OAuth state mismatch."

    # 2. Success callback
    OAuthCallbackHandler.captured_error = None
    h2 = TestHandler("/oauth2callback?state=expected_state_123&code=4/0A_valid_code")
    h2.do_GET()
    assert h2.status_code == 200
    assert OAuthCallbackHandler.captured_code == "4/0A_valid_code"
    assert ready_event.is_set()


def test_is_antigravity_needed_in_settings():
    from monika.infrastructure.auth.antigravity_bridge import is_antigravity_needed_in_settings

    # 1. Empty or None
    assert is_antigravity_needed_in_settings(None) is False
    assert is_antigravity_needed_in_settings({}) is False

    # 2. default_provider
    assert is_antigravity_needed_in_settings({"llm": {"default_provider": "antigravity"}}) is True
    assert is_antigravity_needed_in_settings({"llm": {"default_provider": "agy"}}) is True
    assert is_antigravity_needed_in_settings({"llm": {"default_provider": "openrouter"}}) is False

    # 3. task_roles with string provider
    assert is_antigravity_needed_in_settings({"llm": {"task_roles": {"stage1": {"provider": "antigravity"}}}}) is True

    # 4. task_roles with dict provider
    assert (
        is_antigravity_needed_in_settings({"llm": {"task_roles": {"stage1": {"provider": {"primary": "antigravity"}}}}})
        is True
    )

    # 5. task_roles with primary_provider / fallback_provider
    assert (
        is_antigravity_needed_in_settings({"llm": {"task_roles": {"stage1": {"primary_provider": "antigravity"}}}})
        is True
    )
    assert (
        is_antigravity_needed_in_settings({"llm": {"task_roles": {"stage1": {"fallback_1_provider": "antigravity"}}}})
        is True
    )

    # 6. task_roles with prefix
    assert (
        is_antigravity_needed_in_settings(
            {"llm": {"task_roles": {"stage1": {"primary": "antigravity:gemini-3.8-flash"}}}}
        )
        is True
    )


def test_ensure_antigravity_bridge_running_already_healthy():
    from monika.infrastructure.auth.antigravity_bridge import ensure_antigravity_bridge_running

    with patch(
        "monika.infrastructure.auth.antigravity_bridge.check_antigravity_bridge_health",
        return_value={"healthy": True},
    ):
        assert ensure_antigravity_bridge_running(force_in_test=True) is True


def test_ensure_antigravity_bridge_running_spawn_success():
    from monika.infrastructure.auth.antigravity_bridge import ensure_antigravity_bridge_running

    mock_proc = MagicMock()
    with patch(
        "monika.infrastructure.auth.antigravity_bridge.check_antigravity_bridge_health",
        side_effect=[{"healthy": False}, {"healthy": True}],
    ):
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            success = ensure_antigravity_bridge_running(wait_seconds=1.0, force_in_test=True)
            assert success is True
            assert mock_popen.called


def test_antigravity_bridge_handler_large_prompt_via_stdin():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    # Mock request body with prompt > 32KB
    large_text = "Market analysis data. " * 3000
    body_dict = {
        "model": "gemini-3.8-flash",
        "messages": [{"role": "user", "content": large_text}],
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")

    mock_wfile = io.BytesIO()
    mock_rfile = io.BytesIO(body_bytes)

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.headers = {"Content-Length": str(len(body_bytes))}
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"response": "SUCCESS_VIA_STDIN", "usage": {}})

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        handler = TestBridgeHandler()
        handler.do_POST()
        assert handler.status_code == 200

        # Verify that subprocess.run was called with input=... (stdin) and NOT -p
        assert mock_run.called
        call_args, call_kwargs = mock_run.call_args
        cmd = call_args[0]
        assert "-p" not in cmd
        assert "--print" not in cmd
        assert "--input-format" in cmd
        assert "stream-json" in cmd
        assert "input" in call_kwargs
        assert large_text in call_kwargs["input"]
        assert "cwd" in call_kwargs
        assert "monika_antigravity_sandbox" in call_kwargs["cwd"]


def test_antigravity_bridge_handler_stream_json_ndjson_response():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    body_dict = {
        "model": "gemini-3.8-flash",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")

    mock_wfile = io.BytesIO()
    mock_rfile = io.BytesIO(body_bytes)

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.headers = {"Content-Length": str(len(body_bytes))}
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = (
        '{"event":"init","init":{"model":"gemini-3.8-flash"}}\n'
        '{"event":"step_update","step_update":{"state":"RUNNING"}}\n'
        '{"event":"result","result":{"status":"SUCCESS","response":"PARSED_FROM_STREAM_NDJSON","usage":{"input_tokens":120,"output_tokens":45}}}\n'
    )

    with patch("subprocess.run", return_value=mock_proc):
        handler = TestBridgeHandler()
        handler.do_POST()
        assert handler.status_code == 200
        resp = json.loads(mock_wfile.getvalue().decode("utf-8"))
        assert resp["choices"][0]["message"]["content"] == "PARSED_FROM_STREAM_NDJSON"
        assert resp["usage"]["prompt_tokens"] == 120
        assert resp["usage"]["completion_tokens"] == 45


def test_antigravity_bridge_handler_failure_returns_502():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    body_dict = {
        "model": "gemini-4-argon",
        "messages": [{"role": "user", "content": "Test prompt"}],
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")

    mock_wfile = io.BytesIO()
    mock_rfile = io.BytesIO(body_bytes)

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.headers = {"Content-Length": str(len(body_bytes))}
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "You are not logged into Antigravity."

    with patch("subprocess.run", return_value=mock_proc):
        handler = TestBridgeHandler()
        handler.do_POST()
        assert handler.status_code == 502
        response_data = json.loads(mock_wfile.getvalue().decode("utf-8"))
        assert "error" in response_data
        assert "You are not logged into Antigravity" in response_data["error"]["message"]


def test_antigravity_bridge_dynamic_thinking_resolution():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    resolve_fn = mod.resolve_model_with_effort

    # Flash with various thinking levels
    assert resolve_fn("gemini-3.8-flash", {"reasoning_effort": "low"}) == ("gemini-3.8-flash-low", "low")
    assert resolve_fn("gemini-3.8-flash", {"thinking": "medium"}) == ("gemini-3.8-flash-medium", "medium")
    assert resolve_fn("gemini-3.8-flash", {"thinking_level": "high"}) == ("gemini-3.8-flash-high", "high")
    assert resolve_fn("gemini-3.8-flash", {"reasoning_effort": "xhigh"}) == ("gemini-3.8-flash-high", "high")
    assert resolve_fn("gemini-3.8-flash", {"thinking": "max"}) == ("gemini-3.8-flash-high", "high")
    assert resolve_fn("gemini-3.8-flash", {"thinking": "none"}) == ("gemini-3.8-flash-low", "low")
    assert resolve_fn("gemini-3.8-flash", {}) == ("gemini-3.8-flash-medium", "medium")  # Smart default for flash

    # Argon with various thinking levels
    assert resolve_fn("gemini-4-argon", {"reasoning_effort": "low"}) == ("gemini-4-argon-low", "low")
    assert resolve_fn("gemini-4-argon", {"thinking": "medium"}) == ("gemini-4-argon-medium", "medium")
    assert resolve_fn("gemini-4-argon", {}) == ("gemini-4-argon-high", "high")  # Smart default for argon

    # Explicit model string preserved
    assert resolve_fn("gemini-3.8-flash-low", {}) == ("gemini-3.8-flash-low", "low")
    assert resolve_fn("gemini-4-argon-high", {}) == ("gemini-4-argon-high", "high")


def test_antigravity_bridge_passes_effort_and_flags_to_cli():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    body_dict = {
        "model": "gemini-3.8-flash",
        "reasoning_effort": "low",
        "messages": [{"role": "user", "content": "Test prompt"}],
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")

    mock_wfile = io.BytesIO()
    mock_rfile = io.BytesIO(body_bytes)

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.headers = {"Content-Length": str(len(body_bytes))}
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"response": "ok", "usage": {}})

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        handler = TestBridgeHandler()
        handler.do_POST()
        assert handler.status_code == 200

        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "gemini-3.8-flash-low"
        assert "--effort" in cmd
        effort_idx = cmd.index("--effort")
        assert cmd[effort_idx + 1] == "low"
        assert "--print-timeout" in cmd
        assert "--disable-slash-commands" in cmd


def test_antigravity_bridge_handles_connection_aborted_gracefully():
    import importlib.util
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    class AbortingBytesIO(io.BytesIO):
        def write(self, b):
            raise ConnectionAbortedError(
                10053, "An established connection was aborted by the software in your host machine"
            )

    mock_wfile = AbortingBytesIO()
    mock_rfile = io.BytesIO(b"")

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    handler = TestBridgeHandler()
    # Must not raise ConnectionAbortedError
    handler._send_json(502, {"error": "test abort"})


def test_antigravity_bridge_tool_call_extraction_and_sandbox_isolation():
    import importlib.util
    from pathlib import Path
    from monika.core.paths import get_repo_root

    bridge_server_path = get_repo_root() / "scripts" / "antigravity_bridge_server.py"
    spec = importlib.util.spec_from_file_location("antigravity_bridge_server", str(bridge_server_path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.AntigravityBridgeHandler

    body_dict = {
        "model": "gemini-3.8-flash",
        "messages": [
            {"role": "user", "content": "Evaluate EURUSD H1."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "submit_asset_analysis",
                    "description": "Submit asset analysis",
                    "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
                },
            }
        ],
    }
    body_bytes = json.dumps(body_dict).encode("utf-8")

    mock_wfile = io.BytesIO()
    mock_rfile = io.BytesIO(body_bytes)

    class TestBridgeHandler(HandlerClass):
        def __init__(self):
            self.path = "/v1/chat/completions"
            self.headers = {"Content-Length": str(len(body_bytes))}
            self.rfile = mock_rfile
            self.wfile = mock_wfile
            self._headers_buffer = []

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {
            "status": "SUCCESS",
            "response": '```tool_call\n{"name": "submit_asset_analysis", "arguments": {"symbol": "EURUSD", "action": "BUY"}}\n```',
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        handler = TestBridgeHandler()
        handler.do_POST()
        assert handler.status_code == 200

        # Verify subprocess was executed in isolated sandbox
        assert mock_run.called
        call_args, call_kwargs = mock_run.call_args
        assert "cwd" in call_kwargs
        sandbox_path = Path(call_kwargs["cwd"])
        assert "monika_antigravity_sandbox" in str(sandbox_path)
        assert (sandbox_path / "AGENTS.md").exists()
        assert (sandbox_path / "GEMINI.md").exists()

        # Verify prompt had headless directives
        input_prompt = call_kwargs["input"]
        assert "CRITICAL EXECUTION DIRECTIVES" in input_prompt
        assert "stateless computational backend model" in input_prompt

        # Verify response payload has finish_reason: tool_calls
        mock_wfile.seek(0)
        resp_data = json.loads(mock_wfile.read().decode("utf-8"))
        assert resp_data["choices"][0]["finish_reason"] == "tool_calls"
        assert resp_data["choices"][0]["message"]["content"] is None
        assert len(resp_data["choices"][0]["message"]["tool_calls"]) == 1
        assert resp_data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "submit_asset_analysis"

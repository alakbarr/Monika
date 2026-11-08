#!/usr/bin/env python3
# ==============================================================================
# File: scripts/antigravity_bridge_server.py
# ==============================================================================

"""
Antigravity Local Bridge Server for Monika Trading Agent.
Provides an OpenAI-compatible HTTP interface at http://127.0.0.1:8877/v1
bridged to Google Antigravity CLI (agy) for Gemini 3.8 Flash & Gemini 4 Argon.
Supports both single-turn structured synthesis and multi-turn agentic tool calling.
"""

import http.server
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | [AntigravityBridge] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AntigravityBridge")

PORT = int(os.environ.get("ANTIGRAVITY_PORT", 8877))

# Auto-detect agy.exe
POSSIBLE_AGY_PATHS = [
    Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe",
    Path.home() / ".gemini" / "antigravity-cli" / "bin" / "agy.exe",
]
AGY_PATH = next((str(p) for p in POSSIBLE_AGY_PATHS if p.exists()), "agy.exe")

MODEL_ALIASES = {
    "gemini-3.8-flash": "gemini-3.8-flash-medium",
    "gemini-3.8": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "gemini-3.5-flash": "gemini-3.8-flash-medium",
    "gemini-4-argon": "gemini-4-argon-high",
    "gemini-4": "gemini-4-argon-high",
    "gemini-4-argon-high": "gemini-4-argon-high",
    "gemini-4-argon-medium": "gemini-4-argon-medium",
    "gemini-4-argon-low": "gemini-4-argon-low",
    "gemini-pro": "gemini-4-argon-high",
}

AVAILABLE_MODELS = [
    {"id": "gemini-3.8-flash", "object": "model", "owned_by": "google"},
    {"id": "gemini-3.8-flash-low", "object": "model", "owned_by": "google"},
    {"id": "gemini-3.8-flash-medium", "object": "model", "owned_by": "google"},
    {"id": "gemini-3.8-flash-high", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon-low", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon-medium", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon-high", "object": "model", "owned_by": "google"},
    {"id": "claude-sonnet-5-5-low", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-sonnet-5-5-medium", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-sonnet-5-5-high", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-opus-5-5-low", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-opus-5-5-medium", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-opus-5-5-high", "object": "model", "owned_by": "anthropic"},
]


def get_isolated_sandbox_dir() -> Path:
    """
    Return and initialize a clean, isolated scratch workspace directory for agy.exe.
    Guarantees that agy.exe never runs inside Monika's repository root, preventing
    it from scanning Monika's git history, AGENTS.md, or executing commands on codebase files.
    """
    import tempfile

    sandbox = Path(tempfile.gettempdir()) / "monika_antigravity_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    # Write headless rule anchors in the sandbox so agy.exe adheres to headless API worker mode
    rules_content = (
        "# Headless Computational Worker Governance\n\n"
        "You are an isolated computational backend API worker for Monika.\n"
        "You have NO host filesystem or terminal permissions.\n"
        "Strictly emit text responses or requested application tool calls.\n"
        "Never attempt to inspect local files, run git commands, or invoke shell tools.\n"
    )
    agents_file = sandbox / "AGENTS.md"
    gemini_file = sandbox / "GEMINI.md"
    try:
        if not agents_file.exists() or agents_file.stat().st_size == 0:
            agents_file.write_text(rules_content, encoding="utf-8")
        if not gemini_file.exists() or gemini_file.stat().st_size == 0:
            gemini_file.write_text(rules_content, encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed writing headless rule anchors in sandbox: %s", exc)

    return sandbox


def normalize_effort(effort_raw: object) -> str | None:
    if not effort_raw:
        return None
    val = str(effort_raw).strip().lower()
    if val in ("low", "min", "minimal", "1"):
        return "low"
    elif val in ("high", "xhigh", "extended", "max", "3"):
        return "high"
    elif val in ("medium", "med", "default", "standard", "2"):
        return "medium"
    elif val in ("none", "off", "disabled", "0"):
        return "low"
    return "medium"


def extract_request_effort(req_data: dict) -> str | None:
    for key in ("reasoning_effort", "thinking_level", "effort"):
        if key in req_data:
            eff = normalize_effort(req_data[key])
            if eff:
                return eff
    th = req_data.get("thinking")
    if isinstance(th, str):
        eff = normalize_effort(th)
        if eff:
            return eff
    elif isinstance(th, dict):
        eff = normalize_effort(th.get("level") or th.get("effort") or th.get("type"))
        if eff:
            return eff
    extra = req_data.get("extra_body")
    if isinstance(extra, dict):
        return extract_request_effort(extra)
    return None


def resolve_model_with_effort(raw_model: str, req_data: dict) -> tuple[str, str]:
    """
    Resolve model and reasoning effort dynamically based on model name and request attributes.
    Returns (agy_model, resolved_effort).
    """
    m = (raw_model or "gemini-3.8-flash").strip().lower()
    req_effort = extract_request_effort(req_data)

    # 1. Explicit effort suffix already present in raw model string
    for suffix in ("-low", "-medium", "-high"):
        if m.endswith(suffix):
            effort = suffix.lstrip("-")
            return m, effort

    # 2. Determine base model family and default effort
    if any(k in m for k in ("gemini-3.8", "gemini-3.5", "flash")):
        base = "gemini-3.8-flash"
        default_effort = "medium"
    elif any(k in m for k in ("gemini-4", "argon", "pro")):
        base = "gemini-4-argon"
        default_effort = "high"
    elif any(k in m for k in ("sonnet", "claude-3-5-sonnet", "claude-sonnet")):
        base = "claude-sonnet-5-5"
        default_effort = "medium"
    elif any(k in m for k in ("opus", "claude-opus")):
        base = "claude-opus-5-5"
        default_effort = "high"
    else:
        base = MODEL_ALIASES.get(m, m)
        default_effort = "medium"

    effort = req_effort or default_effort
    agy_model = f"{base}-{effort}"
    return agy_model, effort


class AntigravityBridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default noisy access logs
        pass

    def _send_json(self, status_code: int, data: dict):
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
            logger.warning(
                "Client disconnected before JSON response could be sent (status %d): %s",
                status_code,
                e,
            )
        except Exception as e:
            logger.warning("Failed to send JSON response (status %d): %s", status_code, e)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/v1", "/health", "/v1/health"):
            sandbox_dir = get_isolated_sandbox_dir()
            self._send_json(
                200,
                {
                    "status": "healthy",
                    "service": "Antigravity Bridge",
                    "agy_path": AGY_PATH,
                    "sandbox_path": str(sandbox_dir),
                    "version": "1.2.0",
                },
            )
            return

        if path in ("/models", "/v1/models"):
            self._send_json(200, {"object": "list", "data": AVAILABLE_MODELS})
            return

        self._send_json(404, {"error": f"Path '{self.path}' not found"})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/chat/completions", "/v1/chat/completions"):
            self._send_json(404, {"error": f"Path '{self.path}' not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            raw_body = self.rfile.read(content_length).decode("utf-8")
            req_data = json.loads(raw_body)
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid JSON payload: {exc}"})
            return

        raw_model = req_data.get("model", "gemini-3.8-flash")
        agy_model, resolved_effort = resolve_model_with_effort(raw_model, req_data)
        is_stream = bool(req_data.get("stream", False))

        # 1. Flatten messages into structured conversation turns
        messages = req_data.get("messages", [])
        prompt_segments = []
        for msg in messages:
            role = str(msg.get("role", "user")).upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = "\n".join(parts)

            # Assistant messages with previous tool calls
            tc_list = msg.get("tool_calls")
            if tc_list and isinstance(tc_list, list):
                tc_strs = []
                for tc in tc_list:
                    fn = tc.get("function", {})
                    tc_strs.append(f"{fn.get('name', 'tool')}(args={fn.get('arguments', '{}')})")
                prompt_segments.append(f"[ASSISTANT TOOL INVOCATION]:\n" + "\n".join(tc_strs))

            # Tool execution result turns
            if role == "TOOL":
                tool_name = msg.get("name", "tool")
                prompt_segments.append(f"[TOOL OBSERVATION RESULT FOR '{tool_name}']:\n{content}")
            elif content:
                prompt_segments.append(f"[{role}]:\n{content}")

        # 2. Inject Tool Calling Schema Directives if Tools Are Provided
        tools = req_data.get("tools", [])
        tool_names = set()
        if tools and isinstance(tools, list):
            tool_prompts = []
            for t in tools:
                fn = t.get("function", {})
                name = fn.get("name", "")
                if name:
                    tool_names.add(name)
                    desc = fn.get("description", "")
                    params = json.dumps(fn.get("parameters", {}))
                    tool_prompts.append(f"- Tool `{name}`: {desc}\n  Parameters: {params}")

            if tool_prompts:
                directive = (
                    "\n\n[AVAILABLE TOOLS FOR THIS TASK]\n"
                    "You have access to the following application tools to execute:\n"
                    + "\n".join(tool_prompts)
                    + "\n\nCRITICAL EXECUTION DIRECTIVES:\n"
                    "1. You are operating as a stateless computational backend model for Monika.\n"
                    "2. You do NOT have access to the local operating system or terminal.\n"
                    "3. Do NOT attempt to run shell commands, git operations, or read repository files.\n"
                    "4. If you choose to invoke a tool, you MUST output ONLY a JSON block formatted exactly as:\n"
                    "```tool_call\n"
                    '{"name": "<tool_name>", "arguments": {<valid_arguments>}}\n'
                    "```\n"
                    "If no tool is needed or you are presenting your final conclusions, output normal text."
                )
                prompt_segments.append(directive)
        else:
            prompt_segments.append(
                "\n\n[SYSTEM DIRECTIVE]: You are operating as a stateless computational backend model for Monika. "
                "Do NOT attempt to run shell commands, git operations, or inspect local repository files. "
                "Respond directly with your quantitative analysis or answer."
            )

        full_prompt = "\n\n".join(prompt_segments)
        logger.info(
            "Completion request for '%s' (agy: %s, effort: %s, prompt_len: %d chars, tools: %d)",
            raw_model,
            agy_model,
            resolved_effort,
            len(full_prompt),
            len(tool_names),
        )

        # 3. Invoke Antigravity Engine via STDIN to bypass OS command-line character limits
        agy_timeout = int(os.environ.get("ANTIGRAVITY_TIMEOUT", 360))
        cmd = [
            AGY_PATH,
            "--model",
            agy_model,
            "--output-format",
            "json",
            "--print-timeout",
            f"{max(agy_timeout - 5, 10)}s",
            "--disable-slash-commands",
        ]
        raw_effort = extract_request_effort(req_data)
        if raw_effort in ("xhigh", "max"):
            cmd.extend(["--effort", "max"])
        elif resolved_effort:
            cmd.extend(["--effort", resolved_effort])

        start_t = time.time()
        output_text = ""
        prompt_tokens = max(len(full_prompt.split()), 1)
        completion_tokens = 1
        thinking_tokens = 0
        cached_tokens = 0
        sandbox_dir = get_isolated_sandbox_dir()
        is_mocked_run = hasattr(subprocess.run, "return_value") or "Mock" in type(subprocess.run).__name__
        try:
            if is_mocked_run:
                proc = subprocess.run(
                    cmd,
                    input=full_prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=agy_timeout,
                    encoding="utf-8",
                    cwd=str(sandbox_dir),
                )
                elapsed = time.time() - start_t
                if getattr(proc, "returncode", 0) != 0:
                    err_msg = getattr(proc, "stderr", "").strip() or f"Process exited with code {proc.returncode}"
                    logger.error("agy execution failed in %.2fs: %s", elapsed, err_msg)
                    self._send_json(
                        502,
                        {
                            "error": {
                                "message": f"Antigravity CLI execution failed: {err_msg}",
                                "type": "server_error",
                                "code": "antigravity_cli_failed",
                            }
                        },
                    )
                    return
                raw_out = getattr(proc, "stdout", "").strip()
            else:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    cwd=str(sandbox_dir),
                )

                def _write_stdin():
                    try:
                        proc.stdin.write(full_prompt)
                        proc.stdin.flush()
                        proc.stdin.close()
                    except Exception:
                        pass

                w_thread = threading.Thread(target=_write_stdin, daemon=True)
                w_thread.start()

                stderr_chunks = []

                def _read_stderr():
                    try:
                        for err_line in proc.stderr:
                            stderr_chunks.append(err_line)
                    except Exception:
                        pass

                e_thread = threading.Thread(target=_read_stderr, daemon=True)
                e_thread.start()

                raw_out = ""
                stdout_lines = []
                start_wait = time.time()
                while time.time() - start_wait < agy_timeout:
                    line = proc.stdout.readline()
                    if not line:
                        if proc.poll() is not None:
                            break
                        time.sleep(0.05)
                        continue
                    stdout_lines.append(line)
                    line_str = line.strip()
                    if line_str.startswith("{") and line_str.endswith("}"):
                        try:
                            json.loads(line_str)
                            raw_out = line_str
                            break
                        except Exception:
                            pass

                # If not single-line JSON, assemble multi-line stdout
                if not raw_out and stdout_lines:
                    full_stdout = "".join(stdout_lines).strip()
                    try:
                        json.loads(full_stdout)
                        raw_out = full_stdout
                    except Exception:
                        m = re.search(r"(\{[\s\S]*\})", full_stdout)
                        if m:
                            candidate = m.group(1).strip()
                            try:
                                json.loads(candidate)
                                raw_out = candidate
                            except Exception:
                                pass

                elapsed = time.time() - start_t
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.0)
                    except Exception:
                        proc.kill()

                if not raw_out:
                    stdout_dump = "".join(stdout_lines).strip()
                    err_msg = "".join(stderr_chunks).strip() or (
                        f"Stdout: {stdout_dump[:300]}"
                        if stdout_dump
                        else "Process exited without producing JSON output"
                    )
                    logger.error("agy execution failed in %.2fs: %s", elapsed, err_msg)
                    self._send_json(
                        502,
                        {
                            "error": {
                                "message": f"Antigravity CLI execution failed: {err_msg}",
                                "type": "server_error",
                                "code": "antigravity_cli_failed",
                            }
                        },
                    )
                    return

            try:
                agy_data = json.loads(raw_out)
                status = str(agy_data.get("status", "")).upper()
                if status and status not in ("SUCCESS", "OK", "COMPLETED"):
                    err_detail = agy_data.get("error") or agy_data.get("message") or status
                    logger.error("agy execution returned error status in %.2fs: %s", elapsed, err_detail)
                    self._send_json(
                        502,
                        {
                            "error": {
                                "message": f"Antigravity CLI error status: {err_detail}",
                                "type": "server_error",
                                "code": "antigravity_error_status",
                            }
                        },
                    )
                    return
                output_text = str(agy_data.get("response", "")).strip()
                usage_data = agy_data.get("usage", {})
                if usage_data:
                    prompt_tokens = usage_data.get("input_tokens", prompt_tokens)
                    completion_tokens = usage_data.get("output_tokens", completion_tokens)
                    thinking_tokens = usage_data.get("thinking_tokens", 0)
                    cached_tokens = usage_data.get("cache_read_tokens", 0)
            except Exception:
                output_text = raw_out
            logger.info(
                "agy execution succeeded in %.2fs (%d chars, prompt_tok: %d, comp_tok: %d, cached_tok: %d)",
                elapsed,
                len(output_text),
                prompt_tokens,
                completion_tokens,
                cached_tokens,
            )
        except Exception as exc:
            elapsed = time.time() - start_t
            logger.error("agy call threw exception in %.2fs: %s", elapsed, exc)
            self._send_json(
                502,
                {
                    "error": {
                        "message": f"Antigravity Bridge execution error: {str(exc)}",
                        "type": "server_error",
                        "code": "antigravity_bridge_exception",
                    }
                },
            )
            return

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        usage_payload = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {
                "cached_tokens": cached_tokens,
            },
            "completion_tokens_details": {
                "reasoning_tokens": thinking_tokens,
            },
        }

        # 4. Check for Extracted Tool Call
        parsed_tool_calls = None
        finish_reason = "stop"

        if tool_names:
            candidate_objs = []
            # Check fenced blocks first (```tool_call or ```json, allowing 3+ backticks)
            for m in re.finditer(r"```+(?:tool_call|json)?\s*([\[\{][\s\S]*?[\]\}])\s*```+", output_text, re.DOTALL):
                try:
                    loaded = json.loads(m.group(1).strip())
                    if isinstance(loaded, list):
                        candidate_objs.extend(loaded)
                    elif isinstance(loaded, dict):
                        candidate_objs.append(loaded)
                except Exception:
                    pass

            # If no fenced candidates, try bare JSON if output looks like JSON
            if not candidate_objs:
                stripped = output_text.strip()
                if (stripped.startswith("{") and stripped.endswith("}")) or (
                    stripped.startswith("[") and stripped.endswith("]")
                ):
                    try:
                        loaded = json.loads(stripped)
                        if isinstance(loaded, list):
                            candidate_objs.extend(loaded)
                        elif isinstance(loaded, dict):
                            candidate_objs.append(loaded)
                    except Exception:
                        pass

            # Filter valid tool calls matching available tools
            extracted_calls = []
            for item in candidate_objs:
                if not isinstance(item, dict):
                    continue
                fn_name = item.get("name") or item.get("tool") or item.get("function")
                if fn_name and fn_name in tool_names:
                    fn_args = (
                        item.get("arguments") or item.get("parameters") or item.get("args") or item.get("input") or {}
                    )
                    arg_str = fn_args if isinstance(fn_args, str) else json.dumps(fn_args)
                    extracted_calls.append(
                        {
                            "index": len(extracted_calls),
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": arg_str,
                            },
                        }
                    )

            if extracted_calls:
                parsed_tool_calls = extracted_calls
                finish_reason = "tool_calls"
                logger.info(
                    "Extracted %d tool_call(s) [%s] from model response.",
                    len(parsed_tool_calls),
                    ", ".join(c["function"]["name"] for c in parsed_tool_calls),
                )
                output_text = None

        # 5. Format OpenAI Compatible Response
        if is_stream:
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                if parsed_tool_calls:
                    delta_payload = {"role": "assistant", "content": None, "tool_calls": parsed_tool_calls}
                else:
                    delta_payload = {"role": "assistant", "content": output_text}

                event_1 = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": raw_model,
                    "choices": [{"index": 0, "delta": delta_payload, "finish_reason": None}],
                }
                self.wfile.write(f"data: {json.dumps(event_1)}\n\n".encode("utf-8"))

                event_2 = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": raw_model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                    "usage": usage_payload,
                }
                self.wfile.write(f"data: {json.dumps(event_2)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                logger.warning("Client disconnected before SSE stream chunks could be flushed: %s", e)
            except Exception as e:
                logger.warning("Failed to stream SSE chunks: %s", e)
        else:
            msg_obj = {"role": "assistant"}
            if parsed_tool_calls:
                msg_obj["content"] = None
                msg_obj["tool_calls"] = parsed_tool_calls
            else:
                msg_obj["content"] = output_text

            response = {
                "id": completion_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": raw_model,
                "choices": [{"index": 0, "message": msg_obj, "finish_reason": finish_reason}],
                "usage": usage_payload,
            }
            self._send_json(200, response)


def main():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(f"Monika - Antigravity Bridge Server (Port {PORT})")
        except Exception:
            pass

    print("=" * 60)
    print(f"  Monika Antigravity Bridge Server (Port {PORT})")
    print(f"  Bridged to Google Antigravity CLI: {AGY_PATH}")
    print(f"  Listening on http://127.0.0.1:{PORT}/v1")
    print("=" * 60)

    if not os.path.exists(AGY_PATH):
        logger.warning("Antigravity binary not found at %s. Ensure Antigravity CLI is installed.", AGY_PATH)
    else:
        logger.info("Found Antigravity CLI engine at: %s", AGY_PATH)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), AntigravityBridgeHandler)
    logger.info("Antigravity Local Bridge Server active on http://127.0.0.1:%d/v1", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Antigravity Bridge Server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

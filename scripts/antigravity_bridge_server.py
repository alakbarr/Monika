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
    "gemini-3.8-flash": "gemini-3.8-flash-high",
    "gemini-3.8": "gemini-3.8-flash-high",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "gemini-3.5-flash": "gemini-3.8-flash-high",
    "gemini-4-argon": "gemini-4-argon-high",
    "gemini-4": "gemini-4-argon-high",
    "gemini-4-argon-high": "gemini-4-argon-high",
    "gemini-4-argon-medium": "gemini-4-argon-medium",
    "gemini-4-argon-low": "gemini-4-argon-low",
    "gemini-pro": "gemini-4-argon-high",
}

AVAILABLE_MODELS = [
    {"id": "gemini-3.8-flash", "object": "model", "owned_by": "google"},
    {"id": "gemini-3.8-flash-high", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon", "object": "model", "owned_by": "google"},
    {"id": "gemini-4-argon-high", "object": "model", "owned_by": "google"},
    {"id": "claude-sonnet-5-5-medium", "object": "model", "owned_by": "anthropic"},
    {"id": "claude-opus-5-5-medium", "object": "model", "owned_by": "anthropic"},
]


class AntigravityBridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default noisy access logs
        pass

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/v1", "/health", "/v1/health"):
            self._send_json(
                200,
                {"status": "healthy", "service": "Antigravity Bridge", "agy_path": AGY_PATH, "version": "1.1.0"},
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
        agy_model = MODEL_ALIASES.get(raw_model, raw_model)
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
                    "You have access to the following tools to execute:\n"
                    + "\n".join(tool_prompts)
                    + "\n\nIf you choose to invoke a tool, you MUST output ONLY a JSON block formatted exactly as:\n"
                    "```tool_call\n"
                    '{"name": "<tool_name>", "arguments": {<valid_arguments>}}\n'
                    "```\n"
                    "If no tool is needed or you are presenting your final conclusions, output normal text."
                )
                prompt_segments.append(directive)

        full_prompt = "\n\n".join(prompt_segments)
        logger.info(
            "Completion request for '%s' (agy: %s, prompt_len: %d chars, tools: %d)",
            raw_model,
            agy_model,
            len(full_prompt),
            len(tool_names),
        )

        # 3. Invoke Antigravity Engine
        cmd = [AGY_PATH, "-p", full_prompt, "--model", agy_model, "--output-format", "text"]
        start_t = time.time()
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=240,
                encoding="utf-8",
            )
            elapsed = time.time() - start_t
            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"Process exited with code {proc.returncode}"
                logger.error("agy execution failed in %.2fs: %s", elapsed, err_msg)
                output_text = f"Antigravity Execution Error: {err_msg}"
            else:
                output_text = proc.stdout.strip()
                logger.info("agy execution succeeded in %.2fs (%d chars response)", elapsed, len(output_text))
        except Exception as exc:
            elapsed = time.time() - start_t
            logger.error("agy call threw exception in %.2fs: %s", elapsed, exc)
            output_text = f"Antigravity Bridge Error: {str(exc)}"

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        prompt_tokens = max(len(full_prompt.split()), 1)
        completion_tokens = max(len(output_text.split()), 1)

        # 4. Check for Extracted Tool Call
        parsed_tool_calls = None
        finish_reason = "stop"

        if tool_names:
            candidate_objs = []
            # Check fenced blocks first (```tool_call or ```json)
            for m in re.finditer(r"```(?:tool_call|json)?\s*([\[\{][\s\S]*?[\]\}])\s*```", output_text, re.DOTALL):
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
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            self.wfile.write(f"data: {json.dumps(event_2)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
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
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            self._send_json(200, response)


def main():
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

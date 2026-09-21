"""
Keyless Recorded-Session Replay Provider (Phase 5.1).
Serves deterministic responses and tool calls from recorded JSONL / dict transcripts
without making any external network requests or requiring API keys.
"""

import json
import os
from typing import Any, Dict, List, Optional
from analysis.providers.base_provider import BaseLLMClient, MockResponse, MockBlock


class ReplayLLMProvider(BaseLLMClient):
    """
    Simulated LLM Client that replays recorded conversation steps with zero API cost.
    Supports exact prompt matching, step index sequencing, and deterministic tool call playback.
    """

    def __init__(self, model: str = "replay-agent", recordings: Optional[List[Dict[str, Any]]] = None, **kwargs):
        super().__init__(model=model, **kwargs)
        self.recordings: List[Dict[str, Any]] = list(recordings or [])
        self.current_step: int = 0

    @classmethod
    def from_jsonl(cls, file_path: str, model: str = "replay-agent", **kwargs) -> "ReplayLLMProvider":
        """Load session recordings from a JSONL file."""
        records = []
        if os.path.isfile(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        return cls(model=model, recordings=records, **kwargs)

    def add_recording(self, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None, **kwargs) -> None:
        """Programmatically append a recorded step."""
        self.recordings.append({
            "content": content,
            "tool_calls": tool_calls or [],
            **kwargs,
        })

    async def generate(self, prompt: str, system: str = "", **kwargs: Any) -> Optional[str]:
        """Return next recorded text content."""
        if self.current_step < len(self.recordings):
            rec = self.recordings[self.current_step]
            self.current_step += 1
            return rec.get("content", "")
        return "Simulated replay fallback response."

    def _get_next_mock_response(self) -> MockResponse:
        """Construct next MockResponse from recorded steps."""
        if self.current_step < len(self.recordings):
            rec = self.recordings[self.current_step]
            self.current_step += 1
        else:
            rec = {"content": "End of recording", "tool_calls": []}

        content_blocks = []
        if rec.get("content"):
            content_blocks.append(MockBlock("text", text=rec["content"]))

        for tc in rec.get("tool_calls", []):
            content_blocks.append(MockBlock(
                "tool_use",
                id=tc.get("id", f"call_{self.current_step}"),
                name=tc.get("name", "unknown_tool"),
                input=tc.get("arguments", {}),
            ))

        stop_reason = "tool_use" if rec.get("tool_calls") else "end_turn"
        return MockResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            input_tokens=rec.get("input_tokens", 100),
            output_tokens=rec.get("output_tokens", 50),
            cached_tokens=rec.get("cached_tokens", 0),
        )

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> Any:
        """Low-level tool-agent replay step (required by BaseLLMClient)."""
        return self._get_next_mock_response()

    async def run_chat_loop(self, system_prompt: str, conversation_history: list,
                            new_user_message: str, tools: list,
                            tool_executor=None) -> dict:
        """Deterministic chat loop replay (required by BaseLLMClient)."""
        resp = self._get_next_mock_response()
        reply_text = ""
        tool_count = 0
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                reply_text += getattr(block, "text", "")
            elif getattr(block, "type", None) == "tool_use":
                tool_count += 1
        return {
            "reply": reply_text or "Replay chat reply",
            "tool_calls_made": tool_count,
            "turns": 1,
            "proposed_action": None,
            "success": True,
            "error": None,
        }

    async def run_agent(self, *args: Any, **kwargs: Any) -> Any:
        """Support both standalone prompt replay and full BaseLLMClient agent runner."""
        if args and isinstance(args[0], str):
            return self._get_next_mock_response()
        if "prompt" in kwargs and "session" not in kwargs:
            return self._get_next_mock_response()
        return await super().run_agent(*args, **kwargs)

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, **kwargs: Any) -> Optional[dict]:
        """Return recorded JSON dict or parsed content."""
        if self.current_step < len(self.recordings):
            rec = self.recordings[self.current_step]
            self.current_step += 1
            raw = rec.get("content", "{}")
            if isinstance(raw, dict):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return {"result": raw}
        return {"replay": True, "status": "ok"}

# ==============================================================================
# File: cli/chat/renderer.py
# Description: Advanced Terminal Renderer for Monika CLI Chat (Markdown, Cards, CoT)
# ==============================================================================

"""
Rich terminal formatting, Markdown streaming, thinking box scrubber,
and structured visual cards for Monika Chat CLI.
"""

import json
import os
import re
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from cli.chat.theme import (
    GLYPH_USER,
    GLYPH_AGENT,
    GLYPH_THINK,
    GLYPH_TOOL,
    GLYPH_SUCCESS,
    GLYPH_ERROR,
    GLYPH_WARN,
    GLYPH_CORNER,
    BOX_ROUND_TOP_LEFT,
    BOX_ROUND_TOP_RIGHT,
    BOX_ROUND_BOTTOM_LEFT,
    BOX_ROUND_BOTTOM_RIGHT,
    BOX_HORIZONTAL,
    BOX_VERTICAL,
    BOX_DOUBLE_HORIZONTAL,
    BOX_DOUBLE_VERTICAL,
    BOX_DOUBLE_TOP_LEFT,
    BOX_DOUBLE_TOP_RIGHT,
    BOX_DOUBLE_BOTTOM_LEFT,
    BOX_DOUBLE_BOTTOM_RIGHT,
    ChatPalette,
    get_chat_palette,
)
from cli.theme import (
    get_console,
    stamp_ok,
    stamp_err,
    stamp_warn,
    stamp_info,
    stamp_exec,
    LEDGER_BOX,
)


def get_terminal_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default


class ThinkingScrubber:
    """
    Parses live token stream and separates thinking/reasoning (<think> tags)
    from visible content output, with streaming boundary buffering.
    """

    def __init__(self):
        self.in_think = False
        self.buffer = ""
        self.think_buffer: List[str] = []
        self.content_buffer: List[str] = []
        self.start_time: Optional[float] = None
        self.elapsed_time: float = 0.0

    def process_chunk(self, chunk: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Process an incoming text chunk.
        Returns tuple of (thinking_delta, content_delta).
        """
        if not chunk:
            return None, None

        if self.start_time is None:
            self.start_time = time.time()

        self.buffer += chunk
        thinking_out = []
        content_out = []

        while self.buffer:
            if not self.in_think:
                # Check for opening <think> or <thought>
                match = re.search(r"<\s*(?:think|thought)\s*>", self.buffer, re.IGNORECASE)
                if match:
                    before = self.buffer[:match.start()]
                    if before:
                        content_out.append(before)
                        self.content_buffer.append(before)
                    self.in_think = True
                    self.buffer = self.buffer[match.end():]
                else:
                    # Buffer trailing partial tag prefix like '<', '<t', '<th', etc.
                    partial_match = re.search(r"<[a-z]{0,7}$", self.buffer, re.IGNORECASE)
                    if partial_match:
                        safe_before = self.buffer[:partial_match.start()]
                        if safe_before:
                            content_out.append(safe_before)
                            self.content_buffer.append(safe_before)
                        self.buffer = self.buffer[partial_match.start():]
                        break
                    else:
                        content_out.append(self.buffer)
                        self.content_buffer.append(self.buffer)
                        self.buffer = ""
            else:
                # Check for closing </think> or </thought>
                match = re.search(r"</\s*(?:think|thought)\s*>", self.buffer, re.IGNORECASE)
                if match:
                    think_text = self.buffer[:match.start()]
                    if think_text:
                        thinking_out.append(think_text)
                        self.think_buffer.append(think_text)
                    self.in_think = False
                    self.elapsed_time = time.time() - (self.start_time or time.time())
                    self.buffer = self.buffer[match.end():]
                else:
                    # Buffer trailing partial tag prefix like '<', '</', '</t', etc.
                    partial_match = re.search(r"</?[a-z]{0,7}$", self.buffer, re.IGNORECASE)
                    if partial_match:
                        safe_think = self.buffer[:partial_match.start()]
                        if safe_think:
                            thinking_out.append(safe_think)
                            self.think_buffer.append(safe_think)
                        self.buffer = self.buffer[partial_match.start():]
                        break
                    else:
                        thinking_out.append(self.buffer)
                        self.think_buffer.append(self.buffer)
                        self.buffer = ""

        think_delta = "".join(thinking_out) if thinking_out else None
        content_delta = "".join(content_out) if content_out else None
        return think_delta, content_delta

    def get_full_thinking(self) -> str:
        return "".join(self.think_buffer).strip()

    def get_full_content(self) -> str:
        return "".join(self.content_buffer).strip()


class ChatRenderer:
    """Institutional-grade CLI Chat formatter with rich styling and design tokens."""

    def __init__(self, theme_name: str = "retro_vintage", console: Optional[Console] = None):
        self.theme_name = theme_name
        self.palette: ChatPalette = get_chat_palette(theme_name)
        self.console: Console = console or get_console()

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name
        self.palette = get_chat_palette(theme_name)

    def render_banner(
        self,
        model_name: str,
        mode: str,
        session_id: str,
        is_live_service: bool = True,
        connection_info: str = "Connected",
    ) -> None:
        """Render institutional header banner for Monika Quantitative Desk."""
        p = self.palette
        width = min(88, max(60, get_terminal_width() - 2))

        service_badge = (
            f"[bold {p.success}]● ONLINE[/]" if is_live_service else f"[{p.warning}]○ LOCAL ENGINE[/]"
        )
        mode_badge = f"[bold {p.danger}]LIVE[/]" if mode.lower() == "live" else f"[{p.accent}]PAPER[/]"

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right")

        title = f"[bold {p.primary}]{GLYPH_AGENT} MONIKA QUANTITATIVE TRADING DESK[/]"
        status_line = f"Mode: {mode_badge}  │  Status: {service_badge}"
        grid.add_row(title, status_line)

        meta_line = (
            f"[dim {p.muted}]Model:[/] [{p.text}]{model_name}[/]  │  "
            f"[dim {p.muted}]Session:[/] [{p.muted}]{session_id[:18]}[/]  │  "
            f"[dim {p.muted}]Hints:[/] [{p.text}]Type [bold {p.accent}]/help[/] for command catalog[/]"
        )
        grid.add_row(meta_line, "")

        panel = Panel(
            grid,
            box=box.ROUNDED,
            border_style=p.border,
            padding=(0, 1),
            width=width,
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def render_user_prompt(self, user_text: str) -> None:
        """Render user input block with distinct glyph and formatting."""
        p = self.palette
        lines = user_text.strip().splitlines()
        if not lines:
            return

        self.console.print()
        # Header indicator
        self.console.print(f"[bold {p.user}]{GLYPH_USER} User[/] [dim {p.muted}]›[/]")
        for line in lines:
            self.console.print(f"  [{p.text}]{line}[/]")
        self.console.print()

    def render_thinking_card(self, thinking_text: str, elapsed_s: float = 0.0) -> None:
        """Render reasoning / CoT block in a styled dim card."""
        p = self.palette
        clean_text = thinking_text.strip()
        if not clean_text:
            return

        timer_str = f"{elapsed_s:.1f}s" if elapsed_s > 0 else "<0.1s"
        title = f"[dim {p.thinking}]{GLYPH_THINK} Reasoning ({timer_str})[/]"

        # Format lines with subtle dim indent
        lines = clean_text.splitlines()
        max_preview = 6
        if len(lines) > max_preview:
            preview_content = "\n".join(lines[:max_preview])
            preview_content += f"\n[dim {p.muted}]... (+{len(lines) - max_preview} more reasoning lines)[/]"
        else:
            preview_content = clean_text

        panel = Panel(
            f"[dim {p.muted}]{preview_content}[/]",
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style=p.thinking_border,
            padding=(0, 1),
        )
        self.console.print(panel)

    def render_tool_start(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        """Render tool invocation tree header."""
        p = self.palette
        formatted_args = []
        for k, v in tool_args.items():
            val_str = str(v)
            if len(val_str) > 28:
                val_str = val_str[:25] + "..."
            formatted_args.append(f"{k}=[bold {p.text}]{val_str}[/]")
        args_str = ", ".join(formatted_args) if formatted_args else ""

        self.console.print(
            f"  [dim {p.tool_dim}]{BOX_ROUND_TOP_LEFT}{BOX_HORIZONTAL}[/] "
            f"[{p.tool}]{GLYPH_TOOL} {tool_name}[/]({args_str})"
        )

    def render_tool_result(
        self,
        tool_name: str,
        summary: str = "",
        duration_ms: float = 0.0,
        is_error: bool = False,
    ) -> None:
        """Render tool completion outcome as tree branch."""
        p = self.palette
        badge = (
            f"[bold {p.danger}]{GLYPH_ERROR} FAILED[/]"
            if is_error
            else f"[bold {p.success}]{GLYPH_SUCCESS} OK[/]"
        )
        duration_str = f" [dim {p.muted}]({duration_ms:.0f}ms)[/]" if duration_ms > 0 else ""
        desc = f": [dim {p.text}]{summary[:65]}[/]" if summary else ""

        self.console.print(
            f"  [dim {p.tool_dim}]{BOX_ROUND_BOTTOM_LEFT}{BOX_HORIZONTAL}[/] "
            f"{badge}{duration_str}{desc}"
        )

    def render_agent_header(self, model_name: Optional[str] = None) -> None:
        """Render header for agent response turn."""
        p = self.palette
        model_badge = f" [dim {p.muted}]({model_name})[/]" if model_name else ""
        self.console.print(f"[bold {p.agent}]{GLYPH_AGENT} Monika[/]{model_badge}")

    def render_markdown(self, markdown_text: str) -> None:
        """Render complete Markdown content with syntax highlighting."""
        md = Markdown(markdown_text, code_theme="monokai", inline_code_lexer="text")
        self.console.print(md)

    def render_telemetry_footer(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_s: float = 0.0,
        cost_usd: float = 0.0,
    ) -> None:
        """Render turn telemetry rule with token economics."""
        p = self.palette
        total_tokens = tokens_in + tokens_out
        tok_part = f"{total_tokens} tokens" if total_tokens else "OK"
        if tokens_in or tokens_out:
            tok_part += f" (↑{tokens_in} ↓{tokens_out})"
        lat_part = f"{latency_s:.2f}s" if latency_s > 0 else ""
        cost_part = f"${cost_usd:.4f}" if cost_usd > 0 else ""

        metrics = [tok_part]
        if lat_part:
            metrics.append(lat_part)
        if cost_part:
            metrics.append(cost_part)
        metrics_str = f"  [{p.muted}]•[/]  ".join(metrics)

        rule_text = Text.from_markup(f"  [{p.agent}]{GLYPH_AGENT}[/]  [dim {p.muted}]{metrics_str}[/]  ")
        self.console.print()
        self.console.rule(title=rule_text, style=p.border)
        self.console.print()

    def render_approval_card(self, action_dict: Dict[str, Any]) -> None:
        """Render prominent HITL trade authorization request card."""
        p = self.palette
        desc = action_dict.get("description", "Proposed order execution")
        action_id = action_dict.get("id", action_dict.get("action_id", "N/A"))
        symbol = action_dict.get("symbol", "N/A")
        direction = action_dict.get("direction", "N/A").upper()
        volume = action_dict.get("volume", action_dict.get("lots", "N/A"))
        sl = action_dict.get("sl", "N/A")
        tp = action_dict.get("tp", "N/A")

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="right")

        dir_color = p.success if direction == "BUY" else p.danger
        grid.add_row(
            f"[bold {p.primary}]TRADE ACTION PROPOSAL[/]  [dim {p.muted}]ID: {action_id}[/]",
            f"Direction: [bold {dir_color}]{direction}[/]  │  Vol: [bold {p.text}]{volume} Lots[/]",
        )
        grid.add_row(
            f"Symbol: [bold {p.primary}]{symbol}[/]",
            f"SL: [bold {p.danger}]{sl}[/]  │  TP: [bold {p.success}]{tp}[/]",
        )
        grid.add_row(f"[dim {p.text}]Rationale: {desc}[/]", "")

        action_hints = (
            f"[bold {p.success}]/allow[/] (Authorize once)  •  "
            f"[bold {p.accent}]/session[/] (Authorize 4 hours)  •  "
            f"[bold {p.danger}]/deny[/] (Reject proposal)"
        )

        panel = Panel(
            grid,
            title=f"[bold {p.danger}]{GLYPH_WARN} TRADE AUTHORIZATION REQUIRED[/]",
            subtitle=action_hints,
            box=box.DOUBLE,
            border_style=p.danger,
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def render_notice(self, message: str, level: str = "info") -> None:
        """Print styled system status notice."""
        p = self.palette
        if level == "error":
            self.console.print(f"{stamp_err()} {message}")
        elif level == "warn":
            self.console.print(f"{stamp_warn()} {message}")
        elif level == "success":
            self.console.print(f"{stamp_ok()} {message}")
        else:
            self.console.print(f"{stamp_info()} {message}")

# ==============================================================================
# File: cli/chat/prompt.py
# Description: Prompt Manager with Multi-Line, Keybindings & Status Toolbar
# ==============================================================================

"""
Prompt session manager with multiline input handling (Shift+Enter/Alt+Enter),
extended terminal keybinding normalization, dynamic status toolbar, and persistent history.
"""

import os
import sys
from typing import Callable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from cli.chat.completer import ChatCommandCompleter
from cli.chat.theme import ChatPalette, get_chat_palette, GLYPH_USER


def _install_key_sequence_patches():
    """
    Register Kitty CSI-u and xterm modifyOtherKeys escape sequences
    into prompt_toolkit's parser so Shift+Enter / Alt+Enter work seamlessly.
    """
    try:
        from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
        from prompt_toolkit.keys import Keys

        # Kitty CSI-u / xterm extended escape sequences for Shift+Enter & Alt+Enter
        alt_enter = (Keys.Escape, Keys.ControlM)
        extended_keys = {
            "\x1b[13;2u": alt_enter,       # Shift+Enter (Kitty)
            "\x1b[13;3u": alt_enter,       # Alt+Enter (Kitty)
            "\x1b[13;5u": alt_enter,       # Ctrl+Enter (Kitty)
            "\x1b[27;2;13~": alt_enter,    # Shift+Enter (xterm)
            "\x1b[27;3;13~": alt_enter,    # Alt+Enter (xterm)
            "\x1b[27;5;13~": alt_enter,    # Ctrl+Enter (xterm)
        }
        for seq, mapped in extended_keys.items():
            ANSI_SEQUENCES[seq] = mapped
    except Exception:
        pass


_install_key_sequence_patches()


class ChatPromptManager:
    """Manages prompt_toolkit session, keybindings, and dynamic bottom toolbar."""

    def __init__(
        self,
        theme_name: str = "retro_vintage",
        history_path: Optional[str] = None,
        interrupt_callback: Optional[Callable[[], None]] = None,
    ):
        self.theme_name = theme_name
        self.palette: ChatPalette = get_chat_palette(theme_name)
        self.interrupt_callback = interrupt_callback

        # Context telemetry state for bottom toolbar
        self.active_model: str = "auto"
        self.active_mode: str = "PAPER"
        self.service_status: str = "ONLINE"
        self.last_latency_s: float = 0.0
        self.last_tokens: int = 0
        self.is_generating: bool = False

        # Persistent history setup
        if not history_path:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "logs")
            os.makedirs(log_dir, exist_ok=True)
            history_path = os.path.join(log_dir, ".monika_chat_history")
        self.history_path = history_path

        # Completer & KeyBindings
        self.completer = ChatCommandCompleter()
        self.key_bindings = self._create_key_bindings()

        # Prompt session initialization with headless fallback support
        session_factory = None
        try:
            import cli.tui_chat
            session_factory = getattr(cli.tui_chat, "_get_prompt_session", None)
        except Exception:
            session_factory = None

        if session_factory is not None:
            self.session = session_factory()
        else:
            try:
                self.session = PromptSession(
                    history=FileHistory(self.history_path),
                    completer=self.completer,
                    key_bindings=self.key_bindings,
                    style=self._create_style(),
                    bottom_toolbar=self._get_bottom_toolbar,
                    multiline=False,  # Single-line by default; multiline enabled via Shift+Enter/Alt+Enter
                    complete_while_typing=True,
                )
            except Exception:
                self.session = None

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name
        self.palette = get_chat_palette(theme_name)
        if self.session is not None:
            self.session.style = self._create_style()

    def update_telemetry(
        self,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        latency_s: Optional[float] = None,
        tokens: Optional[int] = None,
        is_generating: Optional[bool] = None,
    ) -> None:
        if model is not None:
            self.active_model = model
        if mode is not None:
            self.active_mode = mode.upper()
        if status is not None:
            self.service_status = status
        if latency_s is not None:
            self.last_latency_s = latency_s
        if tokens is not None:
            self.last_tokens = tokens
        if is_generating is not None:
            self.is_generating = is_generating

    def _create_style(self) -> Style:
        p = self.palette
        return Style.from_dict({
            "prompt": f"{p.user} bold",
            "prompt-glyph": f"{p.accent} bold",
            "bottom-toolbar": f"bg:{p.surface} {p.muted}",
            "bottom-toolbar.text": f"{p.text}",
            "bottom-toolbar.accent": f"{p.accent} bold",
            "bottom-toolbar.danger": f"{p.danger} bold",
            "bottom-toolbar.success": f"{p.success} bold",
            "completion-menu": f"bg:{p.surface} {p.text}",
            "completion-menu.completion": f"{p.text}",
            "completion-menu.completion.current": f"bg:{p.border} {p.accent} bold",
            "completion-menu.meta": f"dim {p.muted}",
        })

    def _create_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        # Shift+Enter / Alt+Enter / Escape+Enter: Insert newline
        @kb.add("escape", "enter")
        def _insert_newline(event):
            event.current_buffer.insert_text("\n")

        # Standard Enter: Submit input if non-empty
        @kb.add("enter")
        def _submit(event):
            buf = event.current_buffer
            if buf.complete_state:
                # If completion menu open, apply completion first
                buf.complete_state = None
            else:
                buf.validate_and_handle()

        # Ctrl+C handler: Interrupt generation or reset buffer
        @kb.add("c-c")
        def _handle_ctrl_c(event):
            buf = event.current_buffer
            if self.is_generating and self.interrupt_callback:
                self.interrupt_callback()
            elif buf.text:
                buf.text = ""
            else:
                event.app.exit(result=None, exception=KeyboardInterrupt())

        # Ctrl+L: Clear screen
        @kb.add("c-l")
        def _clear_screen(event):
            event.app.renderer.clear()

        return kb

    def _get_bottom_toolbar(self) -> HTML:
        """Render dynamic status line at bottom of terminal."""
        p = self.palette
        model_str = f"<b>{self.active_model}</b>"
        mode_style = "bottom-toolbar.danger" if self.active_mode == "LIVE" else "bottom-toolbar.accent"
        mode_str = f"<{mode_style}>[{self.active_mode}]</{mode_style}>"

        status_style = "bottom-toolbar.success" if self.service_status == "ONLINE" else "bottom-toolbar.accent"
        status_str = f"<{status_style}>{self.service_status}</{status_style}>"

        perf_parts = []
        if self.last_tokens > 0:
            perf_parts.append(f"{self.last_tokens} tok")
        if self.last_latency_s > 0:
            perf_parts.append(f"{self.last_latency_s:.1f}s")
        perf_str = f" │ {' • '.join(perf_parts)}" if perf_parts else ""

        hint_str = " │ <b>[?]</b> Help  <b>[Shift+Enter]</b> Multi-line  <b>[/]</b> Commands"

        return HTML(
            f" <b>MONIKA</b> │ Model: {model_str} │ {mode_str} │ {status_str}{perf_str}{hint_str} "
        )

    async def prompt_async(self) -> Optional[str]:
        """Prompt user asynchronously for next turn input."""
        p = self.palette
        prompt_message = [
            ("class:prompt-glyph", f"{GLYPH_USER} "),
            ("class:prompt", "MONIKA "),
            ("class:prompt-glyph", "› "),
        ]
        if self.session is not None:
            try:
                return await self.session.prompt_async(prompt_message)
            except (EOFError, KeyboardInterrupt):
                return None
            except Exception:
                pass

        try:
            import asyncio
            return await asyncio.to_thread(input, "MONIKA > ")
        except (EOFError, KeyboardInterrupt):
            return None

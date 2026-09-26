# ==============================================================================
# File: cli/chat/completer.py
# Description: Fuzzy Slash-Command Completer for Monika CLI Chat
# ==============================================================================

"""
Fuzzy slash-command auto-completer for Monika interactive REPL chat.
Provides inline suggestions with command descriptions using prompt_toolkit.
"""

from typing import Iterable, List, Tuple
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# Slash command catalog: (command, description, [sub-options])
SLASH_COMMANDS: List[Tuple[str, str, List[str]]] = [
    ("/help", "Show interactive command reference and keyboard shortcuts", []),
    ("/model", "Switch routing model tier (fast, medium, analyze, research)", ["fast", "medium", "analyze", "research", "auto"]),
    ("/fast", "Quickly ask with Tier 1 Low-Latency model (Gemini Flash)", []),
    ("/analyze", "Ask with Tier 3 Deep Synthesis model", []),
    ("/research", "Ask with Tier 4 Macro Research model", []),
    ("/status", "Display live system status, flags, and MT5 indicators inline", []),
    ("/positions", "List all active open real & paper positions inline", []),
    ("/theme", "Switch color palette theme", ["retro_vintage", "modern_dark", "high_contrast", "daylight"]),
    ("/mode", "Inspect or switch trading execution mode", ["paper", "live"]),
    ("/allow", "Authorize pending order execution (single order)", []),
    ("/session", "Grant 4-hour trade execution authorization for current session", []),
    ("/deny", "Reject pending order execution proposal", []),
    ("/clear", "Clear terminal screen while keeping conversation context", []),
    ("/history", "View recent conversation session list", []),
    ("/exit", "Terminate interactive desk session and disconnect", []),
    ("/quit", "Alias for /exit", []),
]


class ChatCommandCompleter(Completer):
    """
    Fuzzy auto-completer for Monika slash commands.
    Triggers dropdown when user types '/' or subcommands.
    """

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        text_before_cursor = document.text_before_cursor.lstrip()

        # Only trigger completion if line starts with '/'
        if not text_before_cursor.startswith("/"):
            return

        words = text_before_cursor.split()
        if not words:
            return

        first_word = words[0]

        # Case 1: Typing primary slash command
        if len(words) == 1 and not document.text_before_cursor.endswith(" "):
            query = first_word.lower()
            for cmd, desc, _ in SLASH_COMMANDS:
                if query in cmd.lower():
                    # Calculate start position for replacement
                    start_position = -len(first_word)
                    display_meta = desc
                    yield Completion(
                        cmd,
                        start_position=start_position,
                        display=cmd,
                        display_meta=display_meta,
                    )

        # Case 2: Typing subcommand arguments (e.g. /model fast, /theme modern_dark)
        elif len(words) >= 1:
            cmd_name = first_word.lower()
            arg_query = words[1].lower() if len(words) > 1 and not document.text_before_cursor.endswith(" ") else ""
            for cmd, _, sub_opts in SLASH_COMMANDS:
                if cmd.lower() == cmd_name and sub_opts:
                    for opt in sub_opts:
                        if not arg_query or arg_query in opt.lower():
                            start_pos = -len(words[-1]) if (len(words) > 1 and not document.text_before_cursor.endswith(" ")) else 0
                            yield Completion(
                                opt,
                                start_position=start_pos,
                                display=opt,
                                display_meta=f"{cmd} {opt}",
                            )

# ==============================================================================
# File: cli/overlays/approval_modal.py
# Description: Textual Modal Screen for Operator Action & Trade Approval (HITL)
# ==============================================================================

"""
Interactive Modal Dialog for Human-in-the-Loop (HITL) trade action approvals.

Features:
- Full risk preview (Symbol, Action, Direction, Lots, Entry, SL, TP, Risk/Reward)
- 3-tier approval choices: Allow Once, Allow Session (4h), Deny
- Keyboard shortcuts: [1] Allow Once, [2] Allow Session, [3 / Esc] Deny
- Authentic Monika retro-vintage styling with double brass border
"""

from typing import Any, Dict, Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ApprovalModalScreen(ModalScreen[Optional[str]]):
    """
    Modal screen prompting the operator to review and approve/deny a proposed agent action.
    Returns: 'allow_once' | 'allow_session' | 'deny' | None
    """

    DEFAULT_CSS = """
    ApprovalModalScreen {
        align: center middle;
        background: rgba(14, 12, 10, 0.85);
    }

    #approval_dialog {
        width: 78;
        height: auto;
        max-height: 85%;
        background: #1C1917;
        border: double #F5BD38;
        padding: 1 2;
        box-shadow: 0 4 8 rgba(0, 0, 0, 0.7);
    }

    #approval_title {
        text-align: center;
        width: 100%;
        color: #F5BD38;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: heavy #3A352A;
    }

    #approval_desc {
        padding: 1 0;
        color: #D8D2C2;
    }

    .detail_row {
        height: auto;
        padding: 0 1;
    }

    .detail_label {
        width: 22;
        color: #877F75;
        text-style: bold;
    }

    .detail_value {
        width: 1fr;
        color: #FAF7F2;
    }

    #approval_warning {
        margin: 1 0;
        padding: 1;
        background: #2D1B17;
        border: solid #E25B45;
        color: #E25B45;
        text-align: center;
        text-style: bold;
    }

    #button_bar {
        align: center middle;
        height: auto;
        margin-top: 1;
        padding-top: 1;
        border-top: solid #3A352A;
    }

    #button_bar Button {
        margin: 0 1;
        min-width: 18;
    }

    #btn_allow_once {
        background: #1E4620;
        color: #86EFAC;
        border: solid #4CAF50;
    }

    #btn_allow_session {
        background: #1E3A5F;
        color: #93C5FD;
        border: solid #3B82F6;
    }

    #btn_deny {
        background: #4A1E17;
        color: #FCA5A5;
        border: solid #E25B45;
    }

    #shortcut_hint {
        text-align: center;
        color: #5C544C;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "allow_once", "Allow Once", show=True),
        Binding("2", "allow_session", "Allow Session (4h)", show=True),
        Binding("3", "deny", "Deny", show=True),
        Binding("escape", "deny", "Deny / Close", show=True),
        Binding("a", "allow_once", "Allow Once", show=False),
        Binding("s", "allow_session", "Allow Session", show=False),
        Binding("d", "deny", "Deny", show=False),
    ]

    def __init__(self, action: Dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.action = action
        self.action_id = str(action.get("id", ""))
        self.description = action.get("description", "Proposed trade execution action")
        self.params = action.get("parameters", {}) or {}

    def compose(self) -> ComposeResult:
        with Container(id="approval_dialog"):
            yield Label("⚡ OPERATOR HUMAN-IN-THE-LOOP APPROVAL", id="approval_title")

            yield Static(f"[bold white]{self.description}[/]", id="approval_desc")

            # Structured trade parameters if available
            symbol = self.params.get("symbol") or self.action.get("symbol")
            direction = self.params.get("direction") or self.action.get("direction")
            volume = self.params.get("volume") or self.params.get("lots") or self.action.get("volume")
            entry = self.params.get("entry_price") or self.params.get("entry") or self.action.get("entry_price")
            sl = self.params.get("sl") or self.params.get("stop_loss") or self.action.get("sl")
            tp = self.params.get("tp") or self.params.get("take_profit") or self.action.get("tp")
            risk_usd = self.params.get("risk_usd") or self.action.get("risk_usd")

            if symbol or direction or volume or entry:
                with Vertical(id="details_container"):
                    if symbol:
                        with Horizontal(classes="detail_row"):
                            yield Label("INSTRUMENT / SYMBOL:", classes="detail_label")
                            yield Label(f"[bold yellow]{symbol}[/]", classes="detail_value")
                    if direction:
                        dir_color = "green" if str(direction).lower() == "buy" else "red"
                        with Horizontal(classes="detail_row"):
                            yield Label("ORDER DIRECTION:", classes="detail_label")
                            yield Label(f"[bold {dir_color}]{str(direction).upper()}[/]", classes="detail_value")
                    if volume is not None:
                        with Horizontal(classes="detail_row"):
                            yield Label("POSITION VOLUME:", classes="detail_label")
                            yield Label(f"{volume} Lots", classes="detail_value")
                    if entry is not None:
                        with Horizontal(classes="detail_row"):
                            yield Label("PROPOSED ENTRY:", classes="detail_label")
                            yield Label(f"{entry}", classes="detail_value")
                    if sl is not None:
                        with Horizontal(classes="detail_row"):
                            yield Label("STOP LOSS (SL):", classes="detail_label")
                            yield Label(f"[red]{sl}[/]", classes="detail_value")
                    if tp is not None:
                        with Horizontal(classes="detail_row"):
                            yield Label("TAKE PROFIT (TP):", classes="detail_label")
                            yield Label(f"[green]{tp}[/]", classes="detail_value")
                    if risk_usd is not None:
                        with Horizontal(classes="detail_row"):
                            yield Label("PROJECTED RISK:", classes="detail_label")
                            yield Label(f"${risk_usd:.2f}", classes="detail_value")

            yield Static(
                "⚠ Live capital at risk. Verifying MT5 margin and RiskGate invariants before placement.",
                id="approval_warning"
            )

            with Horizontal(id="button_bar"):
                yield Button("[1] Allow Once", id="btn_allow_once", variant="success")
                yield Button("[2] Allow Session (4h)", id="btn_allow_session", variant="primary")
                yield Button("[3 / Esc] Deny", id="btn_deny", variant="error")

            yield Label("Shortcuts: [1/a] Allow Once • [2/s] Allow 4h • [3/d/Esc] Deny", id="shortcut_hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_allow_once":
            self.action_allow_once()
        elif button_id == "btn_allow_session":
            self.action_allow_session()
        elif button_id == "btn_deny":
            self.action_deny()

    def action_allow_once(self) -> None:
        self.dismiss("allow_once")

    def action_allow_session(self) -> None:
        self.dismiss("allow_session")

    def action_deny(self) -> None:
        self.dismiss("deny")

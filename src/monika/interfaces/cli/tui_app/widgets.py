# ==============================================================================
# File: interfaces/cli/tui_app/widgets.py
# Description: Custom Textual UI widgets for Monika TUI Terminal Dashboard
# ==============================================================================

from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from monika.interfaces.cli.sparklines import bar_gauge, braille_sparkline
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
)


class LiveTickerBanner(Static):
    """Top live ticker / system status banner with braille sparklines and trend arrows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prev_quotes: Dict[str, float] = {}

    def update_status(
        self,
        real_count: int,
        paper_count: int,
        daily_pnl: float,
        pnl_pct: Optional[float],
        vix: Optional[float],
        kill_switch: bool,
        system_paused: bool,
        auto_execute: bool,
        quotes: Optional[Dict[str, float]] = None,
        pnl_history: Optional[List[float]] = None,
        vix_history: Optional[List[float]] = None,
    ) -> None:
        quotes = quotes or {}
        quote_strs = []
        for sym, price in quotes.items():
            prev = self._prev_quotes.get(sym)
            if prev is None:
                trend = f"[dim {MUTED}]•[/]"
            elif price > prev:
                trend = f"[bold {BULL_PROFIT}]▲[/]"
            elif price < prev:
                trend = f"[bold {BEAR_LOSS}]▼[/]"
            else:
                trend = f"[dim {MUTED}]•[/]"
            quote_strs.append(f"[bold {PAPER}]{sym}[/] {trend} [{PHOSPHOR_AMBER}]{price:.4f}[/]")
        self._prev_quotes = dict(quotes)
        if not quote_strs:
            ticker_line = f"[dim {MUTED}]MARKET FEED: AWAITING ACTIVE TICK DATA...[/]"
        else:
            ticker_line = "  │  ".join(quote_strs)

        if vix is not None:
            vix_spark = f" [{PHOSPHOR_AMBER}]{braille_sparkline(vix_history, width=8)}[/]" if vix_history else ""
            ticker_line += f"  │  [bold {PAPER}]VIX[/] [{BRASS}]{vix:.2f}[/]{vix_spark}"

        pnl_color = BULL_PROFIT if daily_pnl >= 0 else BEAR_LOSS
        pnl_sign = "+" if daily_pnl >= 0 else ""
        pct_str = f" ({pnl_sign}{pnl_pct:.2f}%)" if pnl_pct is not None else ""
        pnl_spark = f"  [{pnl_color}]{braille_sparkline(pnl_history, width=10)}[/]" if pnl_history else ""
        pnl_str = f"[{pnl_color}]{pnl_sign}${daily_pnl:,.2f}{pct_str}[/]{pnl_spark}"

        ks_str = f"[bold {BEAR_LOSS}][ACTIVE][/]" if kill_switch else f"[{BULL_PROFIT}][NOMINAL][/]"
        state_str = f"[bold {BRASS}][PAUSED][/]" if system_paused else f"[{BULL_PROFIT}][LIVE][/]"
        exec_str = f"[{PHOSPHOR_AMBER}][AUTO][/]" if auto_execute else f"[dim {MUTED}][MANUAL][/]"

        status_line = (
            f"Positions: [bold {PHOSPHOR_AMBER}]{real_count}R/{paper_count}S[/]  │  "
            f"PnL: {pnl_str}  │  "
            f"Kill: {ks_str}  │  "
            f"Status: {state_str}  │  "
            f"Mode: {exec_str}"
        )

        self.update(f"{ticker_line}\n{status_line}")


class StatusBar(Static):
    """Interactive status footer showing tokens, cache hit rate, context gauge, cost, uptime, and busy status."""

    def update_metrics(
        self,
        cached_tokens: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        uptime_seconds: int,
        ws_status: str,
        context_used: int = 0,
        context_max: int = 200000,
        cache_hit_rate: float = 0.0,
        busy_status: str = "",
        budget_tier: str = "T1 (100%)",
        terminal_width: int = 100,
    ) -> None:
        hours, rem = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        tok_str = f"↑{input_tokens / 1000:.1f}k ↓{output_tokens / 1000:.1f}k"

        # Context window gauge
        gauge_bar, gauge_color = bar_gauge(context_used, context_max, width=8 if terminal_width < 110 else 10)
        pct = (context_used / context_max * 100) if context_max > 0 else 0.0
        ctx_str = f"[{gauge_color}]{gauge_bar}[/] [{PAPER}]{pct:.0f}%[/]"

        # Cache hit rate
        cache_str = f"[{BRASS}]◎ {cache_hit_rate:.1f}%[/]"

        # Budget Tier
        tier_color = BULL_PROFIT if "T1" in budget_tier else (BRASS if "T2" in budget_tier else BEAR_LOSS)
        budget_str = f"  │  [dim {MUTED}]Budget:[/] [{tier_color}]{budget_tier}[/]"

        # Busy input indicator
        busy_str = f"  │  [{PHOSPHOR_AMBER}]{busy_status}[/]" if busy_status else ""

        # Width-budget aware formatting: compact when terminal is constrained (< 90 cols)
        if terminal_width < 90:
            content = (
                f"[dim {MUTED}]Tok:[/] [{PAPER}]{tok_str}[/] │ "
                f"[dim {MUTED}]Hit:[/] {cache_str} │ "
                f"[dim {MUTED}]Cost:[/] [{BRASS}]${cost_usd:.3f}[/] │ "
                f"[dim {MUTED}]Feed:[/] {ws_status}{busy_str}"
            )
        else:
            content = (
                f"[dim {MUTED}]Tokens:[/] [{PAPER}]{tok_str}[/]  │  "
                f"[dim {MUTED}]Cache:[/] {cache_str}  │  "
                f"[dim {MUTED}]Context:[/] {ctx_str}  │  "
                f"[dim {MUTED}]Cost:[/] [{BRASS}]${cost_usd:.4f}[/]  │  "
                f"[dim {MUTED}]Uptime:[/] [{PAPER}]{uptime_str}[/]"
                f"{budget_str}  │  "
                f"[dim {MUTED}]Feed:[/] {ws_status}{busy_str}"
            )
        self.update(content)


class KillConfirmModalScreen(ModalScreen[bool]):
    """Modal screen prompting operator to confirm emergency kill switch."""

    DEFAULT_CSS = """
    KillConfirmModalScreen {
        align: center middle;
        background: rgba(14, 12, 10, 0.85);
    }
    #kill_dialog {
        width: 64;
        height: auto;
        padding: 1 2;
    }
    #kill_title {
        text-align: center;
        width: 100%;
        text-style: bold;
        padding-bottom: 1;
    }
    #kill_msg {
        text-align: center;
        padding: 1 0;
    }
    #kill_buttons {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    #kill_buttons Button {
        margin: 0 1;
    }
    """
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "cancel", "No", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="kill_dialog"):
            yield Label("[EMERGENCY] EMERGENCY KILL SWITCH CONFIRMATION", id="kill_title")
            yield Label(
                "Are you sure you want to trigger the KILL SWITCH?\nThis will close all open positions and halt trading.",
                id="kill_msg",
            )
            with Horizontal(id="kill_buttons"):
                yield Button("CONFIRM [Y]", variant="error", id="btn_confirm")
                yield Button("CANCEL [Esc/N]", variant="default", id="btn_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

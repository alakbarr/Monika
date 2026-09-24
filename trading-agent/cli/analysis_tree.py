# ==============================================================================
# File: cli/analysis_tree.py
# Description: Live Analysis Pipeline Tree Widget for Textual TUI
# ==============================================================================

"""
Live Analysis Cycle Tree widget for Monika AI Trading Agent.

Features:
- Real-time rendering of LangGraph 7-node analysis pipeline:
  (fundamental_brief -> prefetch_data -> bull_advocate -> bear_dissent -> debate_judge -> risk_gate -> execution).
- Active cycle rendered prominently with timing, token counters, and braille sparklines.
- History of last 3 completed cycles collapsed below (expandable).
"""

import time
from typing import Any, Dict, List, Optional
from textual.reactive import reactive
from textual.widget import Widget

from cli.sparklines import braille_sparkline
from cli.theme import (
    ThemePack,
    get_theme,
    PHOSPHOR_AMBER,
    BRASS,
    BULL_PROFIT,
    BEAR_LOSS,
    MUTED,
    PAPER,
)


class AnalysisCycleTree(Widget):
    """
    Renders live LangGraph 7-node pipeline as an ASCII/Unicode tree.
    Tracks active cycle steps, elapsed times, tokens, and recent cycle history.
    """

    cycle_data: reactive[Dict[str, Any]] = reactive(dict, always_update=True)
    history_cycles: reactive[List[Dict[str, Any]]] = reactive(list, always_update=True)
    expanded_cycle_id: reactive[Optional[str]] = reactive(None)

    ICONS = {
        "running": f"[{PHOSPHOR_AMBER}]⟳[/]",
        "completed": f"[{BULL_PROFIT}]✓[/]",
        "failed": f"[{BEAR_LOSS}]✗[/]",
        "waiting": f"[{MUTED}]○[/]",
    }

    RAILS = {
        "mid": "├─",
        "last": "└─",
        "pipe": "│ ",
        "space": "  ",
    }

    PIPELINE_STEPS = [
        "fundamental_brief",
        "prefetch_data",
        "bull_advocate",
        "bear_dissent",
        "debate_judge",
        "risk_gate",
        "execution",
    ]

    STEP_LABELS = {
        "fundamental_brief": "Fundamental Brief",
        "prefetch_data": "Prefetch Data",
        "bull_advocate": "Bull Advocate",
        "bear_dissent": "Bear Dissent",
        "debate_judge": "Debate Judge",
        "risk_gate": "Risk Gate",
        "execution": "Execution Service",
    }

    STEP_ALIASES = {
        "fundamental_analysis": "fundamental_brief",
        "fundamental": "fundamental_brief",
        "data_gathering": "prefetch_data",
        "fetch_data": "prefetch_data",
        "prefetch": "prefetch_data",
        "per_asset_analysis": "bull_advocate",
        "per_asset": "bull_advocate",
        "debate": "debate_judge",
        "rebuttal": "bear_dissent",
        "risk": "risk_gate",
    }

    def __init__(self, theme: Optional[ThemePack] = None, **kwargs):
        super().__init__(**kwargs)
        self._start_time: Optional[float] = None
        self.theme: ThemePack = theme or get_theme("retro_vintage")

    def set_theme(self, theme: ThemePack) -> None:
        """Update active theme pack for analysis tree rendering."""
        self.theme = theme
        self.refresh()

    def get_icons(self) -> Dict[str, str]:
        t = self.theme
        return {
            "running": f"[{t.step_running}]⟳[/]",
            "completed": f"[{t.step_completed}]✓[/]",
            "failed": f"[{t.step_failed}]✗[/]",
            "waiting": f"[{t.step_waiting}]○[/]",
        }

    def start_cycle(self, cycle_id: str, symbol: str) -> None:
        """Initialize and display a new analysis cycle."""
        self._start_time = time.time()
        self.cycle_data = {
            "id": cycle_id,
            "symbol": symbol,
            "start_time": self._start_time,
            "status": "running",
            "steps": {
                step: {"status": "waiting", "duration_s": 0.0, "input_tokens": 0, "output_tokens": 0, "token_history": []}
                for step in self.PIPELINE_STEPS
            },
        }

    def update_step(
        self,
        step_name: str,
        status: str,
        duration_s: Optional[float] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        token_history: Optional[List[float]] = None,
    ) -> None:
        """Update status and metrics for a specific pipeline step."""
        target_step = self.STEP_ALIASES.get(step_name, step_name)
        if not self.cycle_data:
            self.cycle_data = {
                "id": "current",
                "symbol": "ACTIVE",
                "status": "running",
                "steps": {},
            }

        steps = dict(self.cycle_data.get("steps", {}))
        current_step = dict(steps.get(target_step, {}))
        current_step["status"] = status
        if duration_s is not None:
            current_step["duration_s"] = float(duration_s)
        if input_tokens is not None:
            current_step["input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            current_step["output_tokens"] = int(output_tokens)
        if token_history is not None:
            current_step["token_history"] = list(token_history)

        steps[target_step] = current_step
        new_data = dict(self.cycle_data)
        new_data["steps"] = steps
        self.cycle_data = new_data

    def complete_cycle(self, decision: Optional[str] = None, outcome_details: Optional[str] = None) -> None:
        """Archive active cycle to history (keeping last 3) and mark finished."""
        if not self.cycle_data:
            return

        elapsed_s = time.time() - (self.cycle_data.get("start_time") or time.time())
        finished_cycle = dict(self.cycle_data)
        finished_cycle["status"] = "completed"
        finished_cycle["elapsed_s"] = elapsed_s
        finished_cycle["decision"] = decision or "COMPLETED"
        finished_cycle["outcome_details"] = outcome_details or ""

        # Prepend to history, retain last 3
        updated_history = [finished_cycle] + list(self.history_cycles)
        self.history_cycles = updated_history[:3]

        # Reset active cycle
        self.cycle_data = {}
        self._start_time = None

    def toggle_history_expand(self, cycle_id: Optional[str] = None) -> None:
        """Toggle detailed view for a historical cycle."""
        if self.expanded_cycle_id == cycle_id:
            self.expanded_cycle_id = None
        else:
            self.expanded_cycle_id = cycle_id

    def render(self) -> str:
        """Render active cycle tree followed by collapsed historical cycles."""
        lines: List[str] = []
        t = self.theme
        icons = self.get_icons()

        # 1. Active cycle rendering
        if self.cycle_data and self.cycle_data.get("id"):
            cycle = self.cycle_data
            cid = cycle.get("id", "?")
            sym = cycle.get("symbol", "N/A")
            start = cycle.get("start_time")
            elapsed_str = f"{time.time() - start:.1f}s" if start else "0.0s"

            lines.append(f"[{t.primary}]◉ Analysis Cycle #{cid}[/] — [bold {t.text}]{sym}[/] [dim {t.muted}]({elapsed_str})[/]")

            steps = cycle.get("steps", {})
            for i, step_name in enumerate(self.PIPELINE_STEPS):
                is_last = i == len(self.PIPELINE_STEPS) - 1
                rail = self.RAILS["last"] if is_last else self.RAILS["mid"]
                step = steps.get(step_name, {})
                status = step.get("status", "waiting")
                icon = icons.get(status, icons["waiting"])
                label = self.STEP_LABELS.get(step_name, step_name)

                parts = [f"  {rail} {icon} [bold {t.text}]{label}[/]"]

                raw_dur = step.get("duration_s")
                dur = float(raw_dur) if raw_dur is not None else 0.0
                if dur > 0.0:
                    dots_count = max(2, 24 - len(label))
                    parts.append(f" [dim {t.muted}]{'.' * dots_count}[/] [{t.accent}]{dur:.1f}s[/]")
                else:
                    dots_count = max(2, 24 - len(label))
                    parts.append(f" [dim {t.muted}]{'.' * dots_count}[/]")

                inp = int(step.get("input_tokens", 0) or 0)
                out = int(step.get("output_tokens", 0) or 0)
                if inp or out:
                    parts.append(f"  [dim {t.muted}]↑{inp / 1000:.1f}k ↓{out / 1000:.1f}k[/]")

                history = step.get("token_history")
                if history:
                    parts.append(f"  [{t.primary}]{braille_sparkline(history, width=6)}[/]")

                lines.append("".join(parts))
        else:
            lines.append(f"[dim {t.muted}]○ No active analysis cycle. Standing by for market trigger or scheduled dispatch...[/]")

        # 2. Historical completed cycles (Last 3 collapsed)
        if self.history_cycles:
            lines.append("")
            lines.append(f"[dim {t.accent}]── Historical Execution Cycles (Last 3) ──[/]")
            for h in self.history_cycles:
                hcid = h.get("id", "?")
                hsym = h.get("symbol", "N/A")
                helapsed = f"{float(h.get('elapsed_s') or 0.0):.1f}s"
                dec = h.get("decision", "DONE")
                dec_color = t.profit if "BUY" in dec or "SELL" in dec else (t.loss if "REJECT" in dec else t.accent)

                # Total tokens in historical cycle
                tot_inp = sum(int(s.get("input_tokens", 0) or 0) for s in h.get("steps", {}).values())
                tot_out = sum(int(s.get("output_tokens", 0) or 0) for s in h.get("steps", {}).values())
                tok_summary = f"↑{tot_inp/1000:.1f}k ↓{tot_out/1000:.1f}k" if (tot_inp or tot_out) else ""

                is_expanded = self.expanded_cycle_id == str(hcid)
                glyph = "▲" if is_expanded else "▽"

                lines.append(
                    f"  [{t.accent}]{glyph}[/] [bold {t.text}]#{hcid}[/] {hsym} ({helapsed}) "
                    f"[{dec_color}][ {dec} ][/] [dim {t.muted}]{tok_summary}[/]"
                )

                if is_expanded:
                    hsteps = h.get("steps", {})
                    for j, sname in enumerate(self.PIPELINE_STEPS):
                        is_l = j == len(self.PIPELINE_STEPS) - 1
                        rl = self.RAILS["last"] if is_l else self.RAILS["mid"]
                        st = hsteps.get(sname, {})
                        st_status = st.get("status", "completed")
                        st_icon = icons.get(st_status, "✓")
                        st_dur = float(st.get("duration_s") or 0.0)
                        lines.append(f"      {rl} {st_icon} {sname} ({st_dur:.1f}s)")

        return "\n".join(lines)

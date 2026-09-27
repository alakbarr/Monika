# ==============================================================================
# File: analysis/tools/domain/computer_use_tool.py
# ==============================================================================

"""
OS Computer Use and GUI Automation Tool.
Institutional-grade engine turn protection architecture.

Enables Monika to interact with native desktop applications (MT5 terminal,
charts, browser portals) via screenshots, mouse movements, clicks, and keystrokes.
Includes strict coordinate boundary validation and fail-safe safety guards.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.ComputerUse")


class ComputerUseInput(BaseModel):
    """Schema for OS-level GUI automation actions."""
    action: str = Field(
        ...,
        description="The action to perform: 'screenshot', 'mouse_move', 'left_click', 'right_click', 'type_text', or 'key_press'."
    )
    coordinate: Optional[List[int]] = Field(
        None,
        description="Screen [x, y] pixel coordinates for mouse actions."
    )
    text: Optional[str] = Field(
        None,
        description="Text string to type into the active window."
    )
    key: Optional[str] = Field(
        None,
        description="Key name to press (e.g. 'enter', 'tab', 'f9', 'ctrl+s')."
    )


@unified_tool_registry.register(
    name="computer_use",
    category="SYSTEM_AUTOMATION",
    input_model=ComputerUseInput,
)
async def handle_computer_use(
    params: ComputerUseInput,
    context: Optional[Any] = None,
) -> str:
    """Execute desktop GUI interaction or capture screen state."""
    action = params.action.lower().strip()

    try:
        import importlib
        pyautogui = importlib.import_module("pyautogui")
        pyautogui.FAILSAFE = True
    except (ImportError, Exception):
        # Graceful fallback when desktop GUI libraries are not present
        if action == "screenshot":
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                tmp_dir = Path(tempfile.gettempdir()) / "monika_screenshots"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                file_path = tmp_dir / f"screenshot_{int(time.time())}.png"
                img.save(file_path, "PNG")
                return f"[SCREENSHOT CAPTURED via PIL]: Saved to {file_path} ({img.width}x{img.height})"
            except Exception as e:
                return f"GUI Automation Unavailable: 'pyautogui' and 'PIL.ImageGrab' could not be initialized ({e})."
        return "GUI Automation Unavailable: 'pyautogui' is required for desktop mouse/keyboard automation."

    try:
        screen_w, screen_h = pyautogui.size()

        if action == "screenshot":
            screenshot = pyautogui.screenshot()
            tmp_dir = Path(tempfile.gettempdir()) / "monika_screenshots"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            file_path = tmp_dir / f"screenshot_{int(time.time())}.png"
            screenshot.save(file_path, "PNG")
            return f"[SCREENSHOT CAPTURED]: Saved to {file_path} ({screen_w}x{screen_h})"

        elif action in {"mouse_move", "left_click", "right_click"}:
            if not params.coordinate or len(params.coordinate) != 2:
                return f"Error: Action '{action}' requires [x, y] coordinates."
            x, y = params.coordinate
            if not (0 <= x < screen_w and 0 <= y < screen_h):
                return f"Error: Coordinates [{x}, {y}] are out of screen bounds ({screen_w}x{screen_h})."

            if action == "mouse_move":
                pyautogui.moveTo(x, y, duration=0.2)
                return f"Moved cursor to [{x}, {y}]."
            elif action == "left_click":
                pyautogui.click(x, y, button="left")
                return f"Left clicked at [{x}, {y}]."
            elif action == "right_click":
                pyautogui.click(x, y, button="right")
                return f"Right clicked at [{x}, {y}]."

        elif action == "type_text":
            if not params.text:
                return "Error: Action 'type_text' requires 'text' parameter."
            pyautogui.write(params.text, interval=0.02)
            return f"Typed {len(params.text)} characters into active focus."

        elif action == "key_press":
            if not params.key:
                return "Error: Action 'key_press' requires 'key' parameter."
            keys = [k.strip() for k in params.key.split("+")]
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(keys[0])
            return f"Pressed key '{params.key}'."

        return f"Error: Unrecognized computer_use action '{action}'."

    except Exception as exc:
        logger.error(f"[ComputerUse] Failed to perform '{action}': {exc}", exc_info=True)
        return f"Error executing GUI action '{action}': {exc}"

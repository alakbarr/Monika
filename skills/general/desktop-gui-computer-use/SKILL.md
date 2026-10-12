---
name: desktop-gui-computer-use
description: "Desktop GUI Interaction & Computer Use Playbook: Screen inspection, MetaTrader 5 window snapping, mouse click automation, and keystroke dispatching."
category: GENERAL
version: 1.0.0
platforms: [windows]
tags: [computer_use, gui, mt5, pyautogui, screenshot, window_focus, automation]
---

# Desktop GUI & Computer Use Playbook

## 1. Overview & Operational Domain
Enables Monika to act as an autonomous computer operator interacting directly with desktop software—principally the native MetaTrader 5 terminal, charting windows, and broker client portals.

Core Capabilities:
1. **Visual State Inspection**: High-resolution screen capture via `pyautogui` / `PIL.ImageGrab` to verify visual chart state, open orders on chart, and broker dialogue boxes.
2. **Deterministic Window Focusing**: Uses native Windows `user32.dll` API via `focus_mt5_window()` to bring the target application to the foreground before dispatching mouse or keyboard events.
3. **Cursor Navigation & Clicks**: Controlled coordinate positioning with boundary validation to prevent clicking outside valid screen dimensions.
4. **Keystroke Dispatching**: Sending single keys (e.g. `F9` for New Order dialog, `Enter`, `Escape`) or multi-key combos (`ctrl+s`, `alt+f4`).

## 2. Safety Fortress Confirmation Architecture
- **Read-Only Action**: `action="screenshot"` is executed immediately without operator prompt to inspect current screen state.
- **Interactive Actions**: `left_click`, `right_click`, `mouse_move`, `type_text`, `key_press` are gated by Safety Fortress:
  - Intercepted into `PendingAction("desktop_gui_action")`.
  - Operator receives an inline confirmation card specifying action, target coordinates, and typed text.
  - Requires operator tap on "Konfirmasi" before PyAutoGUI dispatches input.

## 3. Tool Commands Reference

### Capturing Screen State
```json
{
  "action": "screenshot"
}
```
Returns path to saved PNG screenshot in temporary directory for multimodal vision inspection.

### Clicking MT5 Interface Elements
```json
{
  "action": "left_click",
  "coordinate": [450, 320]
}
```
*Note: Automatically invokes `focus_mt5_window()` before clicking.*

### Pressing Hotkeys
```json
{
  "action": "key_press",
  "key": "f9"
}
```
Opens the MetaTrader 5 New Order ticket window.

### Typing Text
```json
{
  "action": "type_text",
  "text": "1.08500"
}
```
Types parameter string into the currently focused input box with 20ms human-like key intervals.

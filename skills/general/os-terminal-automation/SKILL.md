---
name: os-terminal-automation
description: "Universal Terminal & Process Execution Playbook: Controlled shell execution, process monitoring, background task supervision, and operator safety gating."
category: GENERAL
version: 1.0.0
platforms: [windows, linux, macos]
tags: [terminal, process, devops, shell, powershell, supervision, operator]
---

# OS Terminal Automation & Process Supervision Playbook

## 1. Overview & Operational Principles
Enables Monika to execute command-line diagnostics, software maintenance, and background tasks safely within the host environment (Windows PowerShell / CMD / Bash).

Safety Fortress Axiom:
- **Read-Only Non-Destructive Commands**: Allowed directly for rapid diagnostics (e.g. `git status`, `git log`, `tasklist`, `uptime`, `dir`, `ps`, `cat`, `date`, `whoami`).
- **Mutating & System Operations**: Strictly intercepted into a `PendingAction("execute_terminal_command")` requiring explicit operator confirmation via Telegram inline button before shell execution.

## 2. Terminal Engine Architecture
Implemented in `analysis/tools/terminal_process_engine.py` and exposed via `analysis/tools/domain/terminal_tools.py`:
- **Foreground Execution**: Runs short commands with a strict timeout (default 60s, max 600s).
- **Automatic Demotion**: Commands exceeding foreground threshold or flagged with `background=True` are demoted to background process sessions with an assigned `session_id`.
- **Output Ring Buffer**: Retains stdout and stderr in rolling memory buffers for inspection via `process_manage(action='log', session_id=...)`.

## 3. Tool Usage Specifications

### Running Commands via `terminal`
```json
{
  "command": "git status --short",
  "timeout": 30.0,
  "background": false
}
```

### Supervising Background Tasks via `process_manage`
- **List Active Tasks**:
  `process_manage(action="list")`
- **Poll Status**:
  `process_manage(action="poll", session_id="sess_xyz")`
- **Read Streaming Logs**:
  `process_manage(action="log", session_id="sess_xyz", offset=0, limit=5000)`
- **Kill Process**:
  `process_manage(action="kill", session_id="sess_xyz")`

## 4. Safety Guardrails & Prohibited Commands
The following operations must never be executed without explicit operator proposal:
1. Deleting files or directories (`rm`, `del`, `Remove-Item`).
2. Force killing processes without operator review (`taskkill /F`, `kill -9`).
3. Modifying environment or system configurations (`setx`, registry modifications).
4. Git force push or reset discarding local workspace code.

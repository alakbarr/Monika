# ==============================================================================
# File: interfaces/cli/commands/inspect_ctrl.py
# ==============================================================================

"""
Inspection, Diagnostics, and Session Commands for Monika.
Handles sessions, logs, doctor, setup, and profile management.
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import aiohttp
from rich.table import Table
from sqlalchemy import desc, func, select

from monika.interfaces.cli.context import cli_main
from monika.infrastructure.database.models import ActivityLog, TelegramConversation
from monika.interfaces.cli.theme import (
    BRASS,
    LEDGER_BOX,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
    stamp_err,
    stamp_exec,
    stamp_info,
    stamp_ok,
    stamp_warn,
)


async def _cmd_sessions(args: Any) -> None:
    """List conversation sessions with metadata."""
    console = cli_main.get_console()

    url = getattr(args, "url", cli_main.DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")
    source = getattr(args, "source", "all")
    limit = getattr(args, "limit", 20)

    sessions_data: Optional[List[Dict[str, Any]]] = None
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            headers = {"X-API-Key": token} if token else {}
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
                q = f"?limit={limit}"
                if source != "all":
                    q += f"&source={source}"
                res = await sess.get(f"{url.rstrip('/')}/api/sessions{q}")
                if res.status == 200:
                    sessions_data = await res.json()
        except Exception:
            sessions_data = None

    if sessions_data is None:
        await cli_main.init_db()
        async with cli_main.get_session() as session:
            query = (
                select(
                    TelegramConversation.telegram_user_id,
                    func.count(TelegramConversation.id).label("message_count"),
                    func.max(TelegramConversation.timestamp).label("last_active"),
                )
                .group_by(TelegramConversation.telegram_user_id)
                .order_by(desc("last_active"))
                .limit(limit)
            )
            if source == "dashboard":
                query = query.where(TelegramConversation.telegram_user_id.like("dash%"))
            elif source == "cli":
                query = query.where(TelegramConversation.telegram_user_id.like("cli%"))
            elif source == "telegram":
                query = query.where(
                    ~TelegramConversation.telegram_user_id.like("dash%"),
                    ~TelegramConversation.telegram_user_id.like("cli%"),
                )

            rows = (await session.execute(query)).all()
            sessions_data = []
            for r in rows:
                uid = str(r.telegram_user_id)
                latest = (
                    await session.execute(
                        select(TelegramConversation.message)
                        .where(TelegramConversation.telegram_user_id == uid)
                        .order_by(TelegramConversation.timestamp.desc())
                        .limit(1)
                    )
                ).first()
                sessions_data.append(
                    {
                        "session_id": uid,
                        "source": "dashboard"
                        if uid.startswith("dash")
                        else ("cli" if uid.startswith("cli") else "telegram"),
                        "message_count": r.message_count,
                        "last_active": r.last_active.isoformat() if r.last_active else "N/A",
                        "last_message": latest[0][:80] if latest else "",
                    }
                )

    table = Table(
        title=f"[{PHOSPHOR_AMBER}]Conversation Sessions[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}"
    )
    table.add_column("Session ID", style=PAPER)
    table.add_column("Source", justify="center")
    table.add_column("Messages", justify="right", style=f"bold {BRASS}")
    table.add_column("Last Active", style=MUTED)
    table.add_column("Last Message", style=PAPER)

    if not sessions_data:
        console.print(f"[{MUTED}]No active conversation sessions found.[/]")
        return

    for s in sessions_data:
        src = str(s.get("source", "unknown")).upper()
        if src == "DASHBOARD":
            src_badge = stamp_ok("DASHBOARD")
        elif src == "CLI":
            src_badge = stamp_exec("CLI")
        else:
            src_badge = stamp_info("TELEGRAM")

        table.add_row(
            str(s.get("session_id", "N/A")),
            src_badge,
            str(s.get("message_count", 0)),
            str(s.get("last_active", "N/A"))[:19].replace("T", " "),
            str(s.get("last_message", "")),
        )

    console.print()
    console.print(table)
    console.print()


async def _cmd_logs(args: Any) -> None:
    """Stream or tail live activity logs."""
    console = cli_main.get_console()

    lines = getattr(args, "lines", 20)
    follow = getattr(args, "follow", False)
    category = getattr(args, "category", None)
    severity = getattr(args, "severity", None)

    await cli_main.init_db()

    def _render_log(log_item: Dict[str, Any]):
        ts = log_item.get("timestamp") or ""
        if "T" in ts:
            ts = ts.split("T")[1][:8]
        cat = str(log_item.get("category", "system")).lower()
        actor = str(log_item.get("actor", "agent"))
        desc = str(log_item.get("description", ""))

        if cat in ("error", "critical"):
            cat_badge = stamp_err("ERROR")
        elif cat in ("warn", "warning", "risk"):
            cat_badge = stamp_warn("RISK")
        elif cat in ("trade", "trading", "order"):
            cat_badge = stamp_exec("TRADE")
        elif cat in ("analysis", "debate"):
            cat_badge = stamp_info("ANALYSIS")
        else:
            cat_badge = f"[{MUTED}][ SYSTEM ][/]"

        console.print(f"[{MUTED}]{ts}[/] {cat_badge} [bold {BRASS}]{actor}:[/] [{PAPER}]{desc}[/]")

    last_seen_id = 0
    async with cli_main.get_session() as session:
        q = select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(lines)
        if category:
            q = q.where(ActivityLog.category == category)
        if severity:
            sev_lower = severity.lower()
            q = q.where(ActivityLog.category.ilike(f"%{sev_lower}%") | ActivityLog.description.ilike(f"%{sev_lower}%"))
        items = (await session.execute(q)).scalars().all()
        for item in reversed(items):
            last_seen_id = max(last_seen_id, item.id)
            _render_log(
                {
                    "id": item.id,
                    "timestamp": item.timestamp.isoformat() if item.timestamp else "",
                    "category": item.category,
                    "actor": item.actor,
                    "description": item.description,
                }
            )

    if not follow:
        return

    console.print(f"[{MUTED}]Streaming real-time system activity logs (Press Ctrl+C to terminate)...[/]")
    try:
        while True:
            await asyncio.sleep(1.5)
            async with cli_main.get_session() as session:
                q = select(ActivityLog).where(ActivityLog.id > last_seen_id).order_by(ActivityLog.timestamp.asc())
                if category:
                    q = q.where(ActivityLog.category == category)
                if severity:
                    sev_lower = severity.lower()
                    q = q.where(
                        ActivityLog.category.ilike(f"%{sev_lower}%") | ActivityLog.description.ilike(f"%{sev_lower}%")
                    )
                new_items = (await session.execute(q)).scalars().all()
                for item in new_items:
                    last_seen_id = max(last_seen_id, item.id)
                    _render_log(
                        {
                            "id": item.id,
                            "timestamp": item.timestamp.isoformat() if item.timestamp else "",
                            "category": item.category,
                            "actor": item.actor,
                            "description": item.description,
                        }
                    )
    except KeyboardInterrupt:
        console.print(f"\n[{MUTED}]Log stream terminated by operator.[/]")
    except asyncio.CancelledError:
        console.print(f"\n[{MUTED}]Log stream terminated by operator.[/]")
        raise
        console.print(f"\n[{MUTED}]Log stream terminated by operator.[/]")


async def _cmd_doctor(args: Any) -> None:
    from monika.interfaces.cli.doctor import SystemDoctor

    doc = SystemDoctor(
        fix=getattr(args, "fix", False),
        live_probes=not getattr(args, "offline", False),
        verbose=getattr(args, "verbose", False),
    )
    await doc.run_diagnostics()
    code = doc.render_report()
    if code != 0:
        sys.exit(code)


async def _cmd_setup(args: Any) -> None:
    from monika.interfaces.cli.setup_wizard import SetupWizard

    wizard = SetupWizard(settings_path=getattr(args, "config", None))
    section = getattr(args, "section", "all")
    quick = getattr(args, "quick", False)
    wizard.run_wizard(section=section, quick=quick)


async def _cmd_profile(args: Any) -> None:
    from monika.interfaces.cli.profile_manager import ProfileManager

    pm = ProfileManager()
    console = cli_main.get_console()
    action = getattr(args, "profile_action", "list") or "list"

    if action == "list":
        profiles = pm.list_profiles()
        tbl = Table(
            title=f"[{PHOSPHOR_AMBER}]MONIKA PROFILES[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}"
        )
        tbl.add_column("Profile", style=f"bold {BRASS}")
        tbl.add_column("Status", justify="center")
        tbl.add_column("Config Path", style=PAPER)

        for p in profiles:
            status = stamp_ok("ACTIVE") if p.is_active else f"[{MUTED}]STANDBY[/]"
            tbl.add_row(p.name, status, p.path)
        console.print()
        console.print(tbl)
        console.print()
    elif action == "use":
        name = getattr(args, "name", "default")
        try:
            pm.set_active_profile(name)
            console.print(f"{stamp_ok('PROFILE')} Switched active profile to: [bold {BRASS}]{name}[/]")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to switch profile: {e}")
    elif action == "create":
        name = getattr(args, "name", "")
        clone = getattr(args, "clone", None)
        try:
            p_dir = pm.create_profile(name, clone_from=clone)
            console.print(f"{stamp_ok('PROFILE')} Created profile [bold {BRASS}]{name}[/] at {p_dir}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to create profile: {e}")
    elif action == "delete":
        name = getattr(args, "name", "")
        try:
            pm.delete_profile(name)
            console.print(f"{stamp_ok('PROFILE')} Deleted profile [bold {BRASS}]{name}[/]")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to delete profile: {e}")
    elif action == "export":
        name = getattr(args, "name", "")
        zip_path = getattr(args, "zip_path", f"{name}.zip")
        try:
            out_path = pm.export_profile(name, zip_path)
            console.print(f"{stamp_ok('PROFILE')} Exported profile [bold {BRASS}]{name}[/] to {out_path}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to export profile: {e}")
    elif action == "import":
        zip_path = getattr(args, "zip_path", "")
        name = getattr(args, "name", None)
        try:
            target_dir = pm.import_profile(zip_path, new_name=name)
            console.print(f"{stamp_ok('PROFILE')} Imported profile to {target_dir}")
        except Exception as e:
            console.print(f"{stamp_err('PROFILE')} Failed to import profile: {e}")

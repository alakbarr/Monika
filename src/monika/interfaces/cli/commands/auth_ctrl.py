# ==============================================================================
# File: interfaces/cli/commands/auth_ctrl.py
# ==============================================================================

"""
CLI Authentication Controller for Subscription & OAuth Providers.
Handles interactive login, credential adoption, token status inspection,
and logout for Z.AI (GLM), Gemini (Antigravity), Claude, and ChatGPT (Codex).
"""

from __future__ import annotations

import getpass
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from rich.console import Console
from rich.table import Table

from monika.core.security.credential_vault import vault
from monika.infrastructure.auth import (
    DEFAULT_ANTIGRAVITY_PROXY_URL,
    check_antigravity_bridge_health,
    delete_oauth_tokens,
    exchange_code_for_token,
    exchange_codex_code,
    generate_pkce_pair,
    get_antigravity_home,
    get_claude_authorization_url,
    get_claude_credentials_path,
    get_codex_cli_auth_path,
    get_oauth_tokens,
    get_token_expiry_timestamp,
    is_antigravity_installed,
    is_token_expiring,
    poll_codex_authorization,
    read_claude_code_credentials,
    read_codex_cli_credentials,
    request_codex_device_code,
    save_oauth_tokens,
)
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    MUTED,
    get_console,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

logger = logging.getLogger("TradingAgent.CLI.Auth")
console = get_console()

GREEN = "green"
RED = "red"
YELLOW = "yellow"
CYAN = "cyan"


def handle_auth_command(args) -> int:
    """Entrypoint dispatcher for 'monika auth' subcommands."""
    action = getattr(args, "auth_action", None)
    if not action or action == "status":
        return show_auth_status()
    if action == "login":
        provider = getattr(args, "provider", None)
        return login_provider(provider)
    if action == "logout":
        provider = getattr(args, "provider", None)
        return logout_provider(provider)

    console.print(f"{stamp_err('ERROR')} Unknown auth action: {action}")
    return 1


def show_auth_status() -> int:
    """Display comprehensive status table for all supported subscription & OAuth providers."""
    console.print(f"\n[bold {BRASS}]=== MONIKA SUBSCRIPTION & OAUTH PROVIDERS STATUS ===[/]\n")

    table = Table(show_header=True, header_style=f"bold {CYAN}", border_style="dim")
    table.add_column("Provider", width=14)
    table.add_column("Type / Protocol", width=22)
    table.add_column("Auth Status", width=22)
    table.add_column("Session / Expiry", width=26)
    table.add_column("Details", width=34)

    # 1. Z.AI / GLM
    zai_key = vault.get_secret("ZAI_API_KEY") or vault.get_secret("GLM_API_KEY")
    if zai_key:
        zai_status = f"[{GREEN}]ACTIVE (Configured)[/]"
        zai_expiry = f"[{MUTED}]Subscription API Key[/]"
        zai_detail = f"[{MUTED}]Z.AI Coding Plan / PaaS[/]"
    else:
        zai_status = f"[{YELLOW}]NOT CONFIGURED[/]"
        zai_expiry = "—"
        zai_detail = "Run 'monika auth login zai'"
    table.add_row("Z.AI (GLM)", "GLM Coding Plan / PaaS", zai_status, zai_expiry, zai_detail)

    # 2. Gemini (Antigravity Bridge)
    health = check_antigravity_bridge_health()
    installed = is_antigravity_installed()
    if health.get("running") and health.get("authenticated"):
        agy_status = f"[{GREEN}]ONLINE (Connected)[/]"
        agy_expiry = f"[{MUTED}]Local Bridge Active[/]"
        agy_detail = f"[{GREEN}]{health.get('proxy_url')}[/]"
    elif installed:
        agy_status = f"[{YELLOW}]STANDBY (CLI Detected)[/]"
        agy_expiry = f"[{MUTED}]~/.gemini/antigravity-cli[/]"
        agy_detail = "Run bridge or start proxy"
    else:
        agy_status = f"[{MUTED}]NOT DETECTED[/]"
        agy_expiry = "—"
        agy_detail = "Antigravity CLI not found"
    table.add_row("Gemini", "Antigravity Bridge / agy", agy_status, agy_expiry, agy_detail)

    # 3. Claude (Anthropic OAuth)
    claude_rec = get_oauth_tokens("anthropic")
    cli_creds = read_claude_code_credentials()
    api_key = vault.get_secret("ANTHROPIC_API_KEY")

    if claude_rec and claude_rec.get("access_token"):
        exp_ts = get_token_expiry_timestamp(claude_rec)
        if is_token_expiring(claude_rec):
            c_status = f"[{YELLOW}]EXPIRING / REFRESHABLE[/]"
        else:
            c_status = f"[{GREEN}]ACTIVE (OAuth Token)[/]"
        c_expiry = _format_expiry(exp_ts)
        c_detail = f"Source: {claude_rec.get('source', 'oauth')}"
    elif cli_creds:
        c_status = f"[{CYAN}]READY TO ADOPT[/]"
        c_expiry = f"[{MUTED}]Claude Code CLI Found[/]"
        c_detail = "Run 'monika auth login claude'"
    elif api_key:
        c_status = f"[{GREEN}]ACTIVE (API Key)[/]"
        c_expiry = f"[{MUTED}]Permanent API Key[/]"
        c_detail = "ANTHROPIC_API_KEY configured"
    else:
        c_status = f"[{YELLOW}]NOT CONFIGURED[/]"
        c_expiry = "—"
        c_detail = "Run 'monika auth login claude'"
    table.add_row("Claude", "Claude Code OAuth / API", c_status, c_expiry, c_detail)

    # 4. ChatGPT (OpenAI Codex)
    codex_rec = get_oauth_tokens("codex")
    codex_cli = read_codex_cli_credentials()
    if codex_rec and codex_rec.get("access_token"):
        exp_ts = get_token_expiry_timestamp(codex_rec)
        if is_token_expiring(codex_rec):
            cx_status = f"[{YELLOW}]EXPIRING / REFRESHABLE[/]"
        else:
            cx_status = f"[{GREEN}]ACTIVE (Codex OAuth)[/]"
        cx_expiry = _format_expiry(exp_ts)
        cx_detail = f"Source: {codex_rec.get('source', 'oauth')}"
    elif codex_cli:
        cx_status = f"[{CYAN}]READY TO ADOPT[/]"
        cx_expiry = f"[{MUTED}]Codex CLI Found[/]"
        cx_detail = "Run 'monika auth login codex'"
    else:
        cx_status = f"[{YELLOW}]NOT CONFIGURED[/]"
        cx_expiry = "—"
        cx_detail = "Run 'monika auth login codex'"
    table.add_row("ChatGPT", "OpenAI Codex OAuth", cx_status, cx_expiry, cx_detail)

    console.print(table)
    console.print(f"\n[{MUTED}]Run 'python -m monika.interfaces.cli.main auth login <provider>' to authenticate.[/]\n")
    return 0


def _format_expiry(expiry_ts: Optional[float]) -> str:
    """Format expiration timestamp into human-readable string."""
    if not expiry_ts:
        return f"[{MUTED}]Active[/]"
    diff = expiry_ts - time.time()
    if diff <= 0:
        return f"[{RED}]Expired (Auto-refresh on call)[/]"
    hours = int(diff // 3600)
    minutes = int((diff % 3600) // 60)
    if hours > 24:
        days = hours // 24
        return f"[{GREEN}]Expires in {days}d {hours % 24}h[/]"
    return f"[{GREEN}]Expires in {hours}h {minutes}m[/]"


def login_provider(provider: Optional[str]) -> int:
    """Authenticate with a specific subscription provider."""
    if not provider:
        console.print(f"{stamp_err('ERROR')} Please specify a provider: zai, antigravity, claude, codex")
        return 1

    p = provider.strip().lower()

    if p in ("zai", "glm", "z-ai", "z.ai"):
        return _login_zai()
    elif p in ("claude", "anthropic"):
        return _login_claude()
    elif p in ("codex", "chatgpt", "openai"):
        return _login_codex()
    elif p in ("antigravity", "gemini", "agy"):
        return _login_antigravity()
    else:
        console.print(
            f"{stamp_err('ERROR')} Unknown provider '{provider}'. Choose from: zai, antigravity, claude, codex"
        )
        return 1


def _login_zai() -> int:
    """Interactive login for Z.AI / GLM Coding Plan."""
    console.print(f"\n[bold {BRASS}]=== Z.AI / GLM CODING PLAN AUTHENTICATION ===[/]\n")
    console.print(f"  [{MUTED}]You can obtain an API key from https://z.ai/subscribe or https://open.bigmodel.cn[/]")

    key = getpass.getpass("Enter your Z.AI / GLM API Key: ").strip()
    if not key:
        console.print(f"{stamp_err('ABORTED')} No API key entered.")
        return 1

    # Validate against models endpoint
    console.print(f"{stamp_info('VERIFYING')} Testing connection to Z.AI PaaS API...")
    req = urllib.request.Request(
        "https://api.z.ai/api/paas/v4/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "Monika/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                vault.set_secret("ZAI_API_KEY", key)
                save_oauth_tokens("zai", {"api_key": key, "source": "manual_login"})
                console.print(f"{stamp_ok('SUCCESS')} Z.AI / GLM credentials saved and verified successfully!\n")
                return 0
    except urllib.error.HTTPError as err:
        console.print(f"{stamp_err('VALIDATION FAILED')} Z.AI returned HTTP {err.code}: {err.reason}")
        return 1
    except Exception as exc:
        console.print(f"{stamp_err('CONNECTION FAILED')} Could not connect to Z.AI: {exc}")
        return 1

    return 0


def _login_claude() -> int:
    """Interactive login for Claude Code OAuth / Anthropic PKCE."""
    console.print(f"\n[bold {BRASS}]=== CLAUDE CODE OAUTH AUTHENTICATION ===[/]\n")

    # Step 1: Check for existing Claude Code credentials
    cli_creds = read_claude_code_credentials()
    if cli_creds:
        creds_file = get_claude_credentials_path()
        console.print(f"  [{GREEN}]Found existing Claude Code CLI session[/] at: {creds_file}")
        ans = input("  Adopt these credentials into Monika? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            save_oauth_tokens("anthropic", cli_creds)
            console.print(f"{stamp_ok('SUCCESS')} Successfully adopted Claude Code credentials into Monika!\n")
            return 0

    # Step 2: PKCE browser login flow
    console.print(f"  [{MUTED}]Starting browser authorization flow...[/]")
    verifier, challenge = generate_pkce_pair()
    auth_url = get_claude_authorization_url(challenge, state="monika_cli_login")

    console.print("\n  1. Open this URL in your browser to sign in with Anthropic:")
    console.print(f"     [bold {CYAN}]{auth_url}[/]\n")
    console.print("  2. After signing in, you will be redirected to a callback page.")
    console.print("     Copy the full redirect URL or the 'code' parameter value.\n")

    code_or_url = input("Paste the authorization code or redirect URL here: ").strip()
    if not code_or_url:
        console.print(f"{stamp_err('ABORTED')} No authorization code provided.")
        return 1

    # Extract code if full URL was pasted
    code = code_or_url
    if "code=" in code_or_url:
        parsed = urllib.parse.urlparse(code_or_url)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [code_or_url])[0]

    console.print(f"{stamp_info('EXCHANGING')} Swapping code for access tokens...")
    tokens = exchange_code_for_token(code, verifier)
    if tokens and tokens.get("access_token"):
        console.print(f"{stamp_ok('SUCCESS')} Successfully authenticated with Claude Code OAuth!\n")
        return 0

    console.print(f"{stamp_err('FAILED')} Token exchange failed. Please verify the code and try again.")
    return 1


def _login_codex() -> int:
    """Interactive login for ChatGPT subscription via OpenAI Codex Device Code flow."""
    console.print(f"\n[bold {BRASS}]=== CHATGPT / OPENAI CODEX DEVICE CODE AUTHENTICATION ===[/]\n")

    # Step 1: Check existing ~/.codex/auth.json
    cli_creds = read_codex_cli_credentials()
    if cli_creds:
        auth_file = get_codex_cli_auth_path()
        console.print(f"  [{GREEN}]Found existing OpenAI Codex CLI credentials[/] at: {auth_file}")
        ans = input("  Adopt these credentials into Monika? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            save_oauth_tokens("codex", cli_creds)
            console.print(f"{stamp_ok('SUCCESS')} Successfully adopted Codex CLI credentials into Monika!\n")
            return 0

    # Step 2: Device Code Request
    console.print(f"{stamp_info('CONNECTING')} Requesting user code from OpenAI...")
    try:
        device_data = request_codex_device_code()
    except Exception as exc:
        console.print(f"{stamp_err('ERROR')} Failed to request device code from OpenAI: {exc}")
        return 1

    user_code = str(device_data.get("user_code") or "").strip()
    device_auth_id = str(device_data.get("device_auth_id") or "").strip()
    poll_interval = int(device_data.get("interval", 5))

    if not user_code or not device_auth_id:
        console.print(f"{stamp_err('ERROR')} Incomplete device auth response received from OpenAI.")
        return 1

    console.print("\n  [bold]Follow these steps to link your ChatGPT Plus/Pro account:[/]")
    console.print(f"  1. Open this URL in your browser: [bold {CYAN}]https://auth.openai.com/codex/device[/]")
    console.print(f"  2. Enter this code: [bold {GREEN}]{user_code}[/]\n")
    console.print(f"  [{MUTED}]Waiting for authorization in browser... (Press Ctrl+C to cancel)[/]")

    try:
        code_resp = poll_codex_authorization(device_auth_id, user_code, poll_interval=poll_interval)
        console.print(f"{stamp_info('EXCHANGING')} Exchanging authorization for tokens...")
        token_record = exchange_codex_code(code_resp)
        if token_record and token_record.get("access_token"):
            console.print(f"{stamp_ok('SUCCESS')} Successfully linked ChatGPT / Codex subscription!\n")
            return 0
    except KeyboardInterrupt:
        console.print(f"\n{stamp_warn('CANCELLED')} Login cancelled by user.")
        return 130
    except Exception as exc:
        console.print(f"{stamp_err('FAILED')} Device login failed: {exc}")
        return 1

    return 1


def _login_antigravity() -> int:
    """Inspect and connect Google Antigravity Bridge."""
    console.print(f"\n[bold {BRASS}]=== GOOGLE GEMINI ANTIGRAVITY BRIDGE SETUP ===[/]\n")

    home = get_antigravity_home()
    if is_antigravity_installed():
        console.print(f"{stamp_ok('DETECTED')} Google Antigravity CLI installation found at:")
        console.print(f"  [{MUTED}]{home}[/]\n")
    else:
        console.print(f"{stamp_warn('NOTICE')} Antigravity CLI directory (~/.gemini/antigravity-cli) was not found.")
        console.print("  To use Gemini without an API key, install and authenticate Google Antigravity (`agy`).\n")

    console.print(
        f"{stamp_info('PROBING')} Checking local Antigravity Bridge proxy at: {DEFAULT_ANTIGRAVITY_PROXY_URL}..."
    )
    health = check_antigravity_bridge_health()
    if health.get("running") and health.get("authenticated"):
        console.print(f"{stamp_ok('HEALTHY')} {health.get('message')}")
        console.print("  Monika can now route Gemini requests through this bridge.\n")
        return 0

    console.print(f"{stamp_warn('OFFLINE')} {health.get('message')}")
    console.print("\n  [bold]How to activate the Antigravity Bridge:[/]")
    console.print("  1. Launch the bridge proxy on your system:")
    console.print(f"     [bold {CYAN}]python -m antigravity_proxy --port 8877[/]")
    console.print("  2. Or configure a custom proxy URL in config/settings.yaml (llm.providers.antigravity.base_url)\n")
    return 1


def logout_provider(provider: Optional[str]) -> int:
    """Remove OAuth tokens for a specific provider."""
    if not provider:
        console.print(f"{stamp_err('ERROR')} Please specify a provider to logout: zai, claude, codex")
        return 1

    p = provider.strip().lower()
    mapping = {
        "zai": "zai",
        "glm": "zai",
        "claude": "anthropic",
        "anthropic": "anthropic",
        "codex": "codex",
        "chatgpt": "codex",
    }
    target = mapping.get(p)
    if not target:
        console.print(f"{stamp_err('ERROR')} Unknown provider '{provider}'.")
        return 1

    # Delete from vault and oauth_store
    delete_oauth_tokens(target)
    if target == "zai":
        vault.delete_secret("ZAI_API_KEY")

    console.print(f"{stamp_ok('SUCCESS')} Successfully logged out from {provider}. Credentials cleared from vault.\n")
    return 0

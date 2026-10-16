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
import http.server
import json
import logging
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Optional

from rich.console import Console
from rich.table import Table

from monika.core.security.credential_vault import vault
from monika.infrastructure.auth import (
    CALLBACK_PATH,
    DEFAULT_ANTIGRAVITY_PROXY_URL,
    DEFAULT_CALLBACK_PORT,
    OAuthCallbackHandler,
    check_antigravity_bridge_health,
    clear_oauth_accounts,
    delete_oauth_account,
    delete_oauth_tokens,
    exchange_antigravity_code,
    exchange_code_for_token,
    exchange_codex_code,
    generate_antigravity_pkce,
    generate_pkce_pair,
    get_antigravity_authorization_url,
    get_antigravity_home,
    get_antigravity_pool_summary,
    get_claude_authorization_url,
    get_claude_credentials_path,
    get_codex_cli_auth_path,
    get_oauth_accounts,
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
        tier = getattr(args, "tier", None)
        return login_provider(provider, tier=tier)
    if action == "logout":
        provider = getattr(args, "provider", None)
        email = getattr(args, "email", None)
        all_accounts = getattr(args, "all_accounts", False)
        return logout_provider(provider, email=email, all_accounts=all_accounts)

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

    # 2. OpenCode Go ($10/mo Multi-Model)
    opencode_key = vault.get_secret("OPENCODE_API_KEY") or os.getenv("OPENCODE_API_KEY")
    if opencode_key:
        oc_status = f"[{GREEN}]ACTIVE (Configured)[/]"
        oc_expiry = f"[{MUTED}]Subscription API Key[/]"
        oc_detail = f"[{MUTED}]OpenCode Go / Zen API[/]"
    else:
        oc_status = f"[{YELLOW}]NOT CONFIGURED[/]"
        oc_expiry = "—"
        oc_detail = "Run 'monika auth login opencode'"
    table.add_row("OpenCode Go", "OpenCode Go / Zen ($10)", oc_status, oc_expiry, oc_detail)

    # 3. Gemini (Antigravity Bridge / Google OAuth)
    accounts = get_oauth_accounts("antigravity")
    pool_summary = get_antigravity_pool_summary()
    agy_rec = get_oauth_tokens("antigravity")
    health = check_antigravity_bridge_health()
    installed = is_antigravity_installed()
    if accounts:
        paid_count = pool_summary.get("paid_accounts", 0)
        free_count = pool_summary.get("free_accounts", 0)
        active_count = pool_summary.get("active_accounts", 0)
        agy_status = f"[{GREEN}]ACTIVE ({len(accounts)} Accounts Pool)[/]"
        agy_expiry = f"[{GREEN}]{active_count} ready / {len(accounts)} total[/]"
        agy_detail = f"{paid_count} Paid, {free_count} Free (Round-Robin)"
    elif agy_rec and agy_rec.get("access_token"):
        exp_ts = get_token_expiry_timestamp(agy_rec)
        if is_token_expiring(agy_rec):
            agy_status = f"[{YELLOW}]EXPIRING / REFRESHABLE[/]"
        else:
            agy_status = f"[{GREEN}]ACTIVE (OAuth Token)[/]"
        agy_expiry = _format_expiry(exp_ts)
        agy_detail = f"Source: {agy_rec.get('source', 'google_antigravity_oauth')}"
    elif health.get("running") and health.get("authenticated"):
        agy_status = f"[{GREEN}]ONLINE (Proxy Connected)[/]"
        agy_expiry = f"[{MUTED}]Local Bridge Active[/]"
        agy_detail = f"[{GREEN}]{health.get('proxy_url')}[/]"
    elif installed:
        agy_status = f"[{YELLOW}]READY TO LOGIN[/]"
        agy_expiry = f"[{MUTED}]CLI Detected[/]"
        agy_detail = "Run 'monika auth login antigravity'"
    else:
        agy_status = f"[{MUTED}]NOT CONFIGURED[/]"
        agy_expiry = "—"
        agy_detail = "Run 'monika auth login antigravity'"
    table.add_row("Gemini", "Google Antigravity OAuth", agy_status, agy_expiry, agy_detail)

    # 4. Claude (Anthropic OAuth)
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

    # 5. ChatGPT (OpenAI Codex)
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

    if accounts:
        console.print(f"\n[bold {CYAN}]--- Antigravity Multi-Account Pool ({len(accounts)} accounts) ---[/]")
        pool_table = Table(show_header=True, header_style=f"bold {CYAN}", border_style="dim")
        pool_table.add_column("Email / Account", width=28)
        pool_table.add_column("Tier", width=12)
        pool_table.add_column("Status", width=18)
        pool_table.add_column("Expiry", width=24)
        pool_table.add_column("Model Scope", width=28)

        now = time.time()
        for acc in accounts:
            email = acc.get("email") or "primary"
            tier = acc.get("tier", "free")
            exp_ts = get_token_expiry_timestamp(acc)
            cooldown_until = acc.get("cooldown_until", 0.0)

            tier_str = f"[{GREEN}]PAID (Subs)[/]" if tier == "paid" else f"[{CYAN}]FREE TIER[/]"
            scope_str = "Gemini 4 Argon & Pro" if tier == "paid" else "Gemini 3.8 & 3.5 Flash"

            if cooldown_until > now:
                remaining = int(cooldown_until - now)
                status_str = f"[{YELLOW}]COOLDOWN ({remaining}s)[/]"
            elif is_token_expiring(acc):
                status_str = f"[{YELLOW}]EXPIRING / AUTO[/]"
            else:
                status_str = f"[{GREEN}]READY[/]"

            pool_table.add_row(email, tier_str, status_str, _format_expiry(exp_ts), scope_str)
        console.print(pool_table)

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


def login_provider(provider: Optional[str], tier: Optional[str] = None) -> int:
    """Authenticate with a specific subscription provider."""
    if not provider:
        console.print(f"{stamp_err('ERROR')} Please specify a provider: zai, opencode, antigravity, claude, codex")
        return 1

    p = provider.strip().lower()

    if p in ("zai", "glm", "z-ai", "z.ai"):
        return _login_zai()
    elif p in ("opencode", "opencode_go", "opencode-go"):
        return _login_opencode()
    elif p in ("claude", "anthropic"):
        return _login_claude()
    elif p in ("codex", "chatgpt", "openai"):
        return _login_codex()
    elif p in ("antigravity", "gemini", "agy"):
        return _login_antigravity(tier=tier)
    else:
        console.print(
            f"{stamp_err('ERROR')} Unknown provider '{provider}'. Choose from: zai, opencode, antigravity, claude, codex"
        )
        return 1


def _login_opencode() -> int:
    """Interactive login for OpenCode Go subscription ($10/mo multi-model)."""
    console.print(f"\n[bold {BRASS}]=== OPENCODE GO / ZEN SUBSCRIPTION AUTHENTICATION ===[/]\n")
    console.print(f"  [{MUTED}]Obtain your API Key from your OpenCode Console at https://opencode.ai[/]")
    console.print(f"  [{MUTED}]Supported models: DeepSeek V3/R1, GLM-5/4, Qwen Coder, Kimi, Claude Haiku, etc.[/]\n")

    key = getpass.getpass("Enter your OpenCode API Key (oc_sk_...): ").strip()
    if not key:
        console.print(f"{stamp_err('ABORTED')} No API key entered.")
        return 1

    # Validate against models endpoint
    console.print(f"{stamp_info('VERIFYING')} Testing connection to OpenCode API...")
    req = urllib.request.Request(
        "https://opencode.ai/inference/go/openai/v1/models",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "Monika-TradingAgent/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                vault.set_secret("OPENCODE_API_KEY", key)
                save_oauth_tokens("opencode", {"api_key": key, "source": "opencode_go_subscription"})
                console.print(f"{stamp_ok('SUCCESS')} OpenCode Go credentials saved and verified successfully!\n")
                return 0
    except urllib.error.HTTPError as err:
        console.print(f"{stamp_err('VALIDATION FAILED')} OpenCode returned HTTP {err.code}: {err.reason}")
        ans = input("Save key anyway without online verification? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            vault.set_secret("OPENCODE_API_KEY", key)
            save_oauth_tokens("opencode", {"api_key": key, "source": "opencode_go_subscription"})
            console.print(f"{stamp_ok('SAVED')} Key saved to CredentialVault.\n")
            return 0
        return 1
    except Exception as exc:
        console.print(f"{stamp_err('CONNECTION FAILED')} Could not connect to OpenCode: {exc}")
        ans = input("Save key anyway without online verification? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            vault.set_secret("OPENCODE_API_KEY", key)
            save_oauth_tokens("opencode", {"api_key": key, "source": "opencode_go_subscription"})
            console.print(f"{stamp_ok('SAVED')} Key saved to CredentialVault.\n")
            return 0
        return 1

    return 0


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


def _login_antigravity(tier: Optional[str] = None) -> int:
    """Interactive Google Desktop OAuth login for Antigravity & Gemini subscriptions."""
    console.print(f"\n[bold {BRASS}]=== GOOGLE GEMINI ANTIGRAVITY OAUTH SETUP ===[/]\n")

    # Step 1: Check existing accounts and tokens
    accounts = get_oauth_accounts("antigravity")
    existing = get_oauth_tokens("antigravity")
    if accounts or (existing and existing.get("access_token")):
        total = len(accounts) if accounts else 1
        console.print(f"  [{GREEN}]Found active Google Antigravity OAuth session ({total} account(s)).[/]")
        if accounts:
            for acc in accounts:
                t = acc.get("tier", "free")
                e = acc.get("email") or "primary"
                console.print(f"    • {e} ([{GREEN if t == 'paid' else CYAN}]{t.upper()}[/])")
        elif existing and existing.get("access_token"):
            exp_ts = get_token_expiry_timestamp(existing)
            console.print(f"  Status: {_format_expiry(exp_ts)}")
        try:
            ans = input("  Do you want to add/re-authenticate another account? [y/N]: ").strip().lower()
        except EOFError, KeyboardInterrupt, OSError:
            ans = "n"
        if ans not in ("y", "yes"):
            console.print(f"{stamp_ok('ACTIVE')} Existing Antigravity session retained.\n")
            return 0

    # Step 2: Determine Tier
    if not tier or tier not in ("paid", "free"):
        console.print("\n  [bold]Select Account Tier:[/]")
        console.print("  [1] Paid / Subscription (Primary - Gemini 4 Argon & Gemini Pro)")
        console.print("  [2] Free Tier (Rotated Round-Robin - Gemini 3.8 / 3.5 Flash)")
        try:
            choice = input("  Select tier [1=paid, 2=free] (default: 2): ").strip()
            tier = "paid" if choice == "1" else "free"
        except EOFError, KeyboardInterrupt, OSError:
            tier = "free"

    tier_label = "Paid Subscription" if tier == "paid" else "Free Tier"
    console.print(f"  Target Tier: [bold {CYAN}]{tier_label}[/]\n")

    home = get_antigravity_home()
    if is_antigravity_installed():
        console.print(f"{stamp_ok('DETECTED')} Google Antigravity CLI installation found at:")
        console.print(f"  [{MUTED}]{home}[/]\n")

    # Step 2: Prepare PKCE & Google Auth URL
    console.print(f"  [{MUTED}]Preparing Google Desktop OAuth 2.0 PKCE flow...[/]")
    verifier, challenge = generate_antigravity_pkce()
    state = f"monika_agy_{secrets.token_hex(8)}"
    redirect_uri = f"http://127.0.0.1:{DEFAULT_CALLBACK_PORT}{CALLBACK_PATH}"
    auth_url = get_antigravity_authorization_url(challenge, state, redirect_uri=redirect_uri)

    # Step 3: Start temporary local callback listener
    server: Optional[http.server.HTTPServer] = None
    ready_event = threading.Event()
    OAuthCallbackHandler.expected_state = state
    OAuthCallbackHandler.captured_code = None
    OAuthCallbackHandler.captured_error = None
    OAuthCallbackHandler.ready = ready_event

    try:
        server = http.server.HTTPServer(("127.0.0.1", DEFAULT_CALLBACK_PORT), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        logger.debug("Started local OAuth callback server on port %d", DEFAULT_CALLBACK_PORT)
    except OSError as exc:
        logger.warning(
            "Could not bind port %d: %s. Proceeding with manual paste fallback.",
            DEFAULT_CALLBACK_PORT,
            exc,
        )
        server = None

    console.print("\n  [bold]Follow these steps to authenticate your Google Account:[/]")
    console.print("  1. Opening browser for Google Sign-In...")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    console.print("     If the browser did not open automatically, visit:")
    console.print(f"     [bold {CYAN}]{auth_url}[/]\n")
    console.print("  2. Select your Google account and grant permissions on Google consent screen.")
    console.print(f"  3. After sign-in, Google will redirect to localhost:{DEFAULT_CALLBACK_PORT} automatically.\n")

    code: Optional[str] = None
    if server:
        console.print(f"  [{MUTED}]Waiting for browser redirect callback... (Press Ctrl+C to enter code manually)[/]")
        try:
            signaled = ready_event.wait(timeout=120.0)
            if signaled:
                if OAuthCallbackHandler.captured_error:
                    console.print(f"{stamp_err('OAUTH ERROR')} {OAuthCallbackHandler.captured_error}")
                    return 1
                code = OAuthCallbackHandler.captured_code
            else:
                console.print(f"{stamp_warn('TIMEOUT')} Browser callback not received within 120 seconds.")
        except KeyboardInterrupt:
            console.print(f"\n{stamp_info('INTERRUPT')} Switching to manual code entry.")
        finally:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass

    if not code:
        console.print(
            f"\n  [{MUTED}]Paste the full redirect URL (http://127.0.0.1:8085/...) or the 'code' parameter below:[/]"
        )
        try:
            code_or_url = input("Paste code or redirect URL here: ").strip()
        except EOFError, KeyboardInterrupt, OSError:
            code_or_url = ""
        if not code_or_url:
            console.print(f"{stamp_err('ABORTED')} No authorization code provided.")
            return 1
        code = code_or_url
        if "code=" in code_or_url:
            parsed = urllib.parse.urlparse(code_or_url)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [code_or_url])[0]

    console.print(f"{stamp_info('EXCHANGING')} Exchanging authorization code with Google OAuth endpoint...")
    token_record = exchange_antigravity_code(code, verifier, redirect_uri=redirect_uri, tier=tier)
    if token_record and token_record.get("access_token"):
        account_email = token_record.get("email") or "primary"
        console.print(
            f"{stamp_ok('SUCCESS')} Successfully authenticated Google account: [bold {GREEN}]{account_email}[/]!"
        )
        console.print(f"  Tier assigned: [bold {CYAN}]{tier.upper()}[/]")

        pool = get_oauth_accounts("antigravity")
        console.print(f"  Account pool now has [bold {GREEN}]{len(pool)}[/] account(s) registered.\n")
        return 0

    console.print(f"{stamp_err('FAILED')} Token exchange failed. Please verify and try again.\n")
    return 1


def logout_provider(provider: Optional[str], email: Optional[str] = None, all_accounts: bool = False) -> int:
    """Remove OAuth tokens or accounts for a specific provider."""
    if not provider:
        console.print(
            f"{stamp_err('ERROR')} Please specify a provider to logout: zai, opencode, antigravity, claude, codex"
        )
        return 1

    p = provider.strip().lower()
    mapping = {
        "zai": "zai",
        "glm": "zai",
        "opencode": "opencode",
        "opencode_go": "opencode",
        "opencode-go": "opencode",
        "claude": "anthropic",
        "anthropic": "anthropic",
        "codex": "codex",
        "chatgpt": "codex",
        "antigravity": "antigravity",
        "gemini": "antigravity",
        "agy": "antigravity",
    }
    target = mapping.get(p)
    if not target:
        console.print(
            f"{stamp_err('ERROR')} Unknown provider '{provider}'. Choose from: zai, opencode, antigravity, claude, codex"
        )
        return 1

    if target == "antigravity":
        if all_accounts:
            clear_oauth_accounts("antigravity")
            delete_oauth_tokens("antigravity")
            console.print(f"{stamp_ok('SUCCESS')} Cleared all Antigravity accounts from pool and vault.\n")
            return 0
        elif email:
            deleted = delete_oauth_account("antigravity", email)
            if deleted:
                console.print(f"{stamp_ok('SUCCESS')} Removed account '{email}' from Antigravity pool.\n")
                return 0
            else:
                console.print(f"{stamp_err('NOT FOUND')} Account '{email}' was not found in Antigravity pool.\n")
                return 1
        else:
            accounts = get_oauth_accounts("antigravity")
            if not accounts:
                delete_oauth_tokens("antigravity")
                console.print(f"{stamp_ok('SUCCESS')} No active Antigravity accounts found.\n")
                return 0
            if len(accounts) == 1:
                acc_email = accounts[0].get("email") or "primary"
                delete_oauth_account("antigravity", acc_email)
                delete_oauth_tokens("antigravity")
                console.print(f"{stamp_ok('SUCCESS')} Removed account '{acc_email}' from Antigravity pool.\n")
                return 0

            console.print(f"{stamp_warn('MULTIPLE ACCOUNTS')} Antigravity pool has {len(accounts)} accounts:")
            for acc in accounts:
                console.print(f"  • {acc.get('email')} ({acc.get('tier', 'free')})")
            console.print("\nSpecify which account to remove with:")
            console.print("  python -m monika.interfaces.cli.main auth logout antigravity --email <email>")
            console.print("Or remove all accounts with:")
            console.print("  python -m monika.interfaces.cli.main auth logout antigravity --all\n")
            return 1

    # Delete from vault and oauth_store for other providers
    delete_oauth_tokens(target)
    if target == "zai":
        vault.delete_secret("ZAI_API_KEY")
    elif target == "opencode":
        vault.delete_secret("OPENCODE_API_KEY")

    console.print(f"{stamp_ok('SUCCESS')} Successfully logged out from {provider}. Credentials cleared from vault.\n")
    return 0

"""
Unit Tests for Trading Agent CLI Entrypoint (cli/main.py).
"""
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch
from cli.main import parse_args, _acli_run


def test_cli_parse_args_defaults():
    """Verify default CLI arguments."""
    args = parse_args([])
    assert args.mode == "paper"
    assert args.config is None


def test_cli_parse_args_custom():
    """Verify custom CLI arguments."""
    args = parse_args(["--mode", "live", "--config", "custom_settings.yaml"])
    assert args.mode == "live"
    assert args.config == "custom_settings.yaml"


@pytest.mark.asyncio
async def test_acli_run_paper_mode():
    """Verify _acli_run properly configures paper mode and calls TradingAgent."""
    args = parse_args(["--mode", "paper"])
    
    mock_settings = {"trading": {}, "paper_trading": {}}
    mock_agent = MagicMock()
    mock_agent.start = AsyncMock()

    with patch("cli.main.acquire_single_instance_lock", return_value=True), \
         patch("cli.main.load_all_config", return_value=mock_settings), \
         patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.run_startup_checks", AsyncMock(return_value=True)), \
         patch("cli.main.TradingAgent", return_value=mock_agent) as MockAgentClass:

        await _acli_run(args)
        
        # Verify TradingAgent instantiation
        MockAgentClass.assert_called_once_with(settings=mock_settings, dry_run=True)
        assert mock_settings["paper_trading"]["enabled"] is True
        mock_agent.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_acli_run_live_mode():
    """Verify _acli_run properly configures live mode with dry_run=False."""
    args = parse_args(["--mode", "live", "--confirm-live"])
    
    mock_settings = {"trading": {}}
    mock_agent = MagicMock()
    mock_agent.start = AsyncMock()

    with patch("cli.main.acquire_single_instance_lock", return_value=True), \
         patch("cli.main.load_all_config", return_value=mock_settings), \
         patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.run_startup_checks", AsyncMock(return_value=True)), \
         patch("cli.main.TradingAgent", return_value=mock_agent) as MockAgentClass:

        await _acli_run(args)
        
        # Verify TradingAgent instantiation
        MockAgentClass.assert_called_once_with(settings=mock_settings, dry_run=False)
        assert mock_settings["trading"]["auto_execute"] is True
        mock_agent.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_cli_subcommand_status(capsys):
    """Verify _cmd_status prints system configs and open position counts."""
    from cli.main import _cmd_status
    args = parse_args(["status"])

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_status(args)

    captured = capsys.readouterr().out
    assert "AI TRADING AGENT STATUS" in captured
    assert "Open Real Positions" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_pause(capsys):
    """Verify _cmd_pause sets system_paused = true in database."""
    from cli.main import _cmd_pause
    args = parse_args(["pause"])

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_cfg = None
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_pause(args)

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    captured = capsys.readouterr().out
    assert "System trading paused successfully" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_resume_with_yes(capsys):
    """Verify _cmd_resume with -y clears pause flags without interactive prompt."""
    from cli.main import _cmd_resume
    args = parse_args(["resume", "-y"])

    mock_session = AsyncMock()
    mock_cfg = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_resume(args)

    assert mock_cfg.value == "false"
    mock_session.commit.assert_awaited_once()
    captured = capsys.readouterr().out
    assert "System trading resumed" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_kill(capsys):
    """Verify _cmd_kill with -y sets kill_switch = true."""
    from cli.main import _cmd_kill
    args = parse_args(["kill", "-y"])

    mock_session = AsyncMock()
    mock_cfg = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_kill(args)

    assert mock_cfg.value == "true"
    mock_session.commit.assert_awaited_once()
    captured = capsys.readouterr().out
    assert "EMERGENCY KILL SWITCH" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_positions(capsys):
    """Verify _cmd_positions prints real and paper positions."""
    from cli.main import _cmd_positions
    args = parse_args(["positions"])

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_positions(args)

    captured = capsys.readouterr().out
    assert "OPEN REAL POSITIONS" in captured
    assert "OPEN PAPER POSITIONS" in captured


def test_cli_parse_args_tui():
    """Verify parse_args for tui subcommand."""
    args = parse_args(["tui", "--url", "http://127.0.0.1:9000", "--refresh", "10", "--token", "secret123"])
    assert args.command == "tui"
    assert args.url == "http://127.0.0.1:9000"
    assert args.refresh == 10
    assert args.token == "secret123"


def test_cli_parse_args_chat():
    """Verify parse_args for chat subcommand."""
    args = parse_args(["chat", "--model", "analyze", "--offline", "--session-id", "test_sess"])
    assert args.command == "chat"
    assert args.model == "analyze"
    assert args.offline is True
    assert args.session_id == "test_sess"


def test_cli_parse_args_config_show():
    """Verify parse_args for config show."""
    args = parse_args(["config", "show", "trading.risk", "--json"])
    assert args.command == "config"
    assert args.config_action == "show"
    assert args.section == "trading.risk"
    assert args.json is True


def test_cli_parse_args_config_set():
    """Verify parse_args for config set."""
    args = parse_args(["config", "set", "trading.risk.max_daily_drawdown_percent=4.0", "--reason", "audit test"])
    assert args.command == "config"
    assert args.config_action == "set"
    assert args.assignments == ["trading.risk.max_daily_drawdown_percent=4.0"]
    assert args.reason == "audit test"


def test_cli_parse_args_sessions():
    """Verify parse_args for sessions subcommand."""
    args = parse_args(["sessions", "--source", "dashboard", "--limit", "15"])
    assert args.command == "sessions"
    assert args.source == "dashboard"
    assert args.limit == 15


def test_cli_parse_args_logs():
    """Verify parse_args for logs subcommand."""
    args = parse_args(["logs", "-n", "50", "-f", "--category", "trade"])
    assert args.command == "logs"
    assert args.lines == 50
    assert args.follow is True
    assert args.category == "trade"


@pytest.mark.asyncio
async def test_cli_subcommand_config_show(capsys):
    """Verify _cmd_config_show prints configuration sections."""
    from cli.main import _cmd_config_show
    args = parse_args(["config", "show", "trading.risk"])

    mock_settings = {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
            }
        }
    }

    with patch("cli.main.load_settings", return_value=mock_settings):
        await _cmd_config_show(args)

    captured = capsys.readouterr().out
    assert "Configuration: trading.risk" in captured
    assert "max_daily_drawdown_percent" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_config_show_missing_section(capsys):
    """Verify _cmd_config_show handles non-existent section gracefully."""
    from cli.main import _cmd_config_show
    args = parse_args(["config", "show", "nonexistent.section"])

    with patch("cli.main.load_settings", return_value={"trading": {}}):
        await _cmd_config_show(args)

    captured = capsys.readouterr().out
    assert "not found" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_config_set_validation(tmp_path, capsys):
    """Verify _cmd_config_set validates configuration schema before writing."""
    from cli.main import _cmd_config_set
    args = parse_args(["config", "set", "invalid_assignment_without_equals"])
    await _cmd_config_set(args)
    captured = capsys.readouterr().out
    assert "Invalid assignment" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_config_set_local_success(tmp_path, capsys):
    """Verify _cmd_config_set updates configuration file and creates backup."""
    from cli.main import _cmd_config_set
    from unittest.mock import mock_open

    dummy_settings = {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 3.0,
                "max_concurrent_positions": 5,
                "max_weekly_drawdown_percent": 8.0,
            }
        }
    }

    dummy_file = tmp_path / "settings.yaml"
    dummy_file.write_text(yaml.dump(dummy_settings), encoding="utf-8")

    args = parse_args(["config", "set", "trading.risk.max_daily_drawdown_percent=4.0", "--config", str(dummy_file)])

    with patch("cli.main.load_settings", return_value=dummy_settings), \
         patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_sess, \
         patch("builtins.open", mock_open()), \
         patch("shutil.copy2"), \
         patch("os.replace") as mock_replace:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_config_set(args)

    captured = capsys.readouterr().out
    assert "Configuration updated and verified" in captured
    assert mock_replace.called


@pytest.mark.asyncio
async def test_cli_subcommand_sessions(capsys):
    """Verify _cmd_sessions formats and prints active sessions."""
    from cli.main import _cmd_sessions
    args = parse_args(["sessions", "--source", "all"])

    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.telegram_user_id = "dash:admin"
    mock_row.message_count = 10
    mock_row.last_active = None

    mock_res1 = MagicMock()
    mock_res1.all.return_value = [mock_row]

    mock_res2 = MagicMock()
    mock_res2.first.return_value = ("Recent message test",)

    mock_session.execute.side_effect = [mock_res1, mock_res2]

    with patch("cli.main.init_db", AsyncMock()), patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_sessions(args)

    captured = capsys.readouterr().out
    assert "Conversation Sessions" in captured
    assert "dash:admin" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_logs(capsys):
    """Verify _cmd_logs fetches and renders activity entries."""
    from cli.main import _cmd_logs
    args = parse_args(["logs", "-n", "5"])

    mock_log = MagicMock()
    mock_log.id = 1
    mock_log.timestamp = None
    mock_log.category = "trade"
    mock_log.actor = "guardian"
    mock_log.description = "Trailing stop modified for EURUSD"

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_log]
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_logs(args)

    captured = capsys.readouterr().out
    assert "TRADE" in captured
    assert "guardian" in captured
    assert "Trailing stop" in captured


@pytest.mark.asyncio
async def test_tui_dashboard_mount():
    """Verify TradingDashboard mounts cleanly in headless mode."""
    from cli.tui import TradingDashboard, LiveTickerBanner, StatusBar
    from textual.widgets import DataTable, RichLog, Input

    app = TradingDashboard(standalone=True)
    async with app.run_test() as pilot:
        # Check widgets mounted
        assert app.query_one("#ticker", LiveTickerBanner) is not None
        assert app.query_one("#positions_table", DataTable) is not None
        assert app.query_one("#activity_log", RichLog) is not None
        assert app.query_one("#status_bar", StatusBar) is not None

        # Verify command execution in TUI
        input_widget = app.query_one("#cmd_input", Input)
        app.post_message(Input.Submitted(input_widget, "help"))
        await pilot.pause(0.1)

        # Check activity log received help
        log = app.query_one("#activity_log", RichLog)
        assert len(log.lines) > 0


@pytest.mark.asyncio
async def test_tui_chat_screen_actions():
    """Verify ChatScreen mounts and actions work properly."""
    from cli.tui_chat import ChatScreen
    from textual.app import App, ComposeResult
    from textual.widgets import RichLog, Static

    class DummyChatApp(App):
        def compose(self) -> ComposeResult:
            yield Static("Root")

    app = DummyChatApp()
    async with app.run_test() as pilot:
        chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
        await app.push_screen(chat_screen)

        transcript = chat_screen.query_one("#transcript", RichLog)
        assert transcript is not None

        # Clear transcript action
        await chat_screen.action_clear_transcript()
        assert len(transcript.lines) > 0


@pytest.mark.asyncio
async def test_cli_subcommand_config_set_api_permission_error(capsys):
    """Verify _cmd_config_set halts on 401/403 API response and does not touch local files."""
    from cli.main import _cmd_config_set

    args = parse_args(["config", "set", "trading.risk.max_concurrent_positions=10", "--token", "viewer_token"])

    mock_resp = MagicMock()
    mock_resp.status = 403

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.put = AsyncMock(return_value=mock_resp)

    with patch("aiohttp.ClientSession", return_value=mock_session), \
         patch("builtins.open") as mock_file:
        await _cmd_config_set(args)
        # Verify local file was NOT opened for writing
        mock_file.assert_not_called()

    captured = capsys.readouterr().out
    assert "Permission denied" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_config_set_json_list(tmp_path, capsys):
    """Verify _cmd_config_set parses JSON arrays for settings like symbols."""
    from cli.main import _cmd_config_set
    from unittest.mock import mock_open

    dummy_settings = {
        "trading": {
            "symbols": ["EURUSD"],
            "risk": {"max_daily_drawdown_percent": 3.0, "max_concurrent_positions": 5},
        }
    }

    dummy_file = tmp_path / "settings.yaml"
    dummy_file.write_text(yaml.dump(dummy_settings), encoding="utf-8")

    args = parse_args(["config", "set", 'trading.symbols=["EURUSD","XAUUSD"]', "--config", str(dummy_file)])

    with patch("cli.main.load_settings", return_value=dummy_settings), \
         patch("cli.main.init_db", AsyncMock()), \
         patch("cli.main.get_session") as mock_sess, \
         patch("builtins.open", mock_open()) as mocked_file, \
         patch("shutil.copy2"), \
         patch("os.replace") as mock_replace:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_config_set(args)

    captured = capsys.readouterr().out
    assert "Configuration updated and verified" in captured
    assert mock_replace.called


@pytest.mark.asyncio
async def test_cli_subcommand_sessions_source_cli(capsys):
    """Verify _cmd_sessions correctly filters for CLI sessions with source='cli'."""
    from cli.main import _cmd_sessions
    args = parse_args(["sessions", "--source", "cli"])

    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.telegram_user_id = "cli:tui_user"
    mock_row.message_count = 5
    mock_row.last_active = None

    mock_res1 = MagicMock()
    mock_res1.all.return_value = [mock_row]
    mock_res2 = MagicMock()
    mock_res2.first.return_value = ("Hello from CLI",)

    mock_session.execute.side_effect = [mock_res1, mock_res2]

    with patch("cli.main.init_db", AsyncMock()), patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_sessions(args)

    captured = capsys.readouterr().out
    assert "Conversation Sessions" in captured
    assert "cli:tui_user" in captured
    assert "CLI" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_sessions_source_telegram(capsys):
    """Verify _cmd_sessions excludes dashboard and CLI sessions when source='telegram'."""
    from cli.main import _cmd_sessions
    args = parse_args(["sessions", "--source", "telegram"])

    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.telegram_user_id = "123456789"
    mock_row.message_count = 12
    mock_row.last_active = None

    mock_res1 = MagicMock()
    mock_res1.all.return_value = [mock_row]
    mock_res2 = MagicMock()
    mock_res2.first.return_value = ("Telegram message",)

    mock_session.execute.side_effect = [mock_res1, mock_res2]

    with patch("cli.main.init_db", AsyncMock()), patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_sessions(args)

    captured = capsys.readouterr().out
    assert "Conversation Sessions" in captured
    assert "123456789" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_logs_with_severity(capsys):
    """Verify _cmd_logs filters by severity level when provided."""
    from cli.main import _cmd_logs
    args = parse_args(["logs", "-n", "10", "--level", "error"])

    mock_log = MagicMock()
    mock_log.id = 42
    mock_log.timestamp = None
    mock_log.category = "error"
    mock_log.actor = "circuit_breaker"
    mock_log.description = "Critical threshold exceeded"

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_log]
    mock_session.execute.return_value = mock_res

    with patch("cli.main.init_db", AsyncMock()), patch("cli.main.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = mock_session
        await _cmd_logs(args)

    captured = capsys.readouterr().out
    assert "ERROR" in captured
    assert "circuit_breaker" in captured


@pytest.mark.asyncio
async def test_cli_subcommand_chat_invocation():
    """Verify _cmd_chat passes arguments to run_cli_chat."""
    from cli.main import _cmd_chat
    args = parse_args(["chat", "--model", "fast", "--offline", "--session-id", "sess_abc"])

    with patch("cli.tui_chat.run_cli_chat", AsyncMock()) as mock_run:
        await _cmd_chat(args)
        mock_run.assert_awaited_once_with(
            api_url="http://127.0.0.1:8000",
            api_key=None,
            session_id="sess_abc",
            offline=True,
            model="fast",
        )


@pytest.mark.asyncio
async def test_tui_command_bar_autocomplete_and_commands():
    """Verify TUI command bar has autocomplete suggester and handles config, sessions, logs commands."""
    from cli.tui import TradingDashboard, LiveTickerBanner, StatusBar
    from textual.widgets import Input, RichLog, DataTable

    app = TradingDashboard(standalone=True)
    async with app.run_test() as pilot:
        input_widget = app.query_one("#cmd_input", Input)

        # 1. Check autocomplete suggester is attached
        assert input_widget.suggester is not None

        # 2. Test navigation actions
        await app.action_focus_input()
        await pilot.pause(0.05)
        assert input_widget.has_focus

        await app.action_blur_input()
        await pilot.pause(0.05)
        assert not input_widget.has_focus

        # 3. Test config command in TUI
        app.post_message(Input.Submitted(input_widget, "config trading.risk"))
        await pilot.pause(0.1)

        # 4. Test sessions command in TUI
        with patch("database.db.get_session") as mock_get_sess:
            mock_sess = AsyncMock()
            mock_res = MagicMock()
            mock_res.all.return_value = []
            mock_sess.execute.return_value = mock_res
            mock_get_sess.return_value.__aenter__.return_value = mock_sess
            app.post_message(Input.Submitted(input_widget, "sessions"))
            await pilot.pause(0.1)

        # 5. Test logs command in TUI
        app.post_message(Input.Submitted(input_widget, "logs"))
        await pilot.pause(0.1)

        log = app.query_one("#activity_log", RichLog)
        assert len(log.lines) > 0


@pytest.mark.asyncio
async def test_tui_ws_event_tick_preserves_position_counts():
    """Verify _handle_ws_event with tick updates quotes and preserves real/paper position counts."""
    from cli.tui import TradingDashboard, LiveTickerBanner

    app = TradingDashboard(standalone=True)
    async with app.run_test() as pilot:
        # Simulate populated counts
        app.real_count = 3
        app.paper_count = 5

        # Handle a tick event
        tick_event = {
            "type": "tick",
            "payload": {"symbol": "EURUSD", "bid": 1.0875},
        }
        await app._handle_ws_event(tick_event)
        await pilot.pause(0.1)

        # Verify quote updated
        assert app._quotes.get("EURUSD") == 1.0875
        # Verify counts preserved on self
        assert app.real_count == 3
        assert app.paper_count == 5


@pytest.mark.asyncio
async def test_tui_chat_screen_streaming():
    """Verify ChatScreen token streaming updates streaming_output widget and finalizes to transcript."""
    from cli.tui_chat import ChatScreen
    from textual.app import App, ComposeResult
    from textual.widgets import RichLog, Static

    class DummyChatApp(App):
        def compose(self) -> ComposeResult:
            yield Static("Root")

    app = DummyChatApp()
    async with app.run_test() as pilot:
        chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
        await app.push_screen(chat_screen)

        streaming_widget = chat_screen.query_one("#streaming_output", Static)
        assert streaming_widget is not None

        # Test local turn execution with live streaming to streaming_output
        mock_agent = MagicMock()
        mock_agent.handle = AsyncMock(return_value=("This is a streaming test reply.", None))
        chat_screen._local_agent = mock_agent

        await chat_screen._run_local_turn("Hello agent")
        await pilot.pause(0.1)

        # Verify streaming widget was cleared after completion
        assert str(streaming_widget.render()) == ""

        # Verify transcript contains completed reply
        transcript = chat_screen.query_one("#transcript", RichLog)
        assert len(transcript.lines) > 0


@pytest.mark.asyncio
async def test_run_cli_chat_fallback_on_ws_disconnect(capsys):
    """Verify run_cli_chat lazily instantiates local_agent when WebSocket drops mid-session."""
    from cli.tui_chat import run_cli_chat

    mock_agent = MagicMock()
    mock_agent.handle = AsyncMock(return_value=("Fallback response from local agent", None))

    # Mock inputs: first message, then exit
    inputs = iter(["Test message", "/exit"])

    with patch("cli.tui_chat._get_prompt_session", return_value=None), \
         patch("asyncio.to_thread", side_effect=lambda fn, prompt: next(inputs)), \
         patch("telegram_bot.chat_agent.ChatAgent", return_value=mock_agent), \
         patch("cli.tui_chat.load_settings", return_value={}):
        # Run with offline=True to trigger local engine directly
        await run_cli_chat(offline=True)

    mock_agent.handle.assert_awaited_once_with("Test message")


def test_is_ws_alive():
    """Verify is_ws_alive handles None, closed, closing transport, and open transport."""
    from cli.tui_chat import is_ws_alive

    # 1. None
    assert is_ws_alive(None) is False

    # 2. ws.closed == True
    mock_ws = MagicMock()
    mock_ws.closed = True
    assert is_ws_alive(mock_ws) is False

    # 3. ws.closed == False, but transport is closing (idle timeout scenario)
    mock_ws.closed = False
    mock_writer = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_closing.return_value = True
    mock_writer.transport = mock_transport
    mock_ws._writer = mock_writer
    assert is_ws_alive(mock_ws) is False

    # 4. ws fully alive
    mock_transport.is_closing.return_value = False
    assert is_ws_alive(mock_ws) is True


@pytest.mark.asyncio
async def test_tui_chat_auto_reconnect_on_stale_ws():
    """Verify ChatScreen automatically reconnects when sending on a stale/closing WebSocket."""
    from cli.tui_chat import ChatScreen
    import aiohttp

    chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")

    # Setup stale ws: closed=False but transport.is_closing()=True
    stale_ws = MagicMock()
    stale_ws.closed = False
    stale_writer = MagicMock()
    stale_transport = MagicMock()
    stale_transport.is_closing.return_value = True
    stale_writer.transport = stale_transport
    stale_ws._writer = stale_writer
    chat_screen._ws = stale_ws

    # New fresh ws
    fresh_ws = MagicMock()
    fresh_ws.closed = False
    fresh_ws.send_json = AsyncMock()
    fresh_msg = MagicMock()
    fresh_msg.type = aiohttp.WSMsgType.TEXT
    fresh_msg.data = '{"type": "complete", "text": "OK reply"}'
    fresh_ws.receive = AsyncMock(return_value=fresh_msg)

    with patch.object(chat_screen, "_connect_ws", AsyncMock(return_value=True)) as mock_conn, \
         patch.object(chat_screen, "query_one") as mock_query:
        mock_log = MagicMock()
        mock_query.return_value = mock_log
        # Once connected, _ws becomes fresh_ws
        async def do_connect():
            chat_screen._ws = fresh_ws
            return True
        mock_conn.side_effect = do_connect

        await chat_screen._run_ws_turn("Halo Monika")

        mock_conn.assert_awaited_once()
        fresh_ws.send_json.assert_awaited_once_with({"type": "message", "text": "Halo Monika"})


@pytest.mark.asyncio
async def test_tui_chat_fallback_to_local_on_ws_error():
    """Verify ChatScreen falls back to local execution if WebSocket connection permanently fails."""
    from cli.tui_chat import ChatScreen

    chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
    chat_screen._ws = None

    with patch.object(chat_screen, "_connect_ws", AsyncMock(return_value=False)), \
         patch.object(chat_screen, "_run_local_turn", AsyncMock()) as mock_local, \
         patch.object(chat_screen, "query_one") as mock_query:
        mock_query.return_value = MagicMock()

        await chat_screen._run_ws_turn("Test fallback")

        mock_local.assert_awaited_once_with("Test fallback")


@pytest.mark.asyncio
async def test_tui_chat_action_interrupt_via_ws():
    """Verify action_interrupt sends interrupt JSON signal through active WebSocket."""
    from cli.tui_chat import ChatScreen

    chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
    mock_ws = MagicMock()
    mock_ws.closed = False
    mock_ws._writer = MagicMock()
    mock_ws._writer.transport = MagicMock()
    mock_ws._writer.transport.is_closing.return_value = False
    mock_ws.send_json = AsyncMock()
    chat_screen._ws = mock_ws

    with patch.object(chat_screen, "query_one") as mock_query:
        mock_log = MagicMock()
        mock_query.return_value = mock_log
        await chat_screen.action_interrupt()

        mock_ws.send_json.assert_awaited_once_with({"type": "interrupt"})
        mock_log.write.assert_called()


@pytest.mark.asyncio
async def test_tui_chat_action_interrupt_local_fallback():
    """Verify action_interrupt interrupts local agent when WebSocket is inactive."""
    from cli.tui_chat import ChatScreen

    chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
    chat_screen._ws = None
    mock_agent = MagicMock()
    chat_screen._local_agent = mock_agent

    with patch.object(chat_screen, "query_one") as mock_query:
        mock_log = MagicMock()
        mock_query.return_value = mock_log
        await chat_screen.action_interrupt()

        mock_agent.interrupt.assert_called_once_with("Turn interrupted by user.")
        mock_log.write.assert_called()


@pytest.mark.asyncio
async def test_tui_chat_handle_approval_decision_via_ws():
    """Verify _handle_approval_decision sends approval response payload through active WebSocket."""
    from cli.tui_chat import ChatScreen

    chat_screen = ChatScreen(api_url="http://127.0.0.1:8000")
    mock_ws = MagicMock()
    mock_ws.closed = False
    mock_ws._writer = MagicMock()
    mock_ws._writer.transport = MagicMock()
    mock_ws._writer.transport.is_closing.return_value = False
    mock_ws.send_json = AsyncMock()
    chat_screen._ws = mock_ws
    chat_screen._pending_action_id = "act-999"

    with patch.object(chat_screen, "query_one") as mock_query:
        mock_log = MagicMock()
        mock_query.return_value = mock_log
        await chat_screen._handle_approval_decision("act-999", "allow_once")

        mock_ws.send_json.assert_awaited_once_with({
            "type": "approval_response",
            "action_id": "act-999",
            "decision": "allow_once",
        })
        assert chat_screen._pending_action_id is None



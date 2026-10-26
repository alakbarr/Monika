import os
import time
import tempfile
import yaml
import pytest
from unittest.mock import MagicMock
from monika.domain.risk.risk_gate import RiskGate
from monika.core.config.hot_reload import RiskParameterReloader


def test_risk_gate_update_parameters():
    initial_settings = {
        "trading": {
            "risk": {"max_daily_drawdown_percent": 3.0, "max_concurrent_positions": 5, "news_window_minutes": 15}
        }
    }
    gate = RiskGate(initial_settings)
    assert gate.max_daily_drawdown_pct == 3.0
    assert gate.max_concurrent == 5
    assert gate.news_window_minutes == 15

    # Update with new parameters
    new_cfg = {
        "trading": {
            "risk": {"max_daily_drawdown_percent": 4.5, "max_concurrent_positions": 8, "news_window_minutes": 20}
        }
    }
    gate.update_parameters(new_cfg)
    assert gate.max_daily_drawdown_pct == 4.5
    assert gate.max_concurrent == 8
    assert gate.news_window_minutes == 20


def test_risk_parameter_reloader_file_watch():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump({"trading": {"risk": {"max_daily_drawdown_percent": 2.5, "max_concurrent_positions": 4}}}, tf)
        tmp_path = tf.name

    try:
        mock_gate = MagicMock()
        reloader = RiskParameterReloader(tmp_path, mock_gate)

        # No change yet
        assert reloader.check_and_reload() is False
        assert not mock_gate.update_parameters.called

        # Modify file and bump mtime
        time.sleep(0.05)
        with open(tmp_path, "w") as f:
            yaml.safe_dump({"trading": {"risk": {"max_daily_drawdown_percent": 5.0, "max_concurrent_positions": 7}}}, f)

        # Should detect change and update
        reloaded = reloader.check_and_reload()
        assert reloaded is True
        mock_gate.update_parameters.assert_called_once()
        args = mock_gate.update_parameters.call_args[0][0]
        assert args["trading"]["risk"]["max_daily_drawdown_percent"] == 5.0

        # Subsequent call without change should return False
        assert reloader.check_and_reload() is False

        # Modify file with invalid config (e.g. max_daily_drawdown_percent out of bounds)
        time.sleep(0.05)
        with open(tmp_path, "w") as f:
            yaml.safe_dump({"trading": {"risk": {"max_daily_drawdown_percent": 99.0}}}, f)

        # Should reject reload due to validation failure
        mock_gate.reset_mock()
        assert reloader.check_and_reload() is False
        assert not mock_gate.update_parameters.called
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@pytest.mark.asyncio
async def test_config_reloader_in_worker_thread_awaits_async_notifier(tmp_path):
    import asyncio
    import warnings

    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(
        yaml.safe_dump({"trading": {"risk": {"max_daily_drawdown_percent": 2.5, "max_concurrent_positions": 4}}}),
        encoding="utf-8",
    )

    sent_messages: list[str] = []

    class DummyNotifier:
        async def send_info(self, msg: str) -> None:
            sent_messages.append(msg)

    mock_gate = MagicMock()
    reloader = RiskParameterReloader(str(cfg_file), mock_gate, notifier=DummyNotifier())
    reloader._loop = asyncio.get_running_loop()

    cfg_file.write_text(
        yaml.safe_dump({"trading": {"risk": {"max_daily_drawdown_percent": 3.5, "max_concurrent_positions": 5}}}),
        encoding="utf-8",
    )
    future_mtime = (reloader.last_mtime or time.time()) + 10.0
    os.utime(cfg_file, (future_mtime, future_mtime))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        reloaded = await asyncio.to_thread(reloader.check_and_reload)
        await asyncio.sleep(0.05)

    assert reloaded is True
    assert sent_messages == ["Configuration hot-reloaded."]
    unawaited = [w for w in caught if "was never awaited" in str(w.message)]
    assert unawaited == []

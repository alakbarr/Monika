import pytest
import os
import tempfile
import shutil
from cli.doctor import SystemDoctor
from cli.profile_manager import ProfileManager
from config.settings import load_settings


@pytest.mark.asyncio
async def test_system_doctor_checks():
    doctor = SystemDoctor(fix=False)
    results = await doctor.run_diagnostics()
    assert len(results) > 0

    categories = {r.category for r in results}
    assert "Filesystem" in categories
    assert "Config" in categories
    assert "Credentials" in categories
    assert "MT5" in categories


def test_profile_manager_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = ProfileManager(root_dir=tmpdir)
        
        # 1. Default profile
        assert pm.get_active_profile_name() == "default"
        profiles = pm.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].name == "default"
        assert profiles[0].is_active

        # 2. Create new profile
        new_dir = pm.create_profile("prop_firm_50k")
        assert os.path.exists(new_dir)
        profiles = pm.list_profiles()
        assert len(profiles) == 2
        names = [p.name for p in profiles]
        assert "prop_firm_50k" in names

        # 3. Switch profile
        pm.set_active_profile("prop_firm_50k")
        assert pm.get_active_profile_name() == "prop_firm_50k"

        # 4. Switch back
        pm.set_active_profile("default")
        assert pm.get_active_profile_name() == "default"


def test_settings_disk_lkg_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = os.path.join(tmpdir, "settings.yaml")
        good_path = f"{cfg_path}.good"

        # 1. Write valid yaml
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("trading:\n  risk:\n    max_risk_per_trade_percent: 1.5\n")

        data = load_settings(path=cfg_path, validate=False)
        assert data["trading"]["risk"]["max_risk_per_trade_percent"] == 1.5
        assert os.path.exists(good_path)

        # 2. Corrupt the yaml file with syntax error
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("trading: risk: [corrupted syntax:\n  unbalanced: {{{")

        # 3. load_settings should recover from .good backup
        recovered = load_settings(path=cfg_path, validate=False)
        assert recovered["trading"]["risk"]["max_risk_per_trade_percent"] == 1.5

        # Check corrupt backup was created
        files = os.listdir(tmpdir)
        corrupt_files = [f for f in files if "corrupt" in f]
        assert len(corrupt_files) >= 1

"""
Tests for PR-23: VPS Deployment Guide + Docker Support.
Verifies docker-compose.vps.yml structure, Dockerfile.mt5-wine directives, install_vps.sh, install_vps.ps1, and deployment documentation.
"""

import yaml
import pytest


@pytest.fixture
def repo_root():
    from monika.core.paths import get_repo_root

    return get_repo_root()


def test_vps_docker_compose_valid_and_complete(repo_root):
    compose_path = repo_root / "deploy" / "docker-compose.vps.yml"
    assert compose_path.exists(), f"Missing {compose_path}"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    assert "services" in compose_data
    services = compose_data["services"]

    # Must define all 3 core services
    assert "db" in services
    assert "agent" in services
    assert "mt5-wine" in services

    # DB service uses pgvector and local-db profile
    assert "pgvector" in services["db"]["image"]
    assert "profiles" in services["db"]
    assert "local-db" in services["db"]["profiles"]

    # Agent depends on DB health (optional)
    assert "depends_on" in services["agent"]
    assert "db" in services["agent"]["depends_on"]
    assert services["agent"]["depends_on"]["db"]["required"] is False

    # Dashboard port binding supports remote VPS IP
    assert "ports" in services["agent"]
    assert any("8000:8000" in p for p in services["agent"]["ports"])

    # MT5 Wine service exists with shared volume bridge
    assert "volumes" in services["mt5-wine"]


def test_mt5_wine_dockerfile_directives(repo_root):
    dockerfile_path = repo_root / "deploy" / "Dockerfile.mt5-wine"
    assert dockerfile_path.exists()

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "wine" in content.lower()
    assert "xvfb" in content.lower()
    assert "ENTRYPOINT" in content


def test_vps_deployment_guide_exists(repo_root):
    guide_path = repo_root / "deploy" / "vps_deployment_guide.md"
    assert guide_path.exists()

    text = guide_path.read_text(encoding="utf-8")
    assert "Arsitektur Deployment VPS" in text
    assert "Persyaratan Minimum VPS" in text
    assert "docker compose" in text


def test_vps_installer_script_exists_and_valid(repo_root):
    installer_path = repo_root / "deploy" / "install_vps.sh"
    assert installer_path.exists()

    content = installer_path.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "set_env_var" in content
    assert "GEMINI_API_KEY" in content
    assert "docker compose" in content
    assert "DASHBOARD_API_KEY" in content
    assert ".monika_tier" in content


def test_vps_windows_installer_scripts_exist_and_valid(repo_root):
    ps1_path = repo_root / "deploy" / "install_vps.ps1"
    assert ps1_path.exists()
    ps1_content = ps1_path.read_text(encoding="utf-8")
    assert "New-NetFirewallRule" in ps1_content
    assert "DASHBOARD_BIND_IP" in ps1_content
    assert "api.ipify.org" in ps1_content
    assert "GEMINI_API_KEY" in ps1_content
    assert ".monika_tier" in ps1_content
    assert '-Argument "run"' in ps1_content

    bat_path = repo_root / "deploy" / "install_vps.bat"
    assert bat_path.exists()
    bat_content = bat_path.read_text(encoding="utf-8")
    assert "install_vps.ps1" in bat_content


def test_start_monika_linux_launcher(repo_root):
    launcher_path = repo_root / "start_monika.sh"
    assert launcher_path.exists()

    content = launcher_path.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "monika.interfaces.cli.main setup" in content
    assert "doctor --fix" in content
    assert "monika-agent" in content
    assert "NON_INTERACTIVE" in content


def test_start_monika_windows_launcher(repo_root):
    launcher_path = repo_root / "start_monika.bat"
    assert launcher_path.exists()

    content = launcher_path.read_text(encoding="utf-8")
    assert "NON_INTERACTIVE" in content
    assert ":apply_tier" in content
    assert "doctor --fix" in content

"""
Tests for PR-23: VPS Deployment Guide + Docker Support.
Verifies docker-compose.vps.yml structure, Dockerfile.mt5-wine directives, and deployment documentation.
"""

import os
from pathlib import Path
import yaml
import pytest


@pytest.fixture
def repo_root():
    # Resolves to repo root (D:\Monika)
    return Path(__file__).resolve().parent.parent.parent.parent


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

    # DB service uses pgvector
    assert "pgvector" in services["db"]["image"]

    # Agent depends on DB health
    assert "depends_on" in services["agent"]
    assert "db" in services["agent"]["depends_on"]

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

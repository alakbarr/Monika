"""
File: cli/profile_manager.py
Multi-profile environment manager for Monika (MT5 Trading Agent).
Enables seamless isolation of trading accounts, prop firm rules, and paper/live environments.
"""

import os
import shutil
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("TradingAgent.CLI.Profile")


@dataclass
class ProfileInfo:
    name: str
    is_active: bool
    path: str
    has_settings: bool


class ProfileManager:
    """Manages profile creation, listing, switching, and directory isolation."""

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir:
            self.root_dir = root_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.root_dir = os.path.join(base_dir, "profiles")
        os.makedirs(self.root_dir, exist_ok=True)
        self.active_marker_file = os.path.join(self.root_dir, "active_profile")

    def get_active_profile_name(self) -> str:
        """Returns the currently active profile name ('default' if not set)."""
        if os.path.exists(self.active_marker_file):
            try:
                with open(self.active_marker_file, "r", encoding="utf-8") as f:
                    name = f.read().strip()
                    if name:
                        return name
            except Exception:
                pass
        return "default"

    def set_active_profile(self, name: str) -> bool:
        """Switches active profile to the given name."""
        clean_name = name.strip().lower()
        if clean_name != "default":
            profile_dir = os.path.join(self.root_dir, clean_name)
            if not os.path.exists(profile_dir):
                raise FileNotFoundError(f"Profile '{clean_name}' does not exist at {profile_dir}")

        with open(self.active_marker_file, "w", encoding="utf-8") as f:
            f.write(clean_name)
        logger.info(f"Switched active profile to: {clean_name}")
        return True

    def list_profiles(self) -> List[ProfileInfo]:
        """Lists all existing profiles."""
        active_name = self.get_active_profile_name()
        profiles = [
            ProfileInfo(
                name="default",
                is_active=(active_name == "default"),
                path="config/settings.yaml",
                has_settings=True,
            )
        ]

        if os.path.exists(self.root_dir):
            for item in sorted(os.listdir(self.root_dir)):
                p_path = os.path.join(self.root_dir, item)
                if os.path.isdir(p_path) and item != "__pycache__":
                    has_cfg = os.path.exists(os.path.join(p_path, "settings.yaml"))
                    profiles.append(
                        ProfileInfo(
                            name=item,
                            is_active=(active_name == item),
                            path=p_path,
                            has_settings=has_cfg,
                        )
                    )
        return profiles

    def create_profile(self, name: str, clone_from: Optional[str] = None) -> str:
        """Creates a new isolated profile directory."""
        clean_name = name.strip().lower()
        if clean_name == "default":
            raise ValueError("Profile name 'default' is reserved.")

        p_dir = os.path.join(self.root_dir, clean_name)
        if os.path.exists(p_dir):
            raise FileExistsError(f"Profile '{clean_name}' already exists.")

        os.makedirs(p_dir, exist_ok=True)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source_cfg = os.path.join(base_dir, "config", "settings.yaml")

        if clone_from and clone_from != "default":
            source_dir = os.path.join(self.root_dir, clone_from)
            clone_cfg = os.path.join(source_dir, "settings.yaml")
            if os.path.exists(clone_cfg):
                source_cfg = clone_cfg

        if os.path.exists(source_cfg):
            target_cfg = os.path.join(p_dir, "settings.yaml")
            shutil.copy2(source_cfg, target_cfg)

        logger.info(f"Created profile '{clean_name}' at {p_dir}")
        return p_dir

    def get_settings_path_for_active(self) -> Optional[str]:
        """Returns the settings.yaml path for the active profile (or None for default)."""
        active = self.get_active_profile_name()
        if active == "default":
            return None
        p_cfg = os.path.join(self.root_dir, active, "settings.yaml")
        if os.path.exists(p_cfg):
            return p_cfg
        return None

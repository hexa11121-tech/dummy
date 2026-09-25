"""App settings + recent files, stored as JSON under %APPDATA%/APKDeco on Windows."""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

APP_DIR_NAME = "APKDeco"


def config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_DIR_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


DEFAULTS: Dict[str, Any] = {
    "java_path": "",        # empty = auto-detect
    "jadx_path": "",        # jadx(.bat/.exe) or jadx folder
    "apktool_path": "",     # apktool.jar
    "output_dir": "",       # empty = <apk dir>/<apk name>_decoded
    "theme": "dark",        # dark | light
    "max_hex_bytes": 1048576,
    "recent": [],           # list of apk paths
    "geometry": "1280x800",
    "log_visible": True,
}


class Settings:
    def __init__(self) -> None:
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(settings_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data.update(data)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            with open(settings_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass

    # -- generic access ----------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def reset(self) -> None:
        self._data = dict(DEFAULTS)

    # -- recent files -------------------------------------------------------
    def add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        recent: List[str] = [p for p in self.get("recent", []) if p != path]
        recent.insert(0, path)
        self._data["recent"] = recent[:12]
        self.save()

    def clear_recent(self) -> None:
        self._data["recent"] = []
        self.save()

    def default_output_dir(self, apk_path: str) -> str:
        configured = self.get("output_dir") or ""
        if configured:
            return configured
        base = os.path.splitext(os.path.basename(apk_path))[0]
        return os.path.join(os.path.dirname(os.path.abspath(apk_path)), base + "_decoded")

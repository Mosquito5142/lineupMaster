"""โหลด config.yaml / aliases.yaml และ resolve path ต่างๆ."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import ROOT


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


DEFAULTS: dict[str, Any] = {
    "lineups_dir": "lineups",
    "hotkeys": {
        "next_map": "numpad+",
        "prev_map": "numpad-",
        "toggle_side": "numpad0",
        "site_a": "numpad1",
        "site_b": "numpad2",
        "site_c": "numpad3",
        "prev_image": "numpad4",
        "zoom": "numpad5",
        "next_image": "numpad6",
        "show_all": "numpad.",
        "toggle_gif": "numpad*",
        "toggle_map": "numpad/",
        # ผูกไว้เฉยๆ เพื่อให้ hook ส่งปุ่ม 7/8/9 มาถึง — ใช้จริงเฉพาะเลือกหมุดบนแผนที่
        "pin_7": "numpad7",
        "pin_8": "numpad8",
        "pin_9": "numpad9",
    },
    "display": {
        "monitor": 1,
        "fullscreen": False,
        "always_on_top": True,
        "max_images": 0,
        "show_status": True,
        "show_labels": True,
        "equal_size": True,
    },
    "gif": {
        "max_seconds": 3.0,
    },
}


@dataclass
class Config:
    raw: dict[str, Any]
    aliases: dict[str, Any]
    root: Path = ROOT

    @property
    def lineups_dir(self) -> Path:
        return (self.root / self.raw["lineups_dir"]).resolve()

    @property
    def hotkeys(self) -> dict[str, str]:
        return self.raw["hotkeys"]

    @property
    def display(self) -> dict[str, Any]:
        return self.raw["display"]

    @property
    def gif(self) -> dict[str, Any]:
        return self.raw["gif"]



def load(root: Path = ROOT) -> Config:
    cfg_path = root / "config.yaml"
    alias_path = root / "aliases.yaml"

    raw = dict(DEFAULTS)
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        raw = _deep_merge(raw, loaded)

    aliases: dict[str, Any] = {}
    if alias_path.exists():
        aliases = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}

    return Config(raw=raw, aliases=aliases, root=root)

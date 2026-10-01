"""โหลด config.yaml / aliases.yaml และ resolve path ต่างๆ."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import settings as settings_mod
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
        # วางรูปชื่อโซนจากคลิปบอร์ดให้อ่าน (OCR) — อยู่นอก numpad เพราะ numpad เต็มแล้ว
        # (บนหน้าแผนที่ เลข 1-9 ถูกใช้เลือกหมุดหมด ไม่เหลือปุ่มว่างที่ใช้ได้ทั้งสองโหมด)
        "locate": "insert",
        # บล็อก 6 ปุ่มเหนือลูกศร = ตัวกรอง (numpad เต็มแล้ว) — อยู่ติดกับ numpad มือเดียวกดถึง
        "filter_agent": "delete",       # สลับตัวละคร
        "filter_ability": "home",       # สลับสกิล
        "filter_fav": "end",            # เฉพาะไม้ตาย
        "filter_tag": "page up",        # สลับแท็กสถานการณ์ (แก้ทาง/post-plant)
        "drill": "page down",           # โหมดซ้อม: สุ่มใบถัดไป
        # เปิด/ปิด "โหมดตามตัว" — อ่านชื่อโซนจากจอเกมเองเรื่อยๆ แทนการกด Insert ทีละครั้ง
        # ใช้ F9 เพราะ numpad กับบล็อก 6 ปุ่มเหนือลูกศรเต็มหมดแล้ว และ VALORANT ไม่ได้ผูก F9 ไว้
        "auto_locate": "f9",
        # เปิด/ปิด "โหมดซูมตามตัว" — เหมือน F9 แต่ไม่ต้องกดอะไรเลย: เข้าโซนไหนซูมใบที่เข้ากับ
        # สถานการณ์ที่สุดให้เอง (เดาจากเส้นทางที่เดิน ดู intent.py) + มินิแมพมุมจอ
        "auto_zoom": "f10",
        # ⚑ แจ้งผิดใบที่เลือก/ซูมอยู่ (กดซ้ำ = เอาธงออก) — ติดกับ F9 · ไปแก้ในเว็บ ⚑ ต้องแก้
        "flag": "f8",
        # ✓ ใช้ได้จริง — โหวตให้ใบที่เอามาจากคอมมูนิตี้ (กดซ้ำ = ถอน) ส่งขึ้นเซิร์ฟเวอร์ตอนเปิดหน้าเว็บ
        "vote_works": "f7",
    },
    "display": {
        "monitor": 1,
        "fullscreen": False,
        "always_on_top": True,
        "max_images": 0,
        "show_status": True,
        "show_labels": True,
        "equal_size": True,
        "start_on_map": True,
    },
    "gif": {
        "max_seconds": 3.0,
    },
    # โหมดตามตัว (ดู app.py::_auto_tick) — ปิดไว้เป็นค่าเริ่มต้น กด F9 ถึงจะเริ่มทำงาน
    "auto": {
        "start_on": False,      # เปิดโปรแกรมมาแล้วเริ่มตามตัวเลยไหม
        "interval_ms": 1000,    # อ่านจอทุกกี่มิลลิวินาที (วัดจริง: แคป ~5 ms + OCR ~17 ms ต่อรอบ)
        "confirm": 2,           # ต้องอ่านได้ชื่อเดิมติดกันกี่ครั้งถึงจะเชื่อ (กัน OCR เพี้ยนครั้งเดียว)
        "blank_limit": 5,       # แคปได้ภาพว่างติดกันกี่ครั้งถึงจะยอมแพ้แล้วปิดโหมดให้เอง
        "resume_on_move": True, # เลือกหมุด/ซูมค้างไว้แล้วเดินออกจากโซนนั้น = ตามต่อให้เอง
        "resume_confirm": 3,    # ...โดยต้องอ่านโซนใหม่ได้ติดกันกี่ครั้ง (ขอมากกว่า confirm)
    },
    # เกณฑ์เทียบชื่อโซนที่ OCR อ่านได้ (ดู callouts._accept) — เดิมเป็นค่าคงที่ในโค้ด ย้ายมาให้ปรับได้
    # จากหน้าตั้งค่า ค่าเริ่มต้นเท่าเดิมเป๊ะ
    "match": {
        "cutoff": 0.6,          # ต้องคล้ายอย่างน้อยเท่านี้ถึงจะยอมรับ (callouts.MATCH_CUTOFF)
        "margin": 0.05,         # อันดับ 1 ต้องนำอันดับ 2 เท่านี้ (callouts.MATCH_MARGIN)
    },
    # หน้าแผนที่ของโปรแกรมหลัก (ดู Browser._near_first / _ring_radius / app._render)
    "map": {
        "near_first": True,     # รู้ว่ายืนไหน = เรียงเลขหมุดจากใกล้ไปไกล
        "dim_others": True,     # หมุดนอกหน้าปัจจุบันวาดเป็นจุดจางๆ
        "face_side": True,      # หมุนแผนที่ให้จุดเกิดฝั่งเราอยู่ล่าง (callouts.facing_turn)
        "ring_group": 2.0,      # วงโซนนับหมุดไกลได้กี่เท่าของหมุดที่ใกล้ที่สุด (browser.ZONE_RING_GROUP)
    },
    # เสียงพูด (ดู voice.py) — ค่าเริ่มต้นตรงกับ voice.DEFAULTS
    "voice": {
        "enabled": True,        # พูดไหม
        "rate": -15,            # ความเร็ว % (ลบ = ช้าลง) · เปลี่ยนแล้วต้องสร้างเสียงใหม่
        "volume": 80,           # ความดัง 0-100
        "notes": True,          # อ่านวิธียิง (โน้ตของใบ) ต่อท้ายชื่อ
        "status": True,         # พูดสถานะ เช่น แมพ/ฝั่ง แจ้งผิด ข้อความเตือน
        "zone": True,           # เดินเข้าโซน (F9/Insert) แล้วบอกว่ายิงไปไหนได้บ้าง
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

    @property
    def auto(self) -> dict[str, Any]:
        return self.raw["auto"]



def load(root: Path = ROOT, with_settings: bool = True) -> Config:
    """``DEFAULTS`` ← ``config.yaml`` ← ``settings.json`` (ค่าที่ปรับจากหน้าตั้งค่า ดู settings.py).

    ``with_settings=False`` = ค่าที่จะได้ถ้าไม่ได้ปรับอะไรในหน้าตั้งค่า (หน้าเว็บใช้โชว์ "ค่าเริ่มต้น")
    """
    cfg_path = root / "config.yaml"
    alias_path = root / "aliases.yaml"

    raw = dict(DEFAULTS)
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        raw = _deep_merge(raw, loaded)
    if with_settings:
        raw = _deep_merge(raw, settings_mod.overrides(root))

    aliases: dict[str, Any] = {}
    if alias_path.exists():
        aliases = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}

    return Config(raw=raw, aliases=aliases, root=root)

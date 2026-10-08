"""หน้าจัดการคลังแบบเว็บ — เปิดในเบราว์เซอร์ แทนหน้าต่าง Qt เดิม.

    python tools/web_manage.py
    LineupMaster.exe web

**ไม่เกี่ยวกับโปรแกรมหลักเลย** (ตัวที่รันบนจอที่สอง + numpad) — ตัวนั้นยังเป็น Qt เหมือนเดิม
ทุกอย่าง ไม่ได้ถูกแตะต้อง ตัวนี้แทนที่เฉพาะ "หน้าจัดการ" ซึ่งนั่งทำหน้าคอมปกติ ไม่ได้ใช้ระหว่างเล่น

**ใช้ไฟล์ข้อมูลชุดเดียวกับตัวหลักเป๊ะ** — ทุกการแก้ไขวิ่งผ่าน ``lineupmaster.library`` /
``positions`` / ``meta`` ตัวเดียวกับที่หน้า Qt เดิมใช้ ของพ่วง (gif, โน้ต, หมุด, สถิติ, แท็ก)
จึงถูกลากตามไปครบเหมือนเดิมทุกประการ เปิดสองหน้าต่างพร้อมกันก็ยังอ่านของชุดเดียวกัน

ทำไมเป็นเว็บ: หน้าตาแก้ง่ายกว่ามาก (HTML/CSS ธรรมดา ไม่ต้องบิ้วใหม่) — ไฟล์หน้าเว็บอยู่ที่
``assets/web/`` **นอกตัว exe** แก้แล้วกด refresh เห็นผลทันที ไม่ต้องบิ้วโปรแกรมใหม่เลย

ไม่ใช้เฟรมเวิร์กเว็บใดๆ (ไม่มี Flask/FastAPI) — ใช้ ``http.server`` ที่มากับ Python อยู่แล้ว
เพราะงานนี้คือเสิร์ฟให้ตัวเองเครื่องเดียว ไม่ต้องรับโหลด ไม่ต้องมี dependency เพิ่มให้บิ้วยาก
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import curate as curate_mod  # noqa: E402
from lineupmaster import index as index_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import merge as merge_mod  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster import settings as settings_mod  # noqa: E402
from lineupmaster import shrink as shrink_mod  # noqa: E402
from lineupmaster import voice as voice_mod  # noqa: E402
from lineupmaster import clipgrab  # noqa: E402
from lineupmaster.browser import ABILITY_TH, AGENT_ABILITIES, AGENT_TH, SIDES, SITES  # noqa: E402
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402
from lineupmaster import paths as paths_mod  # noqa: E402
from lineupmaster.paths import ASSETS, MAPS, ROOT  # noqa: E402
# ตัวโหลดไลน์อัพจากเว็บอยู่ที่ lineup_sources.py — ใช้ร่วมกับเครื่องมือ Qt เดิม สูตร URL,
# การจับคู่ชื่อสกิล และไฟล์จำว่าเอา/ไม่เอาใบไหน จึงเป็นชุดเดียวกันทั้งสองหน้า ไม่ต้องดูแลสองที่
import lineup_sources as source_mod  # noqa: E402
from community_web import CommunityWeb  # noqa: E402
from lineupmaster.community import CommunityError, NotLoggedIn  # noqa: E402
import route_pins  # noqa: E402

# Windows ไม่รู้จักนามสกุลฟอนต์เว็บ ต้องบอกเอง ไม่งั้นเสิร์ฟเป็น octet-stream
mimetypes.add_type("font/woff2", ".woff2")

WEB_DIR = ASSETS / "web"


def _voice_cache() -> Path:
    """ไฟล์เสียงพูด (voice.py) — ที่เดียวกับที่โปรแกรมหลักเปิดเล่น."""
    return ROOT / ".cache" / "voice"
THUMBS = ROOT / ".cache" / "thumbs"
SRC_THUMBS = ROOT / ".cache" / "source-thumbs"
THUMB_WIDTH = 420
SRC_THUMB_WIDTH = 360

HOST = "127.0.0.1"          # เปิดให้เฉพาะเครื่องตัวเอง ไม่รับจากเครื่องอื่นในวง LAN เด็ดขาด
# Windows บางเครื่องไม่รู้จัก .webp ใน registry → mimetypes เดาไม่ออกแล้วตกไปเป็น image/png
# (รูปในคลังเป็น .webp หลังกด "ย่อขนาดรูปทั้งคลัง")
mimetypes.add_type("image/webp", ".webp")
PORT_RANGE = range(8760, 8800)

# tracker.gg (lineup_sources.py · "tg") โหลดจาก Python ตรงๆ ไม่ได้ (เว็บกันบอต 403) — bookmarklet ในเบราว์เซอร์
# ผู้ใช้ดึงรายการแล้วส่งมาที่ /api/tracker/push · ตอบ CORS เฉพาะสองเว็บนี้ และต้องมีรหัสลับถาวรของ bookmarklet
TRACKER_ORIGINS = ("https://tracker.gg", "https://www.tracker.gg")
TRACKER_MAX_BODY = 64 * 1024 * 1024         # ตัวละครที่มีไลน์อัพเยอะสุด (900+ ใบ) ก็แค่ไม่กี่ MB


def tracker_bookmarklet() -> str:
    """ลิงก์ ``javascript:`` ของ bookmarklet "ส่งเข้า LineupMaster" — ฝังรหัสลับ + ช่วงพอร์ตที่เซิร์ฟเวอร์อาจอยู่."""
    code = (WEB_DIR / "bookmarklet.js").read_text(encoding="utf-8")
    code = (code.replace("__KEY__", source_mod.tg_key())
                .replace("__PORT_FIRST__", str(PORT_RANGE.start))
                .replace("__PORT_LAST__", str(PORT_RANGE.stop - 1)))
    return "javascript:" + quote(code, safe="")


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


class Store:
    """ข้อมูลทั้งหมดที่หน้าเว็บต้องใช้ + คำสั่งแก้ไข — ล็อกทุกครั้งที่แตะ.

    อ่านใหม่จากดิสก์ทุกครั้งที่แก้เสร็จ (``reload``) เพราะหน้าจัดการ Qt เดิมหรือโปรแกรมหลัก
    อาจเปิดค้างอยู่พร้อมกันแล้วเขียนไฟล์เดียวกัน — ยึดไฟล์บนดิสก์เป็นความจริงเสมอ
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cfg = config_mod.load(ROOT)
        self.lineups: list = []
        self.positions: dict = {}
        self.meta: dict = {}
        self.merge_plan: dict | None = None   # แผนรวมคลังล่าสุดที่ผู้ใช้กำลังดูสรุปอยู่
        self.reload()

    def reload(self) -> None:
        self.positions = pos_mod.load(ROOT / "positions.json")
        self.lineups = index_mod.scan(self.cfg.lineups_dir, self.cfg.aliases)
        self.fresh_meta()

    def fresh_meta(self) -> dict:
        """อ่าน meta.json สดจากดิสก์ก่อนแก้ทุกครั้ง (อ่าน→แก้→เขียน).

        โปรแกรมหลักเขียนไฟล์นี้เองระหว่างเล่น (F8 แจ้งผิด, นับซ้อม) และ library.move/rename ก็
        ย้ายคีย์บนดิสก์ตรงๆ — ถ้าเขียนจากก๊อปในหน่วยความจำที่อ่านไว้นานแล้ว ธงที่เพิ่งกดจะหาย
        หรือคีย์ชื่อเก่าที่เพิ่งย้ายไปจะโผล่กลับมา
        """
        self.meta = meta_mod.load(ROOT / "meta.json")
        self._meta_stamp = _mtime(ROOT / "meta.json")
        meta_mod.apply(self.meta, self.lineups)
        return self.meta

    def find(self, rel: str):
        return next((lu for lu in self.lineups if lu.rel == rel), None)

    # -- แปลงเป็น JSON ให้หน้าเว็บ ----------------------------------------
    def as_json(self, lu) -> dict:
        entry = self.positions.get(lu.rel) or {}
        return {
            "rel": lu.rel,
            "stem": lu.stem,
            "map": lu.map,
            "side": lu.side,
            "site": lu.site,
            "agent": lu.agent or "sova",
            "ability": lu.ability,
            "fav": bool(lu.fav),
            "tags": list(lu.tags),
            "drilled": int(lu.drilled),
            "flag": bool(lu.flag),
            "hasOriginal": lib.original_of(ROOT, lu.rel).is_file(),
            # เลขเวอร์ชันของไฟล์รูป — ต่อท้าย URL รูปให้เบราว์เซอร์โหลดใหม่หลังวาดทับ (รูปแคชไว้ 1 วัน)
            "v": int(_mtime(lu.path) or 0),
            "note": lu.note or "",
            "howto": lu.howto or "",
            "howtoAi": bool(lu.howto_ai),
            "gif": lu.gif is not None,
            "animated": bool(lu.animated),
            "pin": {
                "from": pos_mod.point_of(entry, "from"),
                "to": pos_mod.point_of(entry, "to"),
            } if entry else None,
        }

    def state(self) -> dict:
        # สแกนดิสก์ใหม่ทุกครั้ง: รูปที่ลากวางเข้าโฟลเดอร์คลังตรงๆ ต้องขึ้น "ยังไม่ปักหมุด" ทันที
        # และธงที่เพิ่งกด F8 ในเกมต้องเห็นหลังรีเฟรช (คลังหลายร้อยใบใช้ ~0.2 วินาที)
        self.reload()
        maps = sorted(self.cfg.aliases.get("maps") or {})
        agents = sorted(self.cfg.aliases.get("agents") or {}) or ["sova"]
        items = [self.as_json(lu) for lu in self.lineups]
        return {
            "lineups": items,
            "maps": maps,
            "agents": [{"id": a, "th": AGENT_TH.get(a, a)} for a in agents],
            "sides": [{"id": s, "th": "บุก" if s == "attack" else "ตั้งรับ"} for s in SIDES],
            "sites": list(SITES),
            "abilities": [{"id": a, "th": th} for a, th in ABILITY_TH.items()],
            "agentAbilities": AGENT_ABILITIES,
            "tags": sorted({t for lu in self.lineups for t in lu.tags}),
            "mapsWithImage": sorted(p.stem for p in MAPS.glob("*.png")),
            # "ยังไม่ปักหมุด" รวมใบที่ยังไม่ได้ตั้งสกิลด้วย — ต้องกลับไปเติมให้ครบเหมือนกัน
            "unpinned": sum(1 for lu in self.lineups if lu.rel not in self.positions or not lu.ability),
        }

    def map_extras(self, map_: str, side: str | None) -> dict:
        """ป้ายจุด A/B/C + ชื่อโซนอ้างอิงของแมพนี้ — ของประกอบตอนจิ้มหมุด."""
        group = [lu for lu in self.lineups if lu.map == map_ and (not side or lu.side == side)]
        labels = pos_mod.site_labels(map_, group, self.positions)
        data = callout_mod.load(ROOT / "callouts.json")
        # จุดเกิดสองฝั่ง — หน้าเว็บใช้หมุนแมพให้จุดเกิดฝั่งเราอยู่ล่างจอ (เหมือนมินิแมพในเกม)
        entries = data.get(map_, {})
        spawns = {side: list(entries[slug]["xy"])
                  for side, slug in (("attack", "spawn-attacker-side"),
                                     ("defense", "spawn-defender-side"))
                  if entries.get(slug, {}).get("xy") is not None}
        return {
            "spawns": spawns,
            "labels": {site: {"xy": list(xy), "manual": manual}
                       for site, (xy, manual) in labels.items()},
            "callouts": [{"label": label, "xy": list(xy)}
                         for label, xy in callout_mod.placed(data, map_)],
        }

    # -- คำสั่งแก้ไข (ทุกตัวต้องถูกเรียกใต้ self.lock) ----------------------
    def save_edits(self, body: dict) -> dict:
        """แก้ชื่อ/ที่อยู่/โน้ต/แท็ก — ลำดับเดียวกับหน้า Qt เดิมเป๊ะ (rename ก่อน แล้วค่อย move)."""
        lu = self.find(body["rel"])
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้ (อาจถูกลบ/ย้ายไปแล้ว — กด refresh)")
        name = lib.clean_stem(str(body.get("name") or "").strip())
        if not name:
            raise ValueError("ชื่อว่างไม่ได้ — ชื่อคือชื่อไฟล์จริงบนดิสก์")

        path = lu.path
        changes: list[str] = []
        if name != lu.stem:
            path = lib.rename(ROOT, self.cfg.lineups_dir, path, name).path
            changes.append(f"เปลี่ยนชื่อเป็น {path.stem}")

        target = (body.get("map") or lu.map, body.get("side") or lu.side,
                  body.get("site") or lu.site)
        agent = body.get("agent") or lu.agent or "sova"
        if target != (lu.map, lu.side, lu.site) or agent != (lu.agent or "sova"):
            result = lib.move(ROOT, self.cfg.lineups_dir, path, *target, agent=agent)
            path = result.path
            changes.append(result.message)

        note = str(body.get("note") or "")
        if note != (lu.note or ""):
            note_path = path.with_suffix(".txt")
            if note:
                note_path.write_text(note, encoding="utf-8")
            elif note_path.is_file():
                note_path.unlink()
            changes.append("แก้โน้ต")

        rel = lib.rel_of(self.cfg.lineups_dir, path)
        self.fresh_meta()
        before = dict(meta_mod.entry(self.meta, rel))
        fields = {"ability": body.get("ability") or None, "fav": bool(body.get("fav")),
                  "tags": body.get("tags") or []}
        if "flag" in body:                  # ฟอร์มเก่าที่ไม่ส่ง flag มา = ไม่แตะธง
            fields["flag"] = bool(body["flag"])
        if "howto" in body:                 # วิธียิงที่เสียงอ่าน — แก้เอง/กดยืนยัน = ไม่ใช่ร่าง AI แล้ว
            howto = str(body.get("howto") or "").strip()
            fields["howto"] = howto
            fields["howto_ai"] = bool(howto) and bool(body.get("howtoAi"))
        meta_mod.set_fields(self.meta, rel, **fields)
        if meta_mod.entry(self.meta, rel) != before:
            meta_mod.save(ROOT / "meta.json", self.meta)
            if bool(before.get("flag")) != bool(meta_mod.entry(self.meta, rel).get("flag")):
                changes.append("⚑ ต้องแก้" if fields.get("flag") else "เอาธง ⚑ ออก")
            if {k: v for k, v in before.items() if k != "flag"} !=                     {k: v for k, v in meta_mod.entry(self.meta, rel).items() if k != "flag"}:
                changes.append("แก้สกิล/ไม้ตาย/แท็ก")

        self.reload()
        return {"rel": rel, "changes": changes or ["ไม่มีอะไรเปลี่ยน"]}

    def save_drawing(self, rel: str, data_url: str) -> dict:
        """เขียนรูปที่วาดทับจากหน้าเว็บลงไฟล์จริง — สำรองต้นฉบับไว้ที่ ``.originals/<rel>`` ครั้งแรกครั้งเดียว.

        วาดซ้ำหลายรอบต้นฉบับยังเป็นรูปก่อนวาดครั้งแรกสุด (กด "กลับเป็นรูปเดิม" ได้เสมอ)
        rel ไม่เปลี่ยน หมุด/แท็กอยู่ครบ · jpg/webp ยังเป็นนามสกุลเดิม (ไม่งั้นต้องเปลี่ยนนามสกุล = เปลี่ยน rel)
        """
        from PySide6.QtGui import QImage

        lu = self.find(rel)
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้ (อาจถูกลบ/ย้ายไปแล้ว — กด refresh)")
        suffix = lu.path.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".webp") or lu.animated:
            raise ValueError("วาดทับได้เฉพาะรูปนิ่ง (ภาพเคลื่อนไหววาดทับไม่ได้)")
        head, _, payload = str(data_url or "").partition(",")
        if not head.startswith("data:image/png;base64"):
            raise ValueError("ข้อมูลรูปที่ส่งมาไม่ใช่ PNG")
        raw = base64.b64decode(payload)
        image = QImage()
        if not image.loadFromData(raw, "PNG"):
            raise ValueError("อ่านรูปที่วาดไม่ออก")

        original = lib.original_of(ROOT, rel)
        if not original.is_file():
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lu.path, original)
        temp = lu.path.with_name(lu.path.name + ".drawing.tmp")
        if suffix == ".png":
            temp.write_bytes(raw)
        elif suffix == ".webp":
            if not image.save(str(temp), "WEBP", shrink_mod.QUALITY):
                raise OSError("เซฟรูป webp ไม่สำเร็จ")
        elif not image.save(str(temp), "JPG", 95):
            raise OSError("เซฟรูป jpg ไม่สำเร็จ")
        os.replace(temp, lu.path)             # ไม่มีจังหวะที่ไฟล์หายหรือครึ่งๆ กลางๆ
        self.reload()
        return {"rel": rel, "message": "บันทึกที่วาดลงรูปแล้ว (รูปเดิมสำรองไว้ กด 'กลับเป็นรูปเดิม' ได้)"}

    def revert_drawing(self, rel: str) -> dict:
        """เอารูปก่อนวาดกลับมา — รูปที่วาดแล้วย้ายเข้า ``.trash/<เวลา>-drawn/`` (ไม่ลบทิ้ง)."""
        lu = self.find(rel)
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้")
        original = lib.original_of(ROOT, rel)
        if not original.is_file():
            raise ValueError("ใบนี้ไม่มีรูปเดิมสำรองไว้ (ยังไม่เคยวาดทับ)")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bin_path = ROOT / ".trash" / f"{stamp}-drawn" / Path(*rel.split("/"))
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(lu.path), bin_path)
        shutil.move(str(original), lu.path)
        self.reload()
        return {"rel": rel, "message": "กลับเป็นรูปเดิมแล้ว (รูปที่วาดไว้อยู่ใน .trash)"}

    def delete(self, rel: str) -> dict:
        lu = self.find(rel)
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้")
        extras = [p.name for p in lib.sidecars(lu.path)]
        result = lib.remove(ROOT, self.cfg.lineups_dir, lu.path)
        self.reload()
        return {"message": result.message, "extras": extras}

    # -- ย่อขนาดรูปทั้งคลัง (ดู lineupmaster/shrink.py) ------------------------
    def shrink_candidates(self) -> dict:
        """รูปที่ยังย่อได้ + ขนาดรวมตอนนี้ — หน้าเว็บวนส่งทีละ rel มาที่ shrink()."""
        lineups_dir = self.cfg.lineups_dir
        paths = [p for p in shrink_mod.candidates(lineups_dir)
                 if self.find(lib.rel_of(lineups_dir, p)) is not None]
        return {"rels": [lib.rel_of(lineups_dir, p) for p in paths],
                "bytes": sum(p.stat().st_size for p in paths)}

    def shrink(self, rel: str) -> dict:
        """ย่อทีละใบ — ทีละใบเพื่อให้หน้าเว็บโชว์ความคืบหน้าและกดหยุดกลางทางได้."""
        lu = self.find(rel)
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้ (อาจถูกลบ/ย้ายไปแล้ว)")
        done = shrink_mod.shrink_one(ROOT, self.cfg.lineups_dir, lu.path)
        if not done.skipped:
            self.reload()
        return {"rel": lib.rel_of(self.cfg.lineups_dir, done.path), "skipped": done.skipped,
                "oldBytes": done.old_bytes, "newBytes": done.new_bytes}

    # -- เสียงพูด (ดู lineupmaster/voice.py) ------------------------------------
    def voice_options(self) -> dict:
        """ค่าเสียงที่ใช้อยู่จริง (อ่าน config สด — เพิ่งปรับความเร็วในหน้าตั้งค่าต้องเห็นเลย)."""
        return {**voice_mod.DEFAULTS, **(config_mod.load(ROOT).raw.get("voice") or {})}

    def voice_candidates(self) -> dict:
        """ประโยคที่ยังไม่มีไฟล์เสียง — หน้าเว็บวนส่งทีละประโยคไปที่ /api/voice/make."""
        options = self.voice_options()
        rate = int(options["rate"])
        texts = voice_mod.phrases(self.lineups, ABILITY_TH, bool(options["notes"]))
        # ลบเสียงของใบที่ลบ/เปลี่ยนชื่อไปแล้ว และของความเร็วเก่า — ทุกครั้งที่เปิดหน้าตั้งค่า
        pruned, freed = voice_mod.prune(_voice_cache(), rate, texts)
        missing = [text for text in texts
                   if not voice_mod.clip_path(_voice_cache(), text, rate).is_file()]
        return {"total": len(texts), "missing": missing, "pruned": pruned, "freed": freed}

    def set_pin(self, rel: str, src, dst) -> dict:
        if self.find(rel) is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้")
        entry: dict = {"from": [round(float(src[0]), 4), round(float(src[1]), 4)]}
        if dst is not None:
            entry["to"] = [round(float(dst[0]), 4), round(float(dst[1]), 4)]
        self.positions[rel] = entry
        if not pos_mod.save(ROOT / "positions.json", self.positions):
            raise OSError("เซฟ positions.json ไม่สำเร็จ")
        self.reload()
        return {"pin": entry}

    def clear_pin(self, rel: str) -> dict:
        if self.positions.pop(rel, None) is None:
            raise KeyError("ใบนี้ยังไม่มีหมุดให้ลบ")
        if not pos_mod.save(ROOT / "positions.json", self.positions):
            raise OSError("เซฟ positions.json ไม่สำเร็จ")
        self.reload()
        return {"ok": True}

    def set_site_label(self, map_: str, site: str, point) -> dict:
        key = pos_mod.site_label_key(map_, site)
        if point is None:
            self.positions.pop(key, None)
        else:
            self.positions[key] = {"from": [round(float(point[0]), 4), round(float(point[1]), 4)]}
        if not pos_mod.save(ROOT / "positions.json", self.positions):
            raise OSError("เซฟ positions.json ไม่สำเร็จ")
        self.reload()
        return {"ok": True}

    def add_image(self, body: dict) -> dict:
        """เพิ่มรูปเข้าคลัง — รับรูปเป็น base64 จากหน้าเว็บ (อัปโหลด/ลากมาวาง/วางจากคลิปบอร์ด)."""
        raw = base64.b64decode(str(body.get("data") or "").split(",")[-1])
        if not raw:
            raise ValueError("ไม่มีข้อมูลรูป")
        suffix = str(body.get("suffix") or ".png").lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".png"
        temp = ROOT / ".cache" / f"upload{suffix}"
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(raw)
        result = lib.add(
            self.cfg.lineups_dir, temp, body["map"], body["side"], body["site"],
            str(body.get("name") or "ไม่มีชื่อ"), body.get("agent") or "sova", move_file=True,
        )
        self.reload()
        return {"rel": lib.rel_of(self.cfg.lineups_dir, result.path),
                "message": result.message}

    def bulk(self, body: dict) -> dict:
        """สั่งเหมาหลายใบพร้อมกัน — ทำทีละใบผ่านทางเดิม ไม่มีทางลัดที่ข้ามของพ่วง."""
        rels = list(body.get("rels") or [])
        done = 0
        for rel in rels:
            lu = self.find(rel)
            if lu is None:
                continue
            path = lu.path
            target = (body.get("map") or lu.map, body.get("side") or lu.side,
                      body.get("site") or lu.site)
            agent = body.get("agent") or lu.agent or "sova"
            if target != (lu.map, lu.side, lu.site) or agent != (lu.agent or "sova"):
                path = lib.move(ROOT, self.cfg.lineups_dir, path, *target, agent=agent).path
            new_rel = lib.rel_of(self.cfg.lineups_dir, path)

            fields = {}
            if "ability" in body:
                fields["ability"] = body["ability"] or None
            if "fav" in body:
                fields["fav"] = bool(body["fav"])
            if "tags" in body:
                fields["tags"] = body["tags"] or []
            if fields:
                # อ่านสดทุกใบ — lib.move ข้างบนเพิ่งย้ายคีย์ใน meta.json บนดิสก์ไปแล้ว
                meta_mod.set_fields(self.fresh_meta(), new_rel, **fields)
                meta_mod.save(ROOT / "meta.json", self.meta)
            done += 1
        self.reload()
        return {"done": done}

    # -- รวมคลังจากโฟลเดอร์อื่น (ตัวรวมจริงอยู่ที่ lineupmaster/merge.py) -------------
    def merge_candidates(self, roots: list[Path] | None = None) -> dict:
        """โฟลเดอร์คลังอื่นในเครื่องที่น่าจะอยากรวม — แถวโฟลเดอร์แม่ของโปรแกรม, Desktop, Downloads.

        ``roots`` ไว้ให้เทสต์ส่งโฟลเดอร์จำลองเอง (ไม่ไปสแกนโฟลเดอร์จริงของเครื่อง)
        """
        if roots is None:
            home = Path.home()
            roots = [paths_mod.APP.parent, home / "Desktop", home / "Downloads", home / "Documents",
                     home / "OneDrive" / "Desktop"]
        return {"folders": merge_mod.find_candidates(roots, exclude=ROOT)}

    def merge_image(self, side: str, conflict_id: int) -> Path | None:
        """ไฟล์รูปของรายการ "รูปขัดกัน" ในแผนที่ดูสรุปอยู่ ไว้โชว์รูปย่อให้เทียบ — อ่านอย่างเดียว.

        path มาจากแผนที่เซิร์ฟเวอร์สร้างเองเท่านั้น (คีย์ของรายการนั้นใต้โฟลเดอร์รูปของฝั่งที่ขอ)
        ไม่รับ path จากหน้าเว็บเด็ดขาด · ไม่มีแผน/ไม่เจอ id/ไม่ใช่รายการรูป = None
        """
        plan = self.merge_plan
        if plan is None or side not in ("here", "there"):
            return None
        item = next((c for c in plan["conflicts"] if c["id"] == conflict_id), None)
        if item is None or item["kind"] != "image":
            return None
        path = merge_mod.lineups_dir(Path(plan[side])) / item["key"]
        return path if path.is_file() else None

    def merge_preview(self, path: str | None) -> dict:
        """ดูว่าจะรวมอะไรบ้าง (อ่านอย่างเดียว) แล้วจำแผนไว้ให้ ``merge_apply`` ใช้.

        รับ path แบบที่ Explorer ก๊อปให้ได้เลย ("Copy as path" มีเครื่องหมายคำพูดครอบมาด้วย)
        """
        raw = str(path or "").strip().strip('"').strip()
        if not raw:
            raise ValueError("ยังไม่ได้เลือกโฟลเดอร์")
        folder = Path(raw)
        if not folder.is_dir():
            raise ValueError(f"ไม่เจอโฟลเดอร์นี้: {raw}")
        self.merge_plan = merge_mod.plan(ROOT, folder)
        return self.merge_plan

    # -- คัดใบซ้ำ (lineupmaster/curate.py) — ของที่โหลดจากเว็บมาทั้งกอง ให้เหลือไม่กี่ใบต่อเป้า --------
    def _curate_file(self, agent: str) -> Path:
        safe = "".join(ch for ch in agent.lower() if ch.isalnum()) or "none"
        return ROOT / ".cache" / f"curate-{safe}.json"

    def curate_decisions(self, agent: str) -> dict:
        try:
            data = json.loads(self._curate_file(agent).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _curate_entries(self, agent: str, catalog: list[dict]) -> list[dict]:
        """ใบของตัวละครนี้ที่มาจากหน้าหาไลน์อัพ — จับคู่กับแคตตาล็อกผ่าน browse.json ("เอามาแล้ว")."""
        lineups = [{"rel": lu.rel, "map": lu.map, "side": lu.side, "agent": lu.agent or "sova",
                    "fav": bool(lu.fav), "stem": lu.stem} for lu in self.lineups]
        try:
            uses = json.loads((ROOT / "last-view.json").read_text(encoding="utf-8")).get("uses") or {}
        except (OSError, ValueError, AttributeError):
            uses = {}
        return curate_mod.build_entries(
            agent, lineups, source_mod.read_decisions(ROOT / "browse.json")["taken"],
            {e["uid"]: e for e in catalog},
            self.positions, uses, source_mod.ability_tag)

    def curate_agents(self, catalog: list[dict]) -> dict:
        agents = sorted({lu.agent or "sova" for lu in self.lineups})
        out = []
        for agent in agents:
            count = len(self._curate_entries(agent, catalog))
            if count:
                out.append({"agent": agent, "th": AGENT_TH.get(agent, agent), "count": count})
        return {"agents": out}

    def curate_state(self, catalog: list[dict], agent: str, keep: int, singles: bool) -> dict:
        entries = self._curate_entries(agent, catalog)
        return {"groups": curate_mod.groups(entries, keep=keep, singles=singles),
                "decisions": self.curate_decisions(agent), "total": len(entries),
                "abilities": ABILITY_TH}

    def curate_decide(self, agent: str, key: str, keep: list | None) -> dict:
        """จำว่ากลุ่มนี้เก็บใบไหน — ``keep=None`` = ลบการตัดสินทิ้ง (กลับไปเป็น "ยังไม่ตัดสิน")."""
        decisions = self.curate_decisions(agent)
        if keep is None:
            decisions.pop(key, None)
        else:
            decisions[key] = [str(rel) for rel in keep]
        path = self._curate_file(agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"decisions": decisions}

    def curate_apply(self, catalog: list[dict], agent: str) -> dict:
        """ทิ้งใบที่ไม่ได้เลือกในกลุ่มที่ตัดสินแล้ว (เข้า .trash ผ่าน library.remove = จดบันทึก/กู้ได้)
        แล้วเติมแท็กสกิลจากเว็บให้ใบที่เหลือของตัวละครนี้ที่ยังไม่มีแท็ก."""
        entries = self._curate_entries(agent, catalog)
        drop = set(curate_mod.drops(curate_mod.groups(entries, singles=True),
                                    self.curate_decisions(agent)))
        tagged = 0
        self.fresh_meta()
        for item in entries:
            lu = self.find(item["rel"])
            if item["rel"] in drop or lu is None or lu.ability or item["ability"] not in ABILITY_TH:
                continue
            meta_mod.set_fields(self.meta, item["rel"], ability=item["ability"])
            tagged += 1
        if tagged and not meta_mod.save(ROOT / "meta.json", self.meta):
            raise OSError("เซฟ meta.json ไม่สำเร็จ")
        removed, errors = 0, []
        for rel in sorted(drop):
            lu = self.find(rel)
            if lu is None:
                continue
            try:
                lib.remove(ROOT, self.cfg.lineups_dir, lu.path)
                removed += 1
            except OSError as error:
                errors.append(f"{rel}: {error}")
        self._curate_file(agent).unlink(missing_ok=True)
        self.reload()
        return {"removed": removed, "tagged": tagged, "errors": errors}

    # -- หน้าตั้งค่า (settings.json ทับ config.yaml — ดู lineupmaster/settings.py) --------
    def settings_state(self) -> dict:
        return settings_mod.state(ROOT)

    def settings_set(self, key: str | None, value) -> dict:
        settings_mod.set_value(ROOT, str(key or ""), value)
        self.cfg = config_mod.load(ROOT)
        return self.settings_state()

    def settings_reset(self, key: str | None) -> dict:
        settings_mod.reset(ROOT, str(key or ""))
        self.cfg = config_mod.load(ROOT)
        return self.settings_state()

    def settings_live(self) -> dict:
        """ผลรอบล่าสุดของโหมดตามตัวที่โปรแกรมหลักเขียนไว้ (app.App._auto_report) + อายุเป็นวินาที."""
        try:
            data = json.loads((ROOT / ".cache" / "auto-live.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"live": None, "age": None}
        if not isinstance(data, dict):
            return {"live": None, "age": None}
        return {"live": data, "age": round(time.time() - float(data.get("at") or 0), 1)}

    def merge_apply(self, choices: dict) -> dict:
        """รวมตามแผนที่ดูสรุปไว้ล่าสุด — ใช้ได้ครั้งเดียว (ล้มเพราะคลังเปลี่ยนก็ต้องดูสรุปใหม่)."""
        if self.merge_plan is None:
            raise ValueError("ยังไม่ได้ดูสรุป — เลือกโฟลเดอร์แล้วกดดูสรุปก่อน")
        plan, self.merge_plan = self.merge_plan, None
        report = merge_mod.apply(plan, choices)
        self.cfg = config_mod.load(ROOT)       # อาจเพิ่งก๊อป config.yaml/aliases.yaml ของโน่นมา
        self.reload()
        return {"report": report}


class SourceBrowser:
    """ฝั่ง "หาไลน์อัพจากเว็บ" — โหลดรายการ/รูปจากเว็บต้นทาง แล้วจำว่าเอา/ไม่เอาใบไหนไปแล้ว.

    แยกออกจาก ``Store`` เพราะคนละชุดข้อมูลกันคนละเรื่อง (อันนั้นคือคลังของเรา อันนี้คือของเว็บ
    ที่ยังไม่ได้เอาเข้า) — ใช้ ``lineup_sources`` เป็นตัวโหลดจริง จึงได้ไฟล์ ``browse.json``
    ชุดเดียวกับเครื่องมือ Qt เดิม กดข้ามในหน้าไหนอีกหน้าก็ไม่เอามาให้ดูซ้ำ

    รหัสไลน์อัพเป็น ``uid`` แบบ ``"<แหล่ง>:<เลข>"`` เพราะดึงจากหลายเว็บแล้วเลขชนกันได้
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._catalog: list[dict] = []
        # ล็อกแยกต่อไลน์อัพ — หน้าเว็บสั่งโหลดล่วงหน้าหลายใบพร้อมกัน ถ้าไม่กันไว้ใบเดียวกัน
        # จะถูกโหลดซ้ำซ้อนหลายเธรดพร้อมกัน (เปลืองทั้งเน็ตของเราและของเว็บเขา)
        self._busy: dict[str, threading.Lock] = {}
        self._callout_stamp: float = -1.0
        # ไลน์อัพจากคลิป YouTube (clipgrab.py) — ไม่ได้อยู่ในแคตตาล็อกของเว็บ เก็บแยกไว้ตรงนี้
        # uid "yt:<วิดีโอ>-<วินาทีเริ่ม>" · ใช้ท่อเดียวกับใบจากเว็บ: จัดหน้า → ปักหมุด → take()
        self._clips: dict[str, tuple[dict, clipgrab.Clip]] = {}

    def catalog(self, force: bool = False) -> list[dict]:
        with self.lock:
            if force or not self._catalog:
                self._catalog = source_mod.fetch_catalog(force=force)
                self._callout_stamp = -1.0
            self._mark_pins()
            return self._catalog

    def reset_catalog(self) -> None:
        """ทิ้งแคตตาล็อกในหน่วยความจำ — ครั้งหน้าที่ถามจะอ่านใหม่ (ใช้หลัง bookmarklet ส่งรายการเข้ามา)."""
        with self.lock:
            self._catalog = []

    def _mark_pins(self) -> None:
        """ติดป้ายให้ทุกใบว่าปักหมุดอัตโนมัติได้แค่ไหน — ตารางจะได้โชว์ก่อนกดเอา.

        คิดทีเดียวทั้งรายการแล้วเก็บไว้ (6,000+ ใบใช้เวลาไม่ถึงวินาที) และคิดใหม่เมื่อ
        ``callouts.json`` ถูกแก้ — ผู้ใช้อาจเพิ่งไปวางชื่อโซนเพิ่มในอีกหน้าต่างหนึ่ง
        """
        path = ROOT / "callouts.json"
        stamp = path.stat().st_mtime if path.is_file() else 0.0
        if stamp == self._callout_stamp:
            return
        data = callout_mod.load(path)
        index = {m: route_pins.index_of(data, m) for m in {e["m"] for e in self._catalog}}
        for entry in self._catalog:
            pin = {}
            start = end = None
            if entry.get("from") or entry.get("to"):
                lookup = index.get(entry["m"]) or []
                start = route_pins.match(entry.get("from"), lookup)
                end = route_pins.match(entry.get("to"), lookup)
                # ไม่มีจุดยืนก็เก็บหมุดไม่ได้เลย (positions.json ต้องมี from เสมอ)
                pin = {"from": start, "to": end} if start else {}
            entry["pin"] = route_pins.pin_state(pin)
            # พิกัดบนแผนที่ + แท็กสกิลของเรา — หน้า "หาไลน์อัพเพิ่ม" (coverage.js) วางใบจากเว็บลงโซนด้วยนี่
            entry["fxy"] = list(start) if start else None
            entry["txy"] = list(end) if end else None
            entry["tag"] = source_mod.ability_tag(entry.get("ab")) or ""
        self._callout_stamp = stamp

    def decisions(self) -> dict:
        return source_mod.read_decisions()

    def find(self, uid: str) -> dict | None:
        if uid in self._clips:
            return self._clips[uid][0]
        return next((l for l in self.catalog() if l["uid"] == uid), None)

    # -- คลิป YouTube ------------------------------------------------------
    def clip_load(self, link: str, aliases: dict) -> dict:
        """ลิงก์คลิป → รายการใบเสมือน (ไม่มีขั้นจนกว่าผู้ใช้จะเลือกเฟรม) + เฟรมทั้งหมดของท่านั้น."""
        clip = clipgrab.load(link, ROOT, aliases)
        entry = self._clip_entry(clip)
        return {"entry": entry, "times": clip.times, "subs": clip.subs}

    def _clip_entry(self, clip: clipgrab.Clip, video: bool = False) -> dict:
        """ใบเสมือนของคลิปนี้ (หน้าตาเหมือนใบจากเว็บ) แล้วจำไว้ใน ``_clips``."""
        uid = f"yt:{clip.vid}-{int(clip.start)}"
        text = f"{clip.chapter} {clip.title}"
        entry = {
            "uid": uid, "src": "yt", "i": uid, "t": clip.name, "m": clip.map or "",
            "a": clip.agent or "sova", "side": clip.side or "attack", "st": (clip.site or "").upper(),
            "ab": source_mod.ability_tag(text) or "", "n": 0, "from": None, "to": None,
            "d": f"{clip.title} · {int(clip.start) // 60}:{int(clip.start) % 60:02d}"
                 f"–{int(clip.end) // 60}:{int(clip.end) % 60:02d}",
            "video": video,
        }
        self._clips[uid] = (entry, clip)
        return entry

    # -- หน้าทำวิดีโอ --------------------------------------------------------
    def video_open(self, link: str, aliases: dict) -> dict:
        """ลิงก์คลิป → โหลดช่วงของท่านั้นมาไว้ในเครื่อง (proxy.mp4) + ข้อมูลที่หน้าทำวิดีโอต้องใช้."""
        clip = clipgrab.open_video(link, ROOT, aliases)
        return self._video_payload(self._clip_entry(clip, video=True), clip)

    @staticmethod
    def _video_payload(entry: dict, clip: clipgrab.Clip, howto: str = "") -> dict:
        return {
            "entry": entry, "start": clip.start, "end": clip.end,
            "offset": clip.proxy_offset, "fps": clip.fps, "max": clipgrab.GIF_MAX,
            "motion": {"times": clip.motion_times, "values": clip.motion},
            "plan": clipgrab.video_plan(clip),
            "suggest": clipgrab.suggest_plan(clip.coarse_times, clip.coarse, clip.start, clip.end),
            "subs": clip.subs, "howto": howto,
        }

    def video_open_entry(self, uid: str) -> dict:
        """ใบของเว็บที่มีสตรีมวิดีโอ (tracker.gg) → โหลดมาไว้ในเครื่อง แล้วเปิดในหน้าทำวิดีโอ.

        ใบยังเป็นใบเดิมในแคตตาล็อก (uid ``tg:…`` เดิม) — เก็บเข้าคลังแล้วจึงขึ้นว่า "เอาแล้ว" ถูกใบ
        คำอธิบายของเว็บใส่ช่อง "วิธียิง" ให้แก้ต่อได้ · พิกัด tracker.gg ยังไม่แปลงเป็นหมุด (จิ้มเอง)
        """
        entry = self.find(str(uid))
        if entry is None or entry.get("src") != "tg" or not entry.get("video"):
            raise KeyError("ไม่เจอใบนี้ หรือใบนี้ไม่มีวิดีโอ")
        with self._gate(entry["uid"]):
            key = "tg-" + re.sub(r"[^A-Za-z0-9_-]", "-", str(entry["i"]))[:56]
            clip = clipgrab.open_stream(
                source_mod.tg_stream_url(entry["video"]), ROOT, key, title=entry["t"],
                side=entry["side"], site=(entry["st"] or "").lower() or None,
                map_=entry["m"], agent=entry["a"])
        self._clips[entry["uid"]] = (entry, clip)
        return self._video_payload(entry, clip, howto=entry.get("desc") or "")

    def video_file(self, uid: str) -> Path | None:
        found = self._clips.get(uid)
        if found is None:
            return None
        path = clipgrab.proxy_path(found[1])
        return path if path.is_file() else None

    def video_render(self, uid: str, plan: dict) -> Path:
        """ทำภาพเคลื่อนไหวตามแผน แล้วจดแผนไว้ใน clip.json — ห้ามเรียกใต้ล็อก Store (ใช้หลายวินาที)."""
        found = self._clips.get(uid)
        if found is None:
            raise KeyError("ไม่เจอคลิปนี้ — วางลิงก์เปิดใหม่อีกครั้ง")
        clip = found[1]
        path = clipgrab.render(clip, plan)
        clip.plan = clipgrab.clean_plan(plan)
        clipgrab.save_clip(clip)
        return path

    def clip_gif(self, uid: str, start, end) -> Path:
        """GIF ช่วงยิงของใบคลิป (ทำครั้งเดียว เก็บในโฟลเดอร์คลิป) — ต่อเน็ต ห้ามเรียกใต้ล็อก Store."""
        found = self._clips.get(uid)
        if found is None:
            raise KeyError("ไม่เจอคลิปนี้ — กดดึงเฟรมใหม่อีกครั้ง")
        return clipgrab.make_gif(found[1], float(start), float(end))

    def clip_suggest(self, uid: str) -> dict:
        found = self._clips.get(uid)
        if found is None:
            raise KeyError("ไม่เจอคลิปนี้ — กดดึงเฟรมใหม่อีกครั้ง")
        guess = clipgrab.suggest_gif(found[1])
        return {"start": guess[0], "end": guess[1]} if guess else {}

    def clip_file(self, uid: str, name: str) -> Path | None:
        found = self._clips.get(uid)
        if found is None or not re.fullmatch(r"anim-[\d.]+-[\d.]+-\d+fps-q\d+\.webp", name):
            return None
        path = Path(found[1].folder) / name
        return path if path.is_file() else None

    def clip_frame(self, uid: str, index: int, small: bool) -> Path | None:
        found = self._clips.get(uid)
        if found is None or not (0 <= index < len(found[1].frames)):
            return None
        path = found[1].paths()[index]
        if not small:
            return path
        thumb = path.with_name(path.stem + ".s.jpg")        # รูปย่อไว้ในแถบเฟรม
        if not thumb.is_file() and not _shrink(path.read_bytes(), thumb, 320):
            return path
        return thumb

    def _entry(self, uid) -> dict:
        entry = self.find(str(uid))
        if entry is None:
            raise KeyError("ไม่เจอไลน์อัพรหัสนี้ในรายการ")
        return entry

    def _gate(self, uid: str) -> threading.Lock:
        with self.lock:
            return self._busy.setdefault(uid, threading.Lock())

    def prepare(self, uid) -> dict:
        """โหลดรูปทุกขั้นของไลน์อัพใบนี้มาพักไว้ (ถ้ายังไม่มี) — หน้าเว็บเรียกล่วงหน้าได้หลายใบ."""
        entry = self._entry(uid)
        with self._gate(entry["uid"]):
            if not source_mod.is_cached(entry):
                source_mod.download(entry)
        return {"uid": entry["uid"], "steps": entry["n"]}

    def step_file(self, uid, index: int) -> Path | None:
        entry = self.find(str(uid))
        if entry is None:
            return None
        paths = source_mod.step_paths(entry)
        if not (1 <= index <= len(paths)) or not paths[index - 1].is_file():
            return None
        return paths[index - 1]

    def thumb_file(self, uid) -> Path | None:
        """รูปย่อไว้โชว์ในตาราง — ทำครั้งเดียวแล้วเก็บไว้ใช้ซ้ำ.

        เว็บไหนมีรูปย่อสำเร็จรูปให้ (ValCompanion) ใช้ของเขาเลย **อย่าโหลดรูปเต็มมาย่อ**
        เพราะรูปเต็มของเขาใบละ ~2.5 MB เปิดตารางหน้าเดียวก็หลายสิบเมกแล้ว ส่วนเว็บที่ไม่มี
        (ValoLineups Pro) โหลดมาแค่ **ขั้นแรกขั้นเดียว** พอ ไม่ต้องโหลดครบทุกขั้น
        """
        entry = self._entry(uid)
        target = SRC_THUMBS / f"{entry['uid'].replace(':', '-')}.jpg"
        if target.is_file() and target.stat().st_size > 0:
            return target
        source = source_mod.SOURCES[entry["src"]]
        with self._gate(entry["uid"]):
            if target.is_file() and target.stat().st_size > 0:
                return target
            ready = source.thumb(entry)
            if ready:
                raw = source_mod._get(ready)
            else:
                urls = source.steps(entry)
                paths = source_mod.step_paths(entry)
                if not urls or not paths:
                    return None
                first = paths[0]
                if not (first.is_file() and first.stat().st_size > 0):
                    first.parent.mkdir(parents=True, exist_ok=True)
                    first.write_bytes(source_mod._get(urls[0]))
                    time.sleep(source_mod.POLITE_GAP)
                raw = first.read_bytes()
            SRC_THUMBS.mkdir(parents=True, exist_ok=True)
            return target if _shrink(raw, target, SRC_THUMB_WIDTH) else None

    def skip(self, uid) -> dict:
        data = self.decisions()
        data["skipped"] = sorted({*data["skipped"], str(uid)})
        source_mod.write_decisions(data)
        return {"ok": True}

    def auto_pin(self, entry: dict, map_: str) -> dict:
        """หมุดที่เดาได้จากชื่อโซนต้นทาง/ปลายทางของเว็บ — เว็บที่ไม่บอกโซนจะคืน {} เสมอ."""
        if not entry.get("from") and not entry.get("to"):
            return {}
        data = callout_mod.load(ROOT / "callouts.json")
        return route_pins.auto_pin(map_, entry.get("from"), entry.get("to"), data)

    def take(self, store: "Store", body: dict) -> dict:
        """รับรูปที่หน้าเว็บจัดหน้า+เขียนทับเสร็จแล้ว (base64 PNG) มาเก็บเข้าคลัง."""
        entry = self._entry(body.get("uid") or body.get("id"))
        map_ = body.get("map") or entry["m"]
        if map_ not in set(store.cfg.aliases.get("maps") or {}):
            raise ValueError(f"แมพ {map_} ไม่มีในคลังเรา เก็บใบนี้ไม่ได้")

        # "เก็บแค่ภาพเคลื่อนไหว" (ใบจากคลิป) — ตัวไลน์อัพคือไฟล์ WebP เคลื่อนไหวเลย ไม่มีรูปนิ่ง
        anim_only = bool(body.get("animOnly")) and bool(body.get("_gifpath"))
        if anim_only:
            temp = ROOT / ".cache" / "source-take.webp"
            shutil.copy2(body["_gifpath"], temp)
        else:
            raw = base64.b64decode(str(body.get("data") or "").split(",")[-1])
            if not raw:
                raise ValueError("ไม่มีข้อมูลรูปที่จัดหน้าแล้วส่งมา")
            temp = ROOT / ".cache" / "source-take.png"
            temp.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(raw)

        site = str(body.get("site") or entry["st"] or "a").lower()
        result = lib.add(
            store.cfg.lineups_dir, temp, map_,
            body.get("side") or entry["side"],
            site if site in SITES else "a",
            str(body.get("name") or entry.get("t") or f"lineup-{entry['i']}"),
            body.get("agent") or entry["a"], move_file=True,
        )
        rel = lib.rel_of(store.cfg.lineups_dir, result.path)
        # ต้องอ่านคลังใหม่ตรงนี้ก่อน ไม่งั้น set_pin ข้างล่างจะหาไฟล์ที่เพิ่งเพิ่มไม่เจอ
        # (มันเช็คจากรายการไลน์อัพในหน่วยความจำ ซึ่งยังเป็นของก่อนเพิ่ม)
        store.reload()

        tag = body.get("ability") or source_mod.ability_tag(entry.get("ab"))
        howto = str(body.get("howto") or "").strip()
        if tag or howto:
            meta_mod.set_fields(store.meta, rel, ability=tag, howto=howto)
            meta_mod.save(ROOT / "meta.json", store.meta)

        # จิ้มหมุดมาจากหน้าเว็บด้วยเลยก็ได้ — ไม่ได้จิ้มมาก็ลองเดาจากชื่อโซนที่เว็บต้นทางบอก
        pin = body.get("pin") or {}
        auto = not (pin.get("from") or pin.get("to"))
        if auto:
            pin = self.auto_pin(entry, map_)
        # ไม่มี "จุดยืน" ก็เก็บหมุดไม่ได้เลย (positions.json ต้องมี from เสมอ) — ปล่อยว่างไว้
        state = "none"
        if pin.get("from"):
            store.set_pin(rel, pin["from"], pin.get("to"))
            state = "full" if pin.get("to") else "half"

        # GIF ช่วงยิงจากคลิป (ทำไว้แล้วก่อนเข้าล็อก ดู do_POST) — วางคู่รูปชื่อเดียวกัน ในเกมกด numpad * ดู
        gif = body.get("_gifpath")
        if gif and Path(gif).is_file() and not anim_only:
            shutil.copy2(gif, result.path.with_suffix(".gif"))
            store.reload()

        data = self.decisions()
        data["taken"][entry["uid"]] = rel
        source_mod.write_decisions(data)
        store.reload()
        return {"rel": rel, "message": result.message, "ability": tag,
                "pin": state, "autoPin": auto and state != "none"}


def _shrink(raw: bytes, target: Path, width: int) -> bool:
    """ย่อรูปจากไบต์ดิบลงไฟล์ JPEG — ใช้ ``QImage`` ล้วน จึงไม่ต้องมี QApplication."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QImage

    image = QImage()
    if not image.loadFromData(raw):
        return False
    if image.width() > width:
        image = image.scaledToWidth(width, _Qt.TransformationMode.SmoothTransformation)
    return bool(image.save(str(target), "JPG", 80))


def thumb_for(store: Store, rel: str) -> Path | None:
    """รูปย่อของไลน์อัพใบนี้ (ทำครั้งเดียวแล้ว cache) — หน้าเว็บโหลดรูปเต็มทั้ง 150 ใบไม่ไหว.

    ใช้ ``QImage`` ล้วนๆ ซึ่ง **ไม่ต้องมี QApplication** (ต่างจาก QPixmap) เซิร์ฟเวอร์จึงไม่ต้อง
    เปิดหน้าต่าง Qt อะไรเลย — ทดสอบแล้วว่าย่อ+เซฟได้ราว 60ms ต่อใบ
    """
    lu = store.find(rel)
    if lu is None or not lu.path.is_file():
        return None
    stamp = int(lu.path.stat().st_mtime)
    # sha1 ไม่ใช่ hash() — hash() ของ Python สุ่มใหม่ทุกครั้งที่เปิดโปรแกรม แคชเลยใช้ข้ามรอบไม่ได้
    # เปิดหน้าเว็บทีไรย่อรูปใหม่ทั้งคลัง การ์ดดำเป็นนาทีจนดูเหมือนคลังว่าง (ผู้ใช้เจอจริง)
    key = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]
    target = THUMBS / f"{key}-{stamp}.jpg"
    if target.is_file():
        return target

    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QImage

    image = QImage(str(lu.path))
    if image.isNull():
        return None
    THUMBS.mkdir(parents=True, exist_ok=True)
    small = image.scaledToWidth(THUMB_WIDTH, _Qt.TransformationMode.SmoothTransformation)
    return target if small.save(str(target), "JPG", 82) else None


class Handler(BaseHTTPRequestHandler):
    server_version = "LineupMasterWeb"

    def __init__(self, *args, store: Store, source: SourceBrowser, token: str,
                 community: CommunityWeb | None = None, **kwargs) -> None:
        self.store = store
        self.source = source
        self.token = token
        self.community = community or CommunityWeb(store, ROOT)
        self._cors: dict[str, str] = {}
        super().__init__(*args, **kwargs)

    # -- ตัวช่วยตอบกลับ ---------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        for name, value in self._cors.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str) -> None:
        """ส่งไฟล์แบบขอทีละส่วนได้ (Range → 206) — ``<video>`` ต้องใช้ ไม่งั้นกระโดดไปเวลาอื่นไม่ได้."""
        size = path.stat().st_size
        wanted = self.headers.get("Range", "")
        found = re.fullmatch(r"bytes=(\d*)-(\d*)", wanted.strip())
        if not found or not (found.group(1) or found.group(2)):
            self.send_response(200)
            first, last = 0, size - 1
        else:
            if found.group(1):
                first = int(found.group(1))
                last = min(int(found.group(2)), size - 1) if found.group(2) else size - 1
            else:                                          # bytes=-500 = 500 ไบต์สุดท้าย
                first, last = max(0, size - int(found.group(2))), size - 1
            if first >= size or first > last:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        length = last - first + 1
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(first)
            left = length
            while left > 0:
                chunk = handle.read(min(left, 1 << 20))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return                                 # เบราว์เซอร์เลิกขอกลางทาง (กระโดดเวลา) — ปกติ
                left -= len(chunk)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _fail(self, message: str, code: int = 400) -> None:
        self._json({"error": str(message)}, code)

    def _guard(self, query: dict) -> bool:
        """กันหน้าเว็บอื่นในเครื่องยิงคำสั่งเข้ามาลบไฟล์ — ต้องมี token ที่สุ่มตอนเปิดโปรแกรม."""
        given = (query.get("t") or [""])[0] or self.headers.get("X-Token", "")
        if secrets.compare_digest(given, self.token):
            return True
        self._fail("token ไม่ถูกต้อง — เปิดหน้านี้จากลิงก์ที่โปรแกรมเปิดให้เท่านั้น", 403)
        return False

    # -- tracker.gg: bookmarklet ในเบราว์เซอร์ของผู้ใช้ส่งรายการเข้ามา ------------------
    # ไม่ใช้ token หน้าเว็บ (เปลี่ยนทุกรอบ) แต่ใช้รหัสถาวรของ bookmarklet (?k=) + จำกัด Origin ให้ tracker.gg
    def _tracker_gate(self, query: dict) -> bool:
        origin = self.headers.get("Origin", "")
        if origin and origin not in TRACKER_ORIGINS:
            self._fail("ไม่รับคำขอจากเว็บนี้", 403)
            return False
        if not secrets.compare_digest((query.get("k") or [""])[0], source_mod.tg_key()):
            self._fail("รหัสไม่ถูกต้อง — ติดตั้ง bookmarklet ใหม่จากหน้าตั้งค่า", 403)
            return False
        if origin:
            self._cors = {
                "Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Private-Network": "true",
                "Access-Control-Allow-Local-Network": "true",
            }
        return True

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server API
        """preflight ของเบราว์เซอร์ (รวมการขออนุญาตเข้าเครือข่ายภายใน) — ตอบเฉพาะเส้นทาง tracker จาก tracker.gg."""
        origin = self.headers.get("Origin", "")
        if not urlparse(self.path).path.startswith("/api/tracker/") or origin not in TRACKER_ORIGINS:
            self._fail("ไม่มีเส้นทางนี้", 404)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Local-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _tracker_push(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= TRACKER_MAX_BODY:
            self._fail("ข้อมูลที่ส่งมาว่างหรือใหญ่เกินไป", 413)
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            count = source_mod.tg_store(str(body.get("agent") or ""), body.get("items") or [])
        except (ValueError, AttributeError, TypeError) as error:
            self._fail(error)
            return
        self.source.reset_catalog()
        self._json({"ok": True, "agent": source_mod.tg_slug(body["agent"]), "count": count})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -- เส้นทาง ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route == "/api/tracker/ping":
            if self._tracker_gate(query):
                self._json({"ok": True, "app": "LineupMaster"})
            return

        if route == "/community/callback":
            # Supabase เด้งกลับมาหลังกดยืนยันใน Discord — ?t= ติดมากับ redirect_to ที่เราส่งไปเอง
            if not self._guard(query):
                return
            try:
                self.community.finish_login((query.get("code") or [""])[0])
                note = "ล็อกอินแล้ว"
            except CommunityError as error:
                note = f"ล็อกอินไม่สำเร็จ: {error}"
            target = f"/?t={self.token}#community"
            body = (f"<meta charset='utf-8'><meta http-equiv='refresh' content='1;url={target}'>"
                    f"<p style='font:16px sans-serif'>{note} — กำลังกลับไปหน้าคอมมูนิตี้…</p>")
            self._send(200, body.encode("utf-8"), "text/html; charset=utf-8")
            return

        if route.startswith("/api/community/"):
            if self._guard(query):
                self._community(route, query, {})
            return

        if route == "/api/video/file":
            if self._guard(query):
                path = self.source.video_file((query.get("uid") or [""])[0])
                if path is None:
                    self._fail("ไม่มีคลิปนี้ในเครื่อง — วางลิงก์เปิดใหม่อีกครั้ง", 404)
                else:
                    self._send_file(path, "video/mp4")
            return
        if route == "/api/clip/suggest":
            if self._guard(query):
                try:
                    self._json(self.source.clip_suggest((query.get("uid") or [""])[0]))
                except KeyError as error:
                    self._fail(error, 404)
            return
        if route == "/api/clip/file":
            if self._guard(query):
                path = self.source.clip_file((query.get("uid") or [""])[0], (query.get("name") or [""])[0])
                if path is None:
                    self._fail("ไม่เจอไฟล์นี้", 404)
                else:
                    self._send(200, path.read_bytes(), "image/webp", cache=True)
            return
        if route == "/api/clip/frame":
            if self._guard(query):
                path = self.source.clip_frame((query.get("uid") or [""])[0], int((query.get("i") or ["0"])[0]),
                                              (query.get("s") or [""])[0] == "1")
                if path is None:
                    self._fail("ไม่เจอเฟรมนี้ (โหลดคลิปใหม่อีกครั้ง)", 404)
                else:
                    self._send(200, path.read_bytes(), "image/jpeg", cache=True)
            return

        if route == "/api/voice/sample":
            if self._guard(query):
                self._voice_sample()
            return

        if route.startswith("/api/"):
            if not self._guard(query):
                return
            try:
                self._api_get(route, query)
            except (KeyError, ValueError, OSError) as error:
                self._fail(error)
            return

        self._static(route)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not parsed.path.startswith("/api/"):
            self._fail("ไม่มีเส้นทางนี้", 404)
            return
        if parsed.path == "/api/tracker/push":
            if self._tracker_gate(query):
                self._tracker_push()
            return
        if not self._guard(query):
            return
        try:
            body = self._body()
        except ValueError:
            self._fail("ข้อมูลที่ส่งมาไม่ใช่ JSON")
            return
        if parsed.path.startswith("/api/community/"):
            self._community(parsed.path, query, body)     # ต่อเน็ต — ห้ามถือล็อกของ Store ไว้รอ
            return
        if parsed.path == "/api/clip/gif":              # ต่อเน็ต + ทำ GIF ~5 วิ — ไม่ถือล็อก
            try:
                path = self.source.clip_gif(str(body.get("uid") or ""), body.get("start"), body.get("end"))
                self._json({"name": path.name, "kb": path.stat().st_size // 1024})
            except KeyError as error:
                self._fail(error, 404)
            except (ValueError, OSError, TypeError) as error:
                self._fail(error)
            return
        if parsed.path == "/api/source/take" and isinstance(body.get("gif"), dict):
            try:                                        # ทำ GIF ให้เสร็จก่อนเข้าล็อก (ต่อเน็ตได้หลายวินาที)
                gif = body["gif"]
                body["_gifpath"] = str(self.source.clip_gif(str(body.get("uid") or ""), gif.get("start"), gif.get("end")))
            except (KeyError, ValueError, OSError, TypeError) as error:
                self._fail(f"ทำ GIF ไม่สำเร็จ: {error}")
                return
        if parsed.path == "/api/source/take" and isinstance(body.get("plan"), dict):
            try:                                        # ทำภาพเคลื่อนไหวตามแผนก่อนเข้าล็อก (~3 วิ)
                body["_gifpath"] = str(self.source.video_render(str(body.get("uid") or ""), body["plan"]))
                body["animOnly"] = True
            except KeyError as error:
                self._fail(error, 404)
                return
            except (ValueError, OSError, TypeError) as error:
                self._fail(f"ทำภาพเคลื่อนไหวไม่สำเร็จ: {error}")
                return
        if parsed.path == "/api/video/open":            # ต่อเน็ต + โหลดคลิป ~10 วิ — ไม่ถือล็อก
            try:
                if body.get("uid"):
                    self._json(self.source.video_open_entry(str(body["uid"])))
                else:
                    self._json(self.source.video_open(str(body.get("link") or ""), self.store.cfg.aliases))
            except KeyError as error:
                self._fail(error, 404)
            except (ValueError, OSError) as error:
                self._fail(error)
            return
        if parsed.path == "/api/clip/load":             # ต่อเน็ต + ถอดวิดีโอ ~20 วิ — ไม่ถือล็อก
            try:
                self._json(self.source.clip_load(str(body.get("link") or ""), self.store.cfg.aliases))
            except (ValueError, OSError) as error:
                self._fail(error)
            return
        if parsed.path == "/api/voice/preview":
            self._voice_preview(str(body.get("rel") or ""), body.get("howto"))
            return
        if parsed.path == "/api/voice/make":
            self._voice_make(str(body.get("text") or ""))  # ต่อเน็ตเหมือนกัน — ไม่ถือล็อก
            return
        try:
            with self.store.lock:
                self._api_post(parsed.path, body)
        except KeyError as error:
            self._fail(error, 404)
        except (ValueError, OSError) as error:
            self._fail(error)

    # -- เสียงพูด: สร้างไฟล์ผ่านเน็ต จึงไม่ถือล็อกของ Store ไว้ระหว่างรอ -------------
    def _voice_make(self, text: str) -> None:
        if not text.strip():
            self._fail("ไม่มีข้อความ")
            return
        rate = int(self.store.voice_options()["rate"])
        text = text.strip()
        path = voice_mod.clip_path(_voice_cache(), text, rate)
        if path.is_file() or voice_mod.synthesize(text, path, rate):
            self._json({"ok": True})
            return
        # เสียงหลักไม่ผ่าน — ทำเสียงสำรองไว้ให้ในเกมมีเสียงไปก่อน แต่ยังนับว่าขาด (กดรอบหน้าลองเสียงหลักใหม่)
        voice_mod.ensure_clip(_voice_cache(), text, rate, tries=0)
        self._fail("เสียงหลักสร้างไม่สำเร็จ (ใช้เสียงสำรองไปก่อน)", 502)

    def _voice_preview(self, rel: str, howto) -> None:
        """ฟังประโยคที่เกมจะพูดตอนเลือกใบนี้ — ใช้วิธียิงที่พิมพ์ค้างในฟอร์ม (ยังไม่บันทึกก็ฟังได้).

        เสียงที่สร้างเก็บในแคชเดียวกับตอนเล่น — ข้อความที่บันทึกจริงตรงกันก็ไม่ต้องสร้างซ้ำ
        ส่วนร่างที่ลองฟังแล้วทิ้ง prune ลบให้เองรอบหน้า (ไม่ตรงกับประโยคไหนในคลัง)
        """
        from dataclasses import replace

        with self.store.lock:
            lu = self.store.find(rel)
            options = self.store.voice_options()
        if lu is None:
            self._fail("ไม่เจอไลน์อัพใบนี้", 404)
            return
        if howto is not None:
            lu = replace(lu, howto=str(howto))
        text = voice_mod.spoken_lineup(lu, ABILITY_TH, bool(options["notes"]))
        path = voice_mod.ensure_clip(_voice_cache(), text, int(options["rate"]), tries=2)
        if path is None:
            self._fail("สร้างเสียงไม่สำเร็จ — เช็คว่าต่อเน็ตอยู่ แล้วลองใหม่", 502)
            return
        self._send(200, path.read_bytes(), "audio/mpeg")

    def _voice_sample(self) -> None:
        """ทดลองฟังในหน้าเว็บ — ความเร็วตามที่ตั้งไว้ตอนนี้."""
        path = voice_mod.ensure_clip(_voice_cache(), voice_mod.SAMPLE, int(self.store.voice_options()["rate"]))
        if path is None:
            self._fail("สร้างเสียงไม่สำเร็จ — เช็คว่าต่อเน็ตอยู่ แล้วลองใหม่", 502)
            return
        self._send(200, path.read_bytes(), "audio/mpeg")

    def _community(self, route: str, query: dict, body: dict) -> None:
        """แท็บคอมมูนิตี้ (ดู tools/community_web.py) — ยังไม่ล็อกอินตอบ 401 ให้หน้าเว็บขึ้นปุ่มล็อกอิน."""
        c = self.community
        arg = lambda name: (query.get(name) or [""])[0]   # noqa: E731
        try:
            if route == "/api/community/state":
                self._json(c.state())
            elif route == "/api/community/config":
                self._json(c.configure(body))
            elif route == "/api/community/login":
                port = self.server.server_address[1]
                self._json(c.login(f"http://{HOST}:{port}/community/callback?t={self.token}"))
            elif route == "/api/community/logout":
                self._json(c.logout())
            elif route == "/api/community/feed":
                self._json(c.feed(arg("agent"), arg("map")))
            elif route == "/api/community/take":
                self._json(c.take(str(body.get("id") or "")))
            elif route == "/api/community/share":
                self._json(c.share(list(body.get("rels") or [])))
            elif route == "/api/community/vote":
                self._json(c.vote(str(body.get("id") or ""), int(body.get("value") or 0)))
            elif route == "/api/community/sync":
                self._json({"sent": c.sync()})
            else:
                self._fail("ไม่มีเส้นทางนี้", 404)
        except NotLoggedIn as error:
            self._fail(error, 401)
        except KeyError as error:
            self._fail(error, 404)
        except (CommunityError, ValueError, OSError) as error:
            self._fail(error)

    def _api_get(self, route: str, query: dict) -> None:
        store = self.store
        if route == "/api/state":
            with store.lock:
                self._json(store.state())
            return
        if route == "/api/settings":
            with store.lock:
                self._json(store.settings_state())
            return
        if route == "/api/settings/live":
            self._json(store.settings_live())     # อ่านไฟล์เล็กไฟล์เดียว ไม่แตะ Store — ไม่ถือล็อก
            return
        if route in ("/api/curate/agents", "/api/curate"):
            catalog = self.source.catalog()       # โหลดครั้งแรกอาจช้า — ทำนอกล็อก
            with store.lock:
                if route == "/api/curate/agents":
                    self._json(store.curate_agents(catalog))
                else:
                    keep = int((query.get("keep") or ["1"])[0] or 1)
                    singles = (query.get("singles") or ["0"])[0] == "1"
                    self._json(store.curate_state(catalog, (query.get("agent") or [""])[0],
                                                  max(1, min(3, keep)), singles))
            return
        if route == "/api/merge/candidates":
            # สแกนโฟลเดอร์ในเครื่องนาน และไม่แตะข้อมูลของ Store — ไม่ถือล็อก หน้าเว็บจะได้ไม่ค้าง
            self._json(store.merge_candidates())
            return
        if route == "/api/merge/image":
            # รูปย่อของรูปที่ขัดกัน — หา path จากแผนที่จำไว้เท่านั้น (ดู Store.merge_image)
            side = (query.get("side") or [""])[0]
            try:
                conflict_id = int((query.get("id") or [""])[0])
            except ValueError:
                conflict_id = -1
            with store.lock:
                path = store.merge_image(side, conflict_id)
            if path is None:
                self._fail("ไม่เจอรูปนี้ในสรุปที่ดูอยู่", 404)
                return
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), ctype)
            return
        if route == "/api/voice/candidates":
            with store.lock:
                self._json(store.voice_candidates())
            return
        if route == "/api/shrink/candidates":
            with store.lock:
                self._json(store.shrink_candidates())
            return
        if route == "/api/map-extras":
            map_ = (query.get("map") or [""])[0]
            side = (query.get("side") or [""])[0] or None
            with store.lock:
                self._json(store.map_extras(map_, side))
            return
        if route == "/api/image":
            rel = (query.get("rel") or [""])[0]
            with store.lock:
                lu = store.find(rel)
            if lu is None or not lu.path.is_file():
                self._fail("ไม่เจอไฟล์รูป", 404)
                return
            ctype = mimetypes.guess_type(lu.path.name)[0] or "image/png"
            self._send(200, lu.path.read_bytes(), ctype, cache=True)
            return
        if route == "/api/thumb":
            rel = (query.get("rel") or [""])[0]
            with store.lock:
                path = thumb_for(store, rel)
            if path is None:
                self._fail("ย่อรูปไม่ได้", 404)
                return
            self._send(200, path.read_bytes(), "image/jpeg", cache=True)
            return
        if route == "/api/tracker/status":
            self._json({"agents": source_mod.tg_status(), "bookmarklet": tracker_bookmarklet()})
            return
        if route == "/api/source/catalog":
            force = (query.get("force") or [""])[0] == "1"
            self._json({"lineups": self.source.catalog(force=force),
                        "decisions": self.source.decisions(),
                        "tracker": max((a["saved"] for a in source_mod.tg_status()), default=0),
                        "sources": [{"id": s.key, "name": s.name, "site": s.site}
                                    for s in source_mod.SOURCES.values()]})
            return
        if route == "/api/source/prepare":
            self._json(self.source.prepare((query.get("uid") or [""])[0]))
            return
        if route == "/api/source/step":
            path = self.source.step_file((query.get("uid") or [""])[0],
                                         int((query.get("i") or ["1"])[0]))
            if path is None:
                self._fail("ยังไม่ได้โหลดรูปขั้นนี้", 404)
                return
            ctype = mimetypes.guess_type(path.name)[0] or "image/webp"
            self._send(200, path.read_bytes(), ctype, cache=True)
            return
        if route == "/api/source/autopin":
            try:
                entry = self.source._entry((query.get("uid") or [""])[0])
            except KeyError as error:
                self._fail(str(error), 404)
                return
            map_ = (query.get("map") or [""])[0] or entry["m"]
            pin = self.source.auto_pin(entry, map_)
            if not pin.get("from"):
                pin = {}          # ไม่มีจุดยืน = เก็บหมุดไม่ได้ ส่งกลับเป็นไม่มีเลยดีกว่า
            self._json({"pin": pin, "state": route_pins.pin_state(pin)})
            return
        if route == "/api/source/thumb":
            try:
                path = self.source.thumb_file((query.get("uid") or [""])[0])
            except (KeyError, OSError, ValueError):
                path = None
            if path is None:
                self._fail("ย่อรูปใบนี้ไม่ได้", 404)
                return
            self._send(200, path.read_bytes(), "image/jpeg", cache=True)
            return
        if route == "/api/map":
            name = (query.get("name") or [""])[0]
            path = MAPS / f"{Path(name).name}.png"
            if not path.is_file():
                self._fail("ยังไม่มีรูปแผนที่นี้ — รันเครื่องมือ 'โหลดรูปแผนที่' ก่อน", 404)
                return
            self._send(200, path.read_bytes(), "image/png", cache=True)
            return
        self._fail("ไม่มีเส้นทางนี้", 404)

    def _api_post(self, route: str, body: dict) -> None:
        store = self.store
        if route == "/api/save":
            self._json(store.save_edits(body))
        elif route == "/api/delete":
            self._json(store.delete(body["rel"]))
        elif route == "/api/draw":
            self._json(store.save_drawing(body["rel"], body.get("png")))
        elif route == "/api/shrink":
            self._json(store.shrink(str(body.get("rel") or "")))
        elif route == "/api/draw/revert":
            self._json(store.revert_drawing(body["rel"]))
        elif route == "/api/pin":
            self._json(store.set_pin(body["rel"], body["from"], body.get("to")))
        elif route == "/api/pin/clear":
            self._json(store.clear_pin(body["rel"]))
        elif route == "/api/site-label":
            self._json(store.set_site_label(body["map"], body["site"], body.get("point")))
        elif route == "/api/add":
            self._json(store.add_image(body))
        elif route == "/api/bulk":
            self._json(store.bulk(body))
        elif route == "/api/source/take":
            self._json(self.source.take(store, body))
        elif route == "/api/source/skip":
            self._json(self.source.skip(body.get("uid") or body.get("id")))
        elif route == "/api/curate/decide":
            self._json(store.curate_decide(str(body.get("agent") or ""), str(body.get("key") or ""),
                                           body.get("keep")))
        elif route == "/api/curate/apply":
            self._json(store.curate_apply(self.source.catalog(), str(body.get("agent") or "")))
        elif route == "/api/settings/set":
            self._json(store.settings_set(body.get("key"), body.get("value")))
        elif route == "/api/settings/reset":
            self._json(store.settings_reset(body.get("key")))
        elif route == "/api/merge/preview":
            self._json(store.merge_preview(body.get("path")))
        elif route == "/api/merge/apply":
            self._json(store.merge_apply(body.get("choices") or {}))
        elif route == "/api/reload":
            store.reload()
            self._json(store.state())
        else:
            self._fail("ไม่มีเส้นทางนี้", 404)

    def _static(self, route: str) -> None:
        """เสิร์ฟไฟล์หน้าเว็บจาก assets/web/ — อยู่นอก exe แก้แล้วกด refresh เห็นผลเลย.

        ``/art/agents/…`` · ``/art/abilities/…`` = รูปหน้าตัวละคร/ไอคอนสกิล (assets/ ชุดเดียวกับหน้าเข้าโปรแกรม)
        """
        if route.startswith("/art/"):
            rel = route[len("/art/"):]
            base = ASSETS.resolve()
            path = (ASSETS / rel).resolve()
            if (rel.split("/")[0] in ("agents", "abilities") and str(path).startswith(str(base))
                    and path.is_file() and path.suffix.lower() == ".png"):
                self._send(200, path.read_bytes(), "image/png", cache=True)
            else:
                self._fail("ไม่เจอรูป", 404)
            return
        name = "index.html" if route in ("/", "") else route.lstrip("/")
        path = (WEB_DIR / name).resolve()
        if not str(path).startswith(str(WEB_DIR.resolve())) or not path.is_file():
            self._fail("ไม่เจอไฟล์", 404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def log_message(self, *_args) -> None:
        pass          # เงียบไว้ ไม่งั้นคอนโซลเต็มไปด้วยบรรทัด GET /api/thumb ทุกใบ


def _free_port() -> int:
    for port in PORT_RANGE:
        with socket.socket() as probe:
            if probe.connect_ex((HOST, port)) != 0:
                return port
    raise OSError("หาพอร์ตว่างไม่ได้เลยในช่วงที่กำหนด")


def _prune_old_thumbs() -> None:
    """รูปย่อรุ่นเก่า (ชื่อจาก hash() ที่สุ่มใหม่ทุกรอบ) ใช้ซ้ำไม่ได้แล้ว — ล้างทิ้ง เป็นแค่แคชที่สร้างใหม่ได้."""
    if not THUMBS.is_dir():
        return
    for path in THUMBS.glob("*.jpg"):
        key = path.stem.split("-")[0]
        if len(key) != 16 or any(c not in "0123456789abcdef" for c in key):
            path.unlink(missing_ok=True)


def _close_with_parent(pid: int, httpd) -> None:
    """เปิดเบื้องหลังจากหน้าเข้าโปรแกรม (ไม่มีหน้าต่างให้ผู้ใช้กดปิด) — หน้านั้นปิดเมื่อไหร่ ปิดตามเอง
    ไม่งั้นค้างอยู่ใน Task Manager เงียบๆ และล็อกโฟลเดอร์จนบิ้ว/อัปเดตไม่ได้ (เจอมาแล้ว)."""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
    if not handle:
        return

    def watch() -> None:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)          # รอจนโปรเซสนั้นจบ
        httpd.shutdown()

    threading.Thread(target=watch, daemon=True).start()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    if not WEB_DIR.is_dir():
        print(f"[x] ไม่เจอไฟล์หน้าเว็บที่ {WEB_DIR}")
        return 1

    import argparse
    import os

    parser = argparse.ArgumentParser(prog="web")
    parser.add_argument("--open", default="", help="เปิดหน้าไหน (library/community/flag/unpinned/add/settings)")
    parser.add_argument("--parent", type=int, default=0,
                        help="pid ของหน้าเข้าโปรแกรมที่เปิดตัวนี้ — ตัวนั้นปิด ตัวนี้ปิดตาม")
    args, _rest = parser.parse_known_args(sys.argv[1:])

    _prune_old_thumbs()
    clipgrab.prune_proxies(ROOT)
    store = Store()
    source = SourceBrowser()
    token = secrets.token_urlsafe(16)
    port = _free_port()
    url = f"http://{HOST}:{port}/?t={token}"
    # หน้าเข้าโปรแกรม (launcher.py) ใช้ไฟล์นี้หาเซิร์ฟเวอร์ที่เปิดอยู่แล้ว — ไม่เปิดซ้อนหลายตัว
    live = ROOT / ".cache" / "web.json"
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(json.dumps({"url": url, "pid": os.getpid()}), encoding="utf-8")

    handler = partial(Handler, store=store, source=source, token=token)
    httpd = ThreadingHTTPServer((HOST, port), handler)

    print("=" * 62)
    print("  หน้าจัดการคลัง (เว็บ) เปิดแล้ว")
    print("=" * 62)
    print(f"  {url}")
    print()
    print(f"  ไลน์อัพในคลัง {len(store.lineups)} ใบ · ยังไม่จิ้มหมุด {store.state()['unpinned']} ใบ")
    print(f"  ไฟล์หน้าเว็บ: {WEB_DIR}  (แก้แล้วกด refresh ในเบราว์เซอร์ได้เลย)")
    print()
    print("  ปิดโปรแกรมนี้ด้วย Ctrl+C ที่หน้าต่างนี้")
    print()
    webbrowser.open(url + (f"#{args.open}" if args.open else ""))
    if args.parent:
        _close_with_parent(args.parent, httpd)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("ปิดแล้ว")
    finally:
        httpd.server_close()
        live.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

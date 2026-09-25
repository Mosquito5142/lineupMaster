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
import json
import mimetypes
import secrets
import socket
import sys
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from lineupmaster import callouts as callout_mod  # noqa: E402
from lineupmaster import config as config_mod  # noqa: E402
from lineupmaster import index as index_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import merge as merge_mod  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster import positions as pos_mod  # noqa: E402
from lineupmaster.browser import ABILITY_TH, AGENT_ABILITIES, AGENT_TH, SIDES, SITES  # noqa: E402
from lineupmaster.index import IMAGE_SUFFIXES  # noqa: E402
from lineupmaster.paths import ASSETS, MAPS, ROOT  # noqa: E402
# ตัวโหลดไลน์อัพจากเว็บอยู่ที่ lineup_sources.py — ใช้ร่วมกับเครื่องมือ Qt เดิม สูตร URL,
# การจับคู่ชื่อสกิล และไฟล์จำว่าเอา/ไม่เอาใบไหน จึงเป็นชุดเดียวกันทั้งสองหน้า ไม่ต้องดูแลสองที่
import lineup_sources as source_mod  # noqa: E402
import route_pins  # noqa: E402

# Windows ไม่รู้จักนามสกุลฟอนต์เว็บ ต้องบอกเอง ไม่งั้นเสิร์ฟเป็น octet-stream
mimetypes.add_type("font/woff2", ".woff2")

WEB_DIR = ASSETS / "web"
THUMBS = ROOT / ".cache" / "thumbs"
SRC_THUMBS = ROOT / ".cache" / "source-thumbs"
THUMB_WIDTH = 420
SRC_THUMB_WIDTH = 360

HOST = "127.0.0.1"          # เปิดให้เฉพาะเครื่องตัวเอง ไม่รับจากเครื่องอื่นในวง LAN เด็ดขาด
PORT_RANGE = range(8760, 8800)


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
        self.meta = meta_mod.load(ROOT / "meta.json")
        self.lineups = index_mod.scan(self.cfg.lineups_dir, self.cfg.aliases)
        meta_mod.apply(self.meta, self.lineups)

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
            "note": lu.note or "",
            "gif": lu.gif is not None,
            "pin": {
                "from": pos_mod.point_of(entry, "from"),
                "to": pos_mod.point_of(entry, "to"),
            } if entry else None,
        }

    def state(self) -> dict:
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
            "unpinned": sum(1 for lu in self.lineups if lu.rel not in self.positions),
        }

    def map_extras(self, map_: str, side: str | None) -> dict:
        """ป้ายจุด A/B/C + ชื่อโซนอ้างอิงของแมพนี้ — ของประกอบตอนจิ้มหมุด."""
        group = [lu for lu in self.lineups if lu.map == map_ and (not side or lu.side == side)]
        labels = pos_mod.site_labels(map_, group, self.positions)
        data = callout_mod.load(ROOT / "callouts.json")
        return {
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
        before = dict(meta_mod.entry(self.meta, rel))
        meta_mod.set_fields(self.meta, rel, ability=body.get("ability") or None,
                            fav=bool(body.get("fav")), tags=body.get("tags") or [])
        if meta_mod.entry(self.meta, rel) != before:
            meta_mod.save(ROOT / "meta.json", self.meta)
            changes.append("แก้สกิล/ไม้ตาย/แท็ก")

        self.reload()
        return {"rel": rel, "changes": changes or ["ไม่มีอะไรเปลี่ยน"]}

    def delete(self, rel: str) -> dict:
        lu = self.find(rel)
        if lu is None:
            raise KeyError("ไม่เจอไลน์อัพใบนี้")
        extras = [p.name for p in lib.sidecars(lu.path)]
        result = lib.remove(ROOT, self.cfg.lineups_dir, lu.path)
        self.reload()
        return {"message": result.message, "extras": extras}

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
        meta_touched = False
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
                meta_mod.set_fields(self.meta, new_rel, **fields)
                meta_touched = True
            done += 1
        if meta_touched:
            meta_mod.save(ROOT / "meta.json", self.meta)
        self.reload()
        return {"done": done}

    # -- รวมคลังจากโฟลเดอร์อื่น (ตัวรวมจริงอยู่ที่ lineupmaster/merge.py) -------------
    def merge_candidates(self) -> dict:
        """โฟลเดอร์คลังอื่นในเครื่องที่น่าจะอยากรวม — แถวโฟลเดอร์แม่ของโปรแกรม, Desktop, Downloads."""
        home = Path.home()
        roots = [ROOT.parent, home / "Desktop", home / "Downloads", home / "Documents",
                 home / "OneDrive" / "Desktop"]
        return {"folders": merge_mod.find_candidates(roots, exclude=ROOT)}

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

    def merge_apply(self, choices: dict) -> dict:
        """รวมตามแผนที่ดูสรุปไว้ล่าสุด — ใช้ได้ครั้งเดียว (ล้มเพราะคลังเปลี่ยนก็ต้องดูสรุปใหม่)."""
        if self.merge_plan is None:
            raise ValueError("ยังไม่ได้ดูสรุป — เลือกโฟลเดอร์แล้วกดดูสรุปก่อน")
        plan, self.merge_plan = self.merge_plan, None
        report = merge_mod.apply(plan, choices)
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

    def catalog(self, force: bool = False) -> list[dict]:
        with self.lock:
            if force or not self._catalog:
                self._catalog = source_mod.fetch_catalog(force=force)
                self._callout_stamp = -1.0
            self._mark_pins()
            return self._catalog

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
            if entry.get("from") or entry.get("to"):
                lookup = index.get(entry["m"]) or []
                start = route_pins.match(entry.get("from"), lookup)
                end = route_pins.match(entry.get("to"), lookup)
                # ไม่มีจุดยืนก็เก็บหมุดไม่ได้เลย (positions.json ต้องมี from เสมอ)
                pin = {"from": start, "to": end} if start else {}
            entry["pin"] = route_pins.pin_state(pin)
        self._callout_stamp = stamp

    def decisions(self) -> dict:
        return source_mod.read_decisions()

    def find(self, uid: str) -> dict | None:
        return next((l for l in self.catalog() if l["uid"] == uid), None)

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
        if tag:
            meta_mod.set_fields(store.meta, rel, ability=tag)
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
    target = THUMBS / f"{abs(hash(rel)) % (10 ** 12)}-{stamp}.jpg"
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

    def __init__(self, *args, store: Store, source: SourceBrowser, token: str, **kwargs) -> None:
        self.store = store
        self.source = source
        self.token = token
        super().__init__(*args, **kwargs)

    # -- ตัวช่วยตอบกลับ ---------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

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
        if not self._guard(query):
            return
        try:
            body = self._body()
        except ValueError:
            self._fail("ข้อมูลที่ส่งมาไม่ใช่ JSON")
            return
        try:
            with self.store.lock:
                self._api_post(parsed.path, body)
        except KeyError as error:
            self._fail(error, 404)
        except (ValueError, OSError) as error:
            self._fail(error)

    def _api_get(self, route: str, query: dict) -> None:
        store = self.store
        if route == "/api/state":
            with store.lock:
                self._json(store.state())
            return
        if route == "/api/merge/candidates":
            # สแกนโฟลเดอร์ในเครื่องนาน และไม่แตะข้อมูลของ Store — ไม่ถือล็อก หน้าเว็บจะได้ไม่ค้าง
            self._json(store.merge_candidates())
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
        if route == "/api/source/catalog":
            force = (query.get("force") or [""])[0] == "1"
            self._json({"lineups": self.source.catalog(force=force),
                        "decisions": self.source.decisions(),
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
        """เสิร์ฟไฟล์หน้าเว็บจาก assets/web/ — อยู่นอก exe แก้แล้วกด refresh เห็นผลเลย."""
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


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    if not WEB_DIR.is_dir():
        print(f"[x] ไม่เจอไฟล์หน้าเว็บที่ {WEB_DIR}")
        return 1

    store = Store()
    source = SourceBrowser()
    token = secrets.token_urlsafe(16)
    port = _free_port()
    url = f"http://{HOST}:{port}/?t={token}"

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
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("ปิดแล้ว")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

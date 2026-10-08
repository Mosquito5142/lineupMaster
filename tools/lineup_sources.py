"""แหล่งไลน์อัพจากเว็บ — ตัวโหลดกลางที่ทั้งโปรแกรม Qt และหน้าเว็บจัดการคลังใช้ร่วมกัน.

เดิมตัวโหลดฝังอยู่ใน ``browse_lineups.py`` และรองรับเว็บเดียว พอจะเพิ่มเว็บที่สองเลยย้าย
ออกมาไว้ตรงนี้ แล้วให้ทุกแหล่ง**คืนข้อมูลรูปแบบเดียวกัน** (ดู ``_norm_*`` ข้างล่าง) ฝั่งที่
เรียกใช้จะได้ไม่ต้องรู้ว่ามาจากเว็บไหน

รหัสไลน์อัพใช้เป็น ``uid`` แบบ ``"<แหล่ง>:<เลข>"`` (เช่น ``vlp:7349``) เพราะเลขของแต่ละ
เว็บชนกันได้ — ของเดิมใน ``browse.json`` เก็บเป็นเลขล้วน ตอนอ่านจึงแปลงให้เป็น ``vlp:`` ให้
อัตโนมัติ (ดู ``read_decisions``) ที่เคยคัดไว้แล้วจะได้ไม่หาย

> รูปเป็นของเว็บต้นทาง/ชุมชนที่ทำไว้ — โหลดมาดูเองในเครื่องเพื่อใช้ซ้อม ไม่ได้เอาไปแจกต่อ
> และหน่วงจังหวะโหลดไว้ (POLITE_GAP) ไม่ยิงถี่ใส่เซิร์ฟเวอร์เขา
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE / "src") not in sys.path:
    sys.path.insert(0, str(_HERE / "src"))

from lineupmaster.browser import SITES  # noqa: E402
from lineupmaster.paths import ROOT  # noqa: E402

TIMEOUT = 30
POLITE_GAP = 0.12                            # หน่วงระหว่างคำขอ ไม่ยิงถี่ใส่เว็บเขา
DATA_MAX_AGE = 7 * 24 * 3600                 # เกินหนึ่งสัปดาห์ค่อยไปถามเว็บใหม่เอง
HEADERS = {"User-Agent": "LineupMaster (personal offline lineup viewer)"}

STATE = ROOT / "browse.json"                 # จำว่าเคยเอา/ไม่เอาใบไหนไปแล้ว
_CACHE_ROOT = ROOT / ".cache"

# ชื่อสกิลของเว็บ -> แท็กสกิลของเรา (ดู ABILITY_TH ใน browser.py) — เทียบจากคำที่โผล่ในชื่อ
# เพราะแต่ละตัวละครเรียกไม่เหมือนกัน (Recon Bolt / Owl Drone / Toxic Screen ฯลฯ)
ABILITY_WORDS = (
    ("recon", "recon"), ("shock", "shock"), ("owl", "drone"), ("drone", "drone"),
    ("hunter", "ult"), ("fury", "ult"), ("orbital", "ult"), ("ultimate", "ult"),
    ("smoke", "smoke"), ("cloud", "smoke"), ("screen", "wall"), ("wall", "wall"),
    ("snake", "molly"), ("molly", "molly"), ("incendiary", "molly"), ("fire", "molly"),
    ("flash", "flash"), ("trapwire", "trapwire"), ("cage", "cage"), ("camera", "camera"),
    ("spycam", "camera"),
    # ชื่อที่โผล่เพิ่มมาจาก ValCompanion — เทียบเท่าของเดิมที่เรามีแท็กอยู่แล้วเท่านั้น
    # ที่ไม่มีแท็กตรงกัน (Gravnet, Slow Orb ฯลฯ) ปล่อยให้คืน None ดีกว่าเดามั่วให้ผิด
    ("nanoswarm", "molly"), ("mosh", "molly"), ("hot hands", "molly"),
    ("blaze", "wall"), ("cove", "smoke"), ("dart", "recon"), ("bolt", "shock"),
    ("blindside", "flash"), ("curveball", "flash"), ("paranoia", "flash"),
    ("haunt", "recon"), ("prowler", "recon"), ("trailblazer", "recon"),
    # KAY/O — เว็บเขียน Zero_Point / Frag_Ment / Flash_Drive (flash จับได้จากคำเดิมอยู่แล้ว)
    ("zero", "knife"), ("frag", "molly"),
)


def ability_tag(name: str | None) -> str | None:
    """แปลงชื่อสกิลของเว็บเป็นแท็กสกิลของเรา — ไม่รู้จักก็คืน None (ไม่เดามั่วให้ผิดตัว)."""
    low = (name or "").lower()
    for word, tag in ABILITY_WORDS:
        if word in low:
            return tag
    # ชื่อสกิลตรงตัวของเกม (Arc Rose, Gravnet …) → แท็กจากไฟล์ไอคอนสกิล (browser._extend_from_icons)
    for word, tag in _game_names():
        if word in low:
            return tag
    return None


_GAME_NAMES: list[tuple[str, str]] | None = None


def _game_names() -> list[tuple[str, str]]:
    """(ชื่อสกิลตัวเล็ก, แท็ก) จาก assets/abilities/index.json — ชื่อยาวก่อน กันชื่อสั้นไปจับซ้อน."""
    global _GAME_NAMES
    if _GAME_NAMES is None:
        from lineupmaster.paths import ASSETS

        try:
            index = json.loads((ASSETS / "abilities" / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            index = {}
        pairs = {(item["name"].lower(), item["tag"]) for items in index.values() for item in items
                 if item.get("name") and item.get("tag")}
        _GAME_NAMES = sorted(pairs, key=lambda pair: -len(pair[0]))
    return _GAME_NAMES


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _cached_json(path: Path, force: bool, build: Callable[[], object]) -> object:
    """อ่านไฟล์แคช ถ้ายังไม่เก่าเกิน DATA_MAX_AGE — ไม่งั้นไปดึงใหม่แล้วเขียนทับ."""
    fresh = path.is_file() and (time.time() - path.stat().st_mtime) < DATA_MAX_AGE
    if not force and fresh:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    data = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


_ARROW = re.compile(r"→|->|→")


def _route(text: str | None) -> tuple[str | None, str | None]:
    """แตก "A Lobby → A Site" เป็นต้นทาง/ปลายทาง — ใช้เป็นทั้งตัวกรองและตัวปักหมุดอัตโนมัติ."""
    parts = [re.sub(r"\s+", " ", p).strip() for p in _ARROW.split(text or "")]
    if len(parts) != 2 or not all(parts):
        return None, None
    return parts[0], parts[1]


# ---------------------------------------------------------------- ValoLineups Pro

VLP_SITE = "https://valorantlineupspro.com"
VLP_DATA = f"{VLP_SITE}/data/lineups.json"
VLP_STEP = VLP_SITE + "/cdn/lineups/{id}/{step}"
VLP_CACHE = _CACHE_ROOT / "valolineups"      # ที่เดิม — ห้ามย้าย ไม่งั้นรูปที่โหลดไว้แล้วหาย


def _norm_vlp(row: dict) -> dict:
    """``s == 1`` คือฝั่งตั้งรับ และจุดเป็น A/B/C/MID (อ่านมาจาก app.js ของเว็บต้นทาง)."""
    site = str(row.get("st") or "").upper()
    frm, to = _route(row.get("d"))
    return {
        "uid": f"vlp:{row['i']}", "src": "vlp", "i": int(row["i"]),
        "t": row.get("t") or "", "a": row.get("a") or "", "m": row.get("m") or "",
        "side": "defense" if row.get("s") == 1 else "attack",
        "st": site if site.lower() in SITES else ("MID" if site == "MID" else ""),
        "ab": row.get("ab") or "", "n": max(1, int(row.get("n") or 1)),
        "from": frm, "to": to, "d": row.get("d") or "",
        "desc": "", "diff": "", "video": "",
    }


def _fetch_vlp(force: bool) -> list[dict]:
    def build() -> list[dict]:
        return json.loads(_get(VLP_DATA).decode("utf-8"))

    rows = _cached_json(VLP_CACHE / "lineups.json", force, build)
    return [_norm_vlp(r) for r in rows if r.get("i") is not None]


def _steps_vlp(entry: dict) -> list[str]:
    return [VLP_STEP.format(id=entry["i"], step=i + 1) for i in range(entry["n"])]


# ------------------------------------------------------------------ ValCompanion

VC_SITE = "https://valcompanion.com"
VC_LIST = VC_SITE + "/api/get_lineups.php?map_id={map_id}"
VC_CACHE = _CACHE_ROOT / "valcompanion"
VC_MAP_IDS = range(1, 21)                    # แมพที่ยังไม่มีข้อมูลจะคืนรายการว่าง ข้ามไปเอง

# จุด A/B/C เขาไม่ได้เก็บแยกไว้ (ฟิลด์ชื่อ site ของเขาคือ *ฝั่ง* บุก/รับ) เลยต้องอ่านจาก
# ชื่อ+คำอธิบายเอา — จับได้ราวครึ่งหนึ่ง ที่เหลือปล่อยว่างให้เลือกเองตอนเก็บ ดีกว่าเดาผิดจุด
_VC_SITE_WORDS = (r"site|main|lobby|long|short|heaven|hell|link|lane|market|window|garage|"
                  r"hookah|elbow|tower|cave|alley|ramp|stairs|default|back|front|boxes?|"
                  r"bath|screens|cubby|tree|generator|rafters|logs|nest|attic|yard|door|"
                  r"hall|dish|kitchen|tube|top|bottom|plant|rope|pit|drop|street|arcade")
_VC_SITE = re.compile(rf"\b([ABC])\s*[-–]?\s*(?:{_VC_SITE_WORDS})\b", re.I)
_VC_SITE_BARE = re.compile(r"(?:^|[\s(,])([ABC])(?:$|[\s),.])")


def _vc_site(text: str) -> str:
    found = _VC_SITE.search(text) or _VC_SITE_BARE.search(text)
    return found.group(1).upper() if found else ""


def _norm_vc(row: dict) -> dict:
    title = (row.get("title") or "").strip()
    desc = (row.get("description") or "").strip()
    # ชื่อมาในรูป "Astra – Gravity Well" เสมอ (ตรวจแล้วทั้ง 3,415 ใบที่สุ่มมา)
    ability = title.split("–")[-1].strip() if "–" in title else ""
    side = "defense" if str(row.get("site") or "").lower().startswith("def") else "attack"
    return {
        "uid": f"vc:{row['id']}", "src": "vc", "i": int(row["id"]),
        "t": title, "a": (row.get("agent_name") or "").lower(),
        "m": (row.get("map_name") or "").lower(),
        "side": side, "st": _vc_site(f"{title} {desc}"),
        "ab": ability, "n": 1,
        # เขาไม่ได้บอกโซนต้นทาง/ปลายทาง ⇒ ปักหมุดอัตโนมัติให้ไม่ได้ ต้องจิ้มเอง
        "from": None, "to": None, "d": "",
        "desc": desc, "diff": (row.get("difficulty") or "").strip(),
        "video": row.get("youtube_url") or "",
        "img": row.get("image_url") or "",
        "thumb": row.get("thumb_path") or row.get("image_url") or "",
    }


def _fetch_vc(force: bool) -> list[dict]:
    def build() -> list[dict]:
        out: list[dict] = []
        for map_id in VC_MAP_IDS:
            try:
                data = json.loads(_get(VC_LIST.format(map_id=map_id)).decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                continue
            out.extend(data.get("lineups") or [])
            time.sleep(POLITE_GAP)
        return out

    rows = _cached_json(VC_CACHE / "lineups.json", force, build)
    return [_norm_vc(r) for r in rows if r.get("id") is not None]


def _steps_vc(entry: dict) -> list[str]:
    return [entry["img"]] if entry.get("img") else []


# ------------------------------------------------------------------- tracker.gg
#
# tracker.gg ตอบ 403 ให้ทุกอย่างที่ไม่ใช่เบราว์เซอร์จริง (กันบอต) — **ห้ามพยายามเลี่ยง** รายการจึงโหลดเองจาก
# Python ไม่ได้ ต้องให้ผู้ใช้กด bookmarklet "ส่งเข้า LineupMaster" บนหน้า tracker.gg ของตัวเอง แล้วมันดึงรายการ
# ในเบราว์เซอร์นั้นส่งมาที่เซิร์ฟเวอร์หน้าจัดการ (tools/web_manage.py · /api/tracker/push) → เก็บเป็นไฟล์ใน
# ``.cache/tracker/guides-<ตัวละคร>.json`` (ของดิบจากเว็บ) ตัวนี้แค่อ่านไฟล์พวกนั้นมาแปลงเป็นรูปแบบกลาง
# วิดีโอ = Cloudflare Stream (HLS ~360p ยาว 10-30 วิ) ไม่มีรูปทีละขั้น จึงมี ``n = 0`` และ ``video`` เป็นรหัสสตรีม

TG_SITE = "https://tracker.gg"
TG_CACHE = _CACHE_ROOT / "tracker"
TG_STREAM = "https://customer-9h7e8ahl6hivmjb6.cloudflarestream.com/{id}/manifest/video.m3u8"


def tg_stream_url(video_id: str) -> str:
    return TG_STREAM.format(id=video_id)


def tg_key() -> str:
    """รหัสลับถาวรที่ฝังใน bookmarklet — สุ่มครั้งแรกแล้วจำไว้ใน ``.cache/tracker/key.txt``.

    เว็บอื่นในเครื่องผู้ใช้ยิงเข้ามาที่เซิร์ฟเวอร์ไม่ได้ถ้าไม่รู้รหัสนี้ (รหัสหน้าเว็บ ``?t=`` เปลี่ยนทุกรอบ
    เลยใช้ฝังใน bookmarklet ไม่ได้ — ผู้ใช้ต้องมาติดตั้งใหม่ทุกครั้งที่เปิดโปรแกรม)
    """
    path = TG_CACHE / "key.txt"
    try:
        found = path.read_text(encoding="utf-8").strip()
        if len(found) >= 16:
            return found
    except OSError:
        pass
    import secrets

    key = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key, encoding="utf-8")
    return key


_TG_KEEP = ("id", "urlSlug", "title", "description", "videoUrl", "previewImageUrl", "score", "views",
            "dateCreated")
_TG_ATTRS = ("map", "agent", "ability", "side", "location")


def tg_clean(row: object) -> dict | None:
    """เก็บเฉพาะฟิลด์ที่ใช้ (ข้อมูลมาจากเบราว์เซอร์ ไม่เชื่อรูปร่างมัน) — ไม่มี id/วิดีโอก็ทิ้ง."""
    if not isinstance(row, dict) or row.get("id") is None or not row.get("videoUrl"):
        return None
    out: dict = {}
    for name in _TG_KEEP:
        value = row.get(name)
        out[name] = value if isinstance(value, (int, float)) else str(value)[:2000] if value is not None else None
    attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
    out["attributes"] = {name: str(attrs[name])[:100] for name in _TG_ATTRS if attrs.get(name) is not None}
    return out


def tg_slug(agent: str) -> str:
    """ชื่อตัวละคร → ชื่อไฟล์ปลอดภัย (ผู้ส่งเป็นเบราว์เซอร์ ห้ามเชื่อชื่อไฟล์ตรงๆ)."""
    return re.sub(r"[^a-z0-9]+", "-", str(agent or "").lower()).strip("-")[:32]


def tg_store(agent: str, items: list) -> int:
    """เก็บรายการของตัวละครนี้ (ทับของเดิมทั้งชุด — bookmarklet ส่งมาครบทุกหน้าเสมอ) · คืนจำนวนที่เก็บ."""
    slug = tg_slug(agent)
    if not slug:
        raise ValueError("ไม่รู้ว่าเป็นตัวละครไหน")
    items = [row for row in map(tg_clean, items) if row]
    if not items:
        raise ValueError("ไม่มีไลน์อัพที่มีวิดีโอในข้อมูลที่ส่งมา")
    path = TG_CACHE / f"guides-{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps({"agent": slug, "saved": int(time.time()), "items": items},
                               ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    return len(items)


def tg_status() -> list[dict]:
    """ตัวละครที่เคยส่งเข้ามา + จำนวน + เวลาที่ส่งล่าสุด — ไว้โชว์ในหน้าตั้งค่า."""
    out = []
    for path in sorted(TG_CACHE.glob("guides-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append({"agent": data.get("agent") or path.stem[7:], "count": len(data.get("items") or []),
                        "saved": int(data.get("saved") or 0)})
        except (OSError, ValueError):
            continue
    return out


def _tg_xy(raw: object) -> tuple[float, float] | None:
    """"x,y" ของเว็บเอง (คนละสเกลกับแผนที่เรา — ยังไม่แปลง) · "-1,-1" = ไม่มี."""
    try:
        x, y = (float(v) for v in str(raw).split(","))
    except ValueError:
        return None
    return None if x < 0 or y < 0 else (x, y)


def _norm_tg(row: dict) -> dict | None:
    attrs = row.get("attributes") or {}
    video = str(row.get("videoUrl") or "").strip()
    if row.get("id") is None or not video:
        return None
    title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()
    desc = str(row.get("description") or "").strip()
    side = str(attrs.get("side") or "all").lower()
    ability = str(attrs.get("ability") or "").strip()
    return {
        "uid": f"tg:{row['id']}", "src": "tg", "i": row["id"],
        "t": title, "a": str(attrs.get("agent") or "").lower(),
        "m": str(attrs.get("map") or "").lower(),
        # "all" = ใช้ได้ทั้งสองฝั่ง — ฝั่งหลักตั้งเป็นบุก ส่วน ``both`` ให้ตัวกรองฝั่งนับเข้าทั้งสองฝั่ง
        "side": "defense" if side.startswith("def") else "attack", "both": side not in ("attack", "defense"),
        "st": _vc_site(title),                       # A/B/C เดาจากชื่อ — ไม่เจอก็ว่างให้เลือกเอง
        "ab": ability, "n": 0, "from": None, "to": None, "d": "",
        "desc": desc, "diff": "", "video": video,
        "thumb": row.get("previewImageUrl") or "",
        "xy": _tg_xy(attrs.get("location")),
        "score": row.get("score"), "views": row.get("views"),
    }


def _fetch_tg(force: bool) -> list[dict]:
    """อ่านไฟล์ที่ bookmarklet ส่งมา — ไม่ต่อเน็ต (``force`` ไม่มีผล)."""
    out: list[dict] = []
    seen: set[str] = set()
    for path in sorted(TG_CACHE.glob("guides-*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8")).get("items") or []
        except (OSError, ValueError):
            continue
        for row in rows:
            entry = _norm_tg(row) if isinstance(row, dict) else None
            if entry and entry["uid"] not in seen:
                seen.add(entry["uid"])
                out.append(entry)
    return out


def _steps_tg(entry: dict) -> list[str]:
    return []                                # มีแต่วิดีโอ ไม่มีรูปทีละขั้น


# --------------------------------------------------------------------- ทะเบียน


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    site: str
    cache: Path
    fetch: Callable[[bool], list[dict]]
    steps: Callable[[dict], list[str]]
    #: รูปย่อสำเร็จรูปของเว็บนั้น — ไม่มีก็คืน None แล้วเราย่อจากขั้นที่ 1 เอง
    thumb: Callable[[dict], str | None] = lambda entry: entry.get("thumb") or None


SOURCES: dict[str, Source] = {
    "vlp": Source("vlp", "ValoLineups Pro", VLP_SITE, VLP_CACHE, _fetch_vlp, _steps_vlp,
                  lambda entry: None),
    "vc": Source("vc", "ValCompanion", VC_SITE, VC_CACHE, _fetch_vc, _steps_vc),
    "tg": Source("tg", "tracker.gg", TG_SITE, TG_CACHE, _fetch_tg, _steps_tg),
}
DEFAULT_SOURCES = tuple(SOURCES)


def fetch_catalog(force: bool = False, sources: tuple[str, ...] = DEFAULT_SOURCES) -> list[dict]:
    """รายการไลน์อัพจากทุกแหล่งที่ขอ — แหล่งไหนล่มก็ข้ามไป ไม่ให้พังทั้งหน้า."""
    out: list[dict] = []
    for key in sources:
        source = SOURCES.get(key)
        if source is None:
            continue
        try:
            out.extend(source.fetch(force))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    return out


# ----------------------------------------------------------- ไฟล์รูปที่โหลดมาพัก


def split_uid(uid: str) -> tuple[str, int]:
    key, _, number = str(uid).partition(":")
    if not number:                            # ของเดิมที่เก็บเป็นเลขล้วน = ValoLineups Pro
        key, number = "vlp", key
    return key, int(number)


def _suffix(url: str) -> str:
    tail = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return tail if tail in {".webp", ".png", ".jpg", ".jpeg"} else ".webp"


def step_paths(entry: dict) -> list[Path]:
    source = SOURCES[entry["src"]]
    folder = source.cache / str(entry["i"])
    return [folder / f"{i + 1}{_suffix(url)}" for i, url in enumerate(source.steps(entry))]


def is_cached(entry: dict) -> bool:
    paths = step_paths(entry)
    return bool(paths) and all(p.is_file() and p.stat().st_size > 0 for p in paths)


def download(entry: dict) -> list[Path]:
    """โหลดรูปทุกขั้นมาพักไว้ (ข้ามอันที่มีแล้ว) — หน่วงระหว่างรูปไม่ให้ยิงถี่ใส่เว็บเขา."""
    source = SOURCES[entry["src"]]
    urls = source.steps(entry)
    paths = step_paths(entry)
    if paths:
        paths[0].parent.mkdir(parents=True, exist_ok=True)
    for url, target in zip(urls, paths):
        if target.is_file() and target.stat().st_size > 0:
            continue
        target.write_bytes(_get(url))
        time.sleep(POLITE_GAP)
    return paths


# ------------------------------------------------------- จำว่าเอา/ไม่เอาใบไหนแล้ว


def read_decisions(path: Path | None = None) -> dict:
    """อ่าน browse.json — แปลงรหัสเลขล้วนของเดิมเป็น ``vlp:<เลข>`` ให้อัตโนมัติ.

    ``path`` = อ่านจากไฟล์อื่นแทน ``STATE`` (ที่ผูกกับ ROOT ตอน import) — ตัวคัดใบซ้ำส่ง path ของคลังมาเอง
    """
    try:
        data = json.loads((path or STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    raw_taken = data.get("taken") if isinstance(data.get("taken"), dict) else {}
    raw_skipped = data.get("skipped") if isinstance(data.get("skipped"), list) else []

    def fix(value: object) -> str:
        text = str(value)
        return text if ":" in text else f"vlp:{text}"

    return {"taken": {fix(k): v for k, v in raw_taken.items()},
            "skipped": sorted({fix(v) for v in raw_skipped})}


def write_decisions(data: dict) -> None:
    try:
        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass

"""เสียงพูดภาษาไทย — บอกชื่อไลน์อัพ/วิธียิง/สถานะ โดยไม่ต้องละสายตาจากเกม.

เสียงมาจาก edge-tts (เสียง Premwadee ของ Microsoft) สร้างเป็น mp3 เก็บไว้ที่
``<ROOT>/.cache/voice/`` ประโยคละไฟล์ — ชื่อไฟล์คือแฮชของ (เสียง, ความเร็ว, ข้อความ)
ประโยคที่เคยสร้างแล้วจึงไม่สร้างซ้ำ · ตอนเล่นเปิดไฟล์ในเครื่องทันที ไม่ต้องต่อเน็ต
เจอประโยคใหม่ที่ยังไม่มีไฟล์ = สร้างเบื้องหลังแล้วพูดตาม (ต้องมีเน็ต ช้าราว 1 วินาที)
หน้าตั้งค่ามีปุ่ม "สร้างเสียงล่วงหน้า" ทำไฟล์ของทุกใบในคลังไว้ก่อนเล่น (ดู ``phrases``)

เล่นเสียงด้วย MCI ของ Windows (winmm) — ไม่ต้องพ่วง QtMultimedia + ffmpeg เข้า exe
ทุกคำสั่ง MCI อยู่ในเธรดเดียว (``Voice._run``) เพราะ alias ของ MCI ผูกกับเธรดที่เปิดมัน

ส่วนบน (แปลงไลน์อัพ/ข้อความสถานะเป็นประโยคพูด) เป็นฟังก์ชันล้วน ทดสอบได้ไม่ต้องมีเสียง
"""

from __future__ import annotations

import hashlib
import queue
import re
import sys
import threading
import time
from pathlib import Path

VOICE = "th-TH-PremwadeeNeural"
# เสียงสำรอง — Premwadee ไม่เสถียรจากฝั่งบริการ (บางช่วงปฏิเสธเกือบทุกประโยค วัดจริง 28/09/2026)
# ส่วน Niwat ผ่านทุกครั้ง · ใช้แทนชั่วคราวให้ในเกมยังมีเสียง แล้วปุ่ม "สร้างเสียง" ลอง Premwadee ใหม่
FALLBACK = "th-TH-NiwatNeural"
DEFAULTS = {"enabled": True, "rate": -15, "volume": 80, "notes": True, "status": True, "zone": True}

SIDE_SPOKEN = {"attack": "ฝั่งบุก", "defense": "ฝั่งตั้งรับ"}

# ประโยคตายตัวที่พูดบ่อย — สร้างล่วงหน้าไปพร้อมชื่อไลน์อัพ จะได้ไม่ต้องรอเน็ตตอนกด
FIXED = ("แจ้งผิดแล้ว", "เอาธงออกแล้ว", "ใช้ได้จริง", "ถอนโหวตแล้ว")
SAMPLE = "รีคอน. A Lobby ไป A Front. ชาร์จสองขีด เด้งหนึ่งครั้ง"   # ปุ่ม "ทดลองฟัง" ในหน้าตั้งค่า
# ข้อความสถานะที่โปรแกรมหลักสร้างเสียงเองระหว่างเล่น (เช่น "ไม่มีหมุดเลข 5") — จดไว้ให้ prune
# รู้ว่าเป็นของที่ยังใช้อยู่ ไม่ใช่ขยะ · บรรทัดละ "<ความเร็ว>\t<ข้อความ>"
EXTRA = "status.txt"


# ======================================================================
#  ข้อความ → ประโยคพูด
# ======================================================================
def spoken_route(stem: str) -> str:
    """ชื่อไฟล์ → ประโยคที่ฟังรู้เรื่อง: ``A Lobby to A Front (anti-cypher) #2``
    → ``A Lobby ไป A Front, anti-cypher, แบบที่ 2``."""
    text = stem
    dup = re.search(r"\s*#\s*(\d+)\s*$", text)
    if dup:
        text = text[: dup.start()]
    text = re.sub(r"\s+to\s+", " ไป ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfrom\s+", "จาก ", text, flags=re.IGNORECASE)
    text = text.replace("→", " ไป ").replace("->", " ไป ")
    text = re.sub(r"\s*[(\[]\s*", ", ", text)
    text = re.sub(r"\s*[)\]]\s*", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if dup:
        text = f"{text}, แบบที่ {dup.group(1)}"
    return text


def spoken_lineup(lu, ability_th: dict[str, str], with_note: bool = True) -> str:
    """สกิล + เส้นทาง (+ วิธียิง ``howto`` ถ้ามีและเปิดไว้).

    อ่าน ``howto`` ไม่ใช่ ``note`` — note คือชื่อที่โชว์บนจอแทนชื่อไฟล์ อ่านซ้ำก็คือพูดชื่อสองรอบ
    """
    parts = []
    route = spoken_route(lu.stem)
    if lu.ability:
        name = ability_th.get(lu.ability, lu.ability)
        parts.append(name)
        # ชื่อไฟล์หลายใบมีชื่อสกิลในวงเล็บอยู่แล้ว เช่น "(มีด)" — ไม่พูดซ้ำสองรอบ
        route = ", ".join(bit for bit in route.split(", ") if bit.strip() != name)
    parts.append(route)
    howto = (getattr(lu, "howto", "") or "").strip()
    if with_note and howto:
        parts.append(re.sub(r"\s+", " ", howto))
    return ". ".join(p for p in parts if p)


def spoken_place(map_: str | None, side: str | None) -> str:
    return f"{(map_ or '').capitalize()} {SIDE_SPOKEN.get(side or '', '')}".strip()


def spoken_zone(zone: str, targets: list[str]) -> str:
    """เดินเข้าโซนแล้วบอกว่ายิงไปไหนได้บ้าง — เกิน 4 จุดพูดแค่ 3 จุดแรก (ใกล้ก่อน) ที่เหลือบอกจำนวน."""
    if not targets:
        return f"ตอนนี้อยู่ {zone} แถวนี้ยังไม่มีไลน์อัพ"
    said = targets if len(targets) <= 4 else targets[:3]
    places = said[0] if len(said) == 1 else f"{', '.join(said[:-1])} กับ {said[-1]}"
    more = f" และอีก {len(targets) - len(said)} จุด" if len(said) < len(targets) else ""
    return f"ตอนนี้อยู่ {zone} มีไลน์อัพ {len(targets)} จุด ยิงไป {places}{more} ได้"


def spoken_status(note: str) -> str:
    """ข้อความสถานะบนจอ → ประโยคสั้น: ตัดคำแนะนำท้าย (หลัง —) สัญลักษณ์ และตัวคั่น."""
    text = re.split(r"\s+—\s+|\s{2,}·\s{2,}|\s+│\s+", note, maxsplit=1)[0]
    text = re.sub(r"[⚑✓✗⭐★│]", " ", text)
    text = text.replace("/", " หรือ ").replace(":", " ")
    return re.sub(r"\s+", " ", text).strip()


def phrases(lineups, ability_th: dict[str, str], with_note: bool = True) -> list[str]:
    """ทุกประโยคที่ควรมีเสียงไว้ก่อนเล่น — ชื่อทุกใบ + แมพ×ฝั่ง + ประโยคตายตัว (ไม่ซ้ำ เรียงคงที่)."""
    out: dict[str, None] = {}
    for lu in lineups:
        out[spoken_lineup(lu, ability_th, with_note)] = None
    for map_ in sorted({lu.map for lu in lineups if lu.map}):
        for side in SIDE_SPOKEN:
            out[spoken_place(map_, side)] = None
    for text in FIXED:
        out[text] = None
    return [t for t in out if t]


# ======================================================================
#  ไฟล์เสียง
# ======================================================================
def clip_path(cache: Path, text: str, rate: int, voice: str = VOICE) -> Path:
    key = hashlib.sha1(f"{voice}|{rate:+d}|{text}".encode("utf-8")).hexdigest()[:20]
    return cache / f"{key}.mp3"


def _extra_texts(cache: Path, rate: int) -> set[str]:
    try:
        lines = (cache / EXTRA).read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {line.split("\t", 1)[1] for line in lines
            if "\t" in line and line.split("\t", 1)[0] == f"{rate:+d}"}


def prune(cache: Path, rate: int, texts: list[str]) -> tuple[int, int]:
    """ลบไฟล์เสียงที่ไม่ใช้แล้ว — คืน (จำนวนไฟล์, ไบต์ที่ได้คืน).

    ที่เก็บไว้: ประโยคของคลังตอนนี้ (``texts``) + ปุ่มทดลองฟัง + ข้อความสถานะที่โปรแกรมหลักเคย
    ใช้ (``EXTRA``) — ทั้งหมดที่ความเร็วปัจจุบัน · ที่เหลือคือเสียงของใบที่ลบ/เปลี่ยนชื่อไปแล้ว
    หรือของความเร็วเก่า ลบทิ้ง (สร้างใหม่ได้เสมอ ไม่ใช่ข้อมูลของผู้ใช้)
    """
    if not cache.is_dir():
        return 0, 0
    extra = _extra_texts(cache, rate)
    keep = {clip_path(cache, text, rate, voice).name
            for text in (*texts, SAMPLE, *extra) for voice in (VOICE, FALLBACK)}
    count = freed = 0
    now = time.time()
    for path in cache.iterdir():
        try:
            stale_part = path.name.endswith(".part") and now - path.stat().st_mtime > 600
            if (path.suffix == ".mp3" and path.name not in keep) or stale_part:
                size = path.stat().st_size
                path.unlink()
                count += 1
                freed += size
        except OSError:
            continue                        # กำลังเล่นอยู่ (ไฟล์ถูกล็อก) — รอบหน้าค่อยลบ
    if (cache / EXTRA).is_file():           # ข้อความสถานะของความเร็วเก่าไม่ต้องจำแล้ว
        try:
            (cache / EXTRA).write_text("".join(f"{rate:+d}\t{t}\n" for t in sorted(extra)),
                                       encoding="utf-8")
        except OSError:
            pass
    return count, freed


def synthesize(text: str, target: Path, rate: int, voice: str = VOICE, tries: int = 6) -> bool:
    """สร้าง mp3 ผ่าน edge-tts — เขียนไฟล์ชั่วคราวก่อนแล้วค่อยเปลี่ยนชื่อ (ไม่มีไฟล์ครึ่งๆ ค้าง).

    เสียง Premwadee ตอบว่างเปล่า (NoAudioReceived) แบบสุ่มราว 40% ของครั้ง ไม่ขึ้นกับข้อความหรือ
    ความเร็ว (วัดจริง 28/09/2026 · เสียง Niwat ไม่เป็น) — ลองซ้ำ 6 รอบ โอกาสพลาดหมดเหลือ <1%
    """
    import asyncio

    import edge_tts

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")

    async def run() -> None:
        await edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(str(temp))

    for attempt in range(tries):
        try:
            asyncio.run(run())
            if temp.is_file() and temp.stat().st_size > 0:
                temp.replace(target)
                return True
        except Exception as error:  # noqa: BLE001 - เน็ตหลุด/บริการปฏิเสธ ยกได้หลายแบบ
            if attempt == tries - 1:
                print(f"[voice] สร้างเสียงไม่สำเร็จ {tries} รอบ: {text!r} · {error}", file=sys.stderr)
        time.sleep(0.3)
    temp.unlink(missing_ok=True)
    return False


def ensure_clip(cache: Path, text: str, rate: int, tries: int = 3) -> Path | None:
    """ไฟล์เสียงของประโยคนี้ — เสียงหลักก่อน สร้างไม่ได้ใช้เสียงสำรอง (None = ไม่มีทั้งคู่ เน็ตหลุด)."""
    main = clip_path(cache, text, rate)
    if main.is_file() or synthesize(text, main, rate, tries=tries):
        return main
    backup = clip_path(cache, text, rate, FALLBACK)
    if backup.is_file() or synthesize(text, backup, rate, FALLBACK, tries=2):
        return backup
    return None


class _Mci:
    """เล่น mp3 ผ่าน MCI ของ Windows — พูดใหม่ = ตัดเสียงเก่าทิ้งทันที."""

    ALIAS = "lmvoice"

    def __init__(self) -> None:
        import ctypes

        self._send = ctypes.windll.winmm.mciSendStringW
        self._buffer = ctypes.create_unicode_buffer(128)

    def _cmd(self, command: str) -> int:
        return self._send(command, self._buffer, 127, 0)

    def play(self, path: Path, volume: int) -> None:
        self.stop()
        if self._cmd(f'open "{path}" type mpegvideo alias {self.ALIAS}'):
            return
        self._cmd(f"setaudio {self.ALIAS} volume to {max(0, min(100, volume)) * 10}")
        self._cmd(f"play {self.ALIAS}")

    def stop(self) -> None:
        self._cmd(f"close {self.ALIAS}")


class Voice:
    """ตัวพูด — ``say`` เรียกจากเธรดไหนก็ได้ (ไม่บล็อก) · ขอพูดรัวๆ = พูดแค่อันล่าสุด."""

    def __init__(self, cache: Path, options: dict | None = None) -> None:
        self.cache = cache
        self.options = dict(DEFAULTS)
        self.configure(options or {})
        self._queue: queue.Queue[tuple[str, bool] | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def configure(self, options: dict) -> None:
        for key in DEFAULTS:
            if key in options:
                self.options[key] = options[key]

    @property
    def enabled(self) -> bool:
        return bool(self.options["enabled"]) and sys.platform == "win32"

    def say(self, text: str, lineup: bool = False) -> None:
        """``lineup=False`` = ข้อความสถานะ — ถ้าต้องสร้างเสียงใหม่จะจดไว้ใน EXTRA ให้ prune ไม่ลบทิ้ง
        (ชื่อไลน์อัพไม่ต้องจด เพราะ prune คำนวณจากคลังตอนนั้นเองอยู่แล้ว)."""
        text = (text or "").strip()
        if not text or not self.enabled:
            return
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="voice", daemon=True)
            self._thread.start()
        self._queue.put((text, lineup))

    def close(self) -> None:
        if self._thread is not None:
            self._queue.put(None)

    def _run(self) -> None:
        player = _Mci()
        while True:
            item = self._queue.get()
            while not self._queue.empty():          # กดรัว = ข้ามไปอันล่าสุด
                item = self._queue.get()
            if item is None:
                player.stop()
                return
            text, lineup = item
            rate = int(self.options["rate"])
            path = clip_path(self.cache, text, rate)
            backup = clip_path(self.cache, text, rate, FALLBACK)
            if not path.is_file() and backup.is_file():
                path = backup                       # ระหว่างเกมไม่รอลองเสียงหลักซ้ำ — ปุ่มสร้างเสียงทำให้
            elif not path.is_file():
                path = ensure_clip(self.cache, text, rate)
                if path is None:
                    continue
                if not lineup:
                    try:
                        with (self.cache / EXTRA).open("a", encoding="utf-8") as out:
                            out.write(f"{rate:+d}\t{text}\n")
                    except OSError:
                        pass
            if not self._queue.empty():             # ระหว่างรอสร้างเสียง ผู้ใช้กดต่อไปแล้ว
                continue
            player.play(path, int(self.options["volume"]))

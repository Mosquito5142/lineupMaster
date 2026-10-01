"""นำเข้าไลน์อัพจากคลิป YouTube — ถอดเฟรมเฉพาะช่วงของท่านั้นมาให้เลือกทำเป็นรูปขั้นตอน.

ValoPlant (และคลิปสอนไลน์อัพทั่วไป) ให้ลิงก์ YouTube ที่ติดเวลาไว้ เช่น ``youtu.be/Qlbwecza9GI?t=376``
คลิปพวกนี้มักแบ่ง **chapter** ทีละท่า ("Alternative B Back Site Reveal (Attacker)") จึงรู้ช่วงเริ่ม-จบ
ชื่อท่า และฝั่งได้เอง · คลิปที่ไม่มี chapter ใช้ช่วง ``BEFORE`` วิก่อนถึง ``AFTER`` วิหลังเวลาในลิงก์

**ไม่โหลดทั้งคลิป** — คลิปสอน 10 นาทีที่ 720p ก็ราว 250 MB · ใช้ yt-dlp หาลิงก์ไฟล์วิดีโอตรงๆ แล้วให้
PyAV (ffmpeg) อ่านผ่าน ``_RangeReader`` ที่ขอทีละ 1 MB เฉพาะส่วนที่ต้องใช้ (ท่าละ ~10-20 MB)
ปล่อยให้ ffmpeg ขอไฟล์เองจะค้าง: มันขอแบบไม่มีจุดจบ แล้ว YouTube หน่วงคำขอแบบนั้นจนแทบไม่ขยับ

เฟรมเก็บใน ``<ROOT>/.cache/clips/<วิดีโอ>-<วินาทีเริ่ม>/`` พร้อม ``clip.json`` — เปิดลิงก์เดิมซ้ำไม่โหลดใหม่

> คลิปเป็นของคนทำคลิป — ถอดมาดูในเครื่องเพื่อซ้อมเอง ไม่ได้เอาไปแจกต่อ (โปรแกรมใช้คนเดียว)
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .index import is_animated  # noqa: F401 - ให้ฝั่งเรียกใช้จากที่เดียวกับตัวทำภาพเคลื่อนไหว

BEFORE, AFTER = 2.0, 20.0        # คลิปไม่มี chapter — เอากี่วิก่อน/หลังเวลาในลิงก์
STEP = 0.5                       # ถอดเฟรมทุกกี่วินาที
MAX_FRAMES = 80                  # chapter ยาวมาก = ถ่างระยะเฟรมออก ไม่ให้เกินนี้
HEIGHTS = (1080, 720)            # เลือกความละเอียดนี้ก่อน — 1080 อ่านแถบชาร์จ/ตัวเลขเล็กๆ ออก
# คลิปในเครื่องของหน้าทำวิดีโอ — 720p พอ (ผลลัพธ์กว้างแค่ 640) ไฟล์เล็ก โหลดไว
PROXY_HEIGHTS = (720, 1080)
PROXY_NAME = "proxy.mp4"
PROXY_DAYS = 30                  # ไม่ได้เปิดนานกว่านี้ ล้างทิ้งตอนเซิร์ฟเวอร์เริ่ม (แคชล้วน)
MOTION_FPS = 10                  # วัดการขยับกี่ครั้งต่อวิ (กราฟบนแถบเวลา)
# ภาพเคลื่อนไหวช่วงยิง (ดูในเกมด้วย numpad * หรือเล่นเองถ้าใบนั้นเป็นภาพเคลื่อนไหวล้วน)
# 12 ภาพ/วิ กล้องหมุนเร็วแล้วดูกระตุก (ผู้ใช้บอก 29/09/2026) จึงใช้ 20 · WebP เคลื่อนไหว 4 วิ ≈ 1 MB
GIF_WIDTH, GIF_FPS, GIF_MAX = 640, 20, 10.0
ANIM_QUALITY = 75
GIF_SPAN, GIF_LEAD = 4.0, 1.0     # ช่วงที่ "หาช่วงยิงให้" เลือก: ก่อนปล่อยลูก 1 วิ รวมยาว 4 วิ
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class Clip:
    vid: str
    title: str                   # ชื่อคลิป
    chapter: str                 # ชื่อท่า (chapter) — ไม่มีก็ว่าง
    start: float
    end: float
    folder: str
    frames: list[str] = field(default_factory=list)      # ชื่อไฟล์ในโฟลเดอร์ เรียงตามเวลา
    times: list[float] = field(default_factory=list)     # วินาทีในคลิปของแต่ละเฟรม
    subs: list[str] = field(default_factory=list)        # ซับไตเติลช่วงนี้ (ไว้ช่วยเขียนวิธียิง)
    side: str | None = None      # เดาจาก (Attacker)/(Defender)
    site: str | None = None      # เดาจากตัว A/B/C ในชื่อท่า
    map: str | None = None       # เดาจากชื่อคลิป/ท่า
    agent: str | None = None
    # --- หน้าทำวิดีโอ (open_video) — ใบที่ถอดเฟรมแบบเดิมไม่มีค่าพวกนี้ ---
    proxy_offset: float | None = None   # เวลาในคลิป = เวลาใน proxy.mp4 + ค่านี้
    fps: float = 30.0
    motion_times: list[float] = field(default_factory=list)   # ทุก 1/MOTION_FPS วิ
    motion: list[float] = field(default_factory=list)         # ภาพเปลี่ยนเท่าไหร่จากจุดก่อนหน้า
    coarse_times: list[float] = field(default_factory=list)   # ทุก STEP วิ — ไว้ให้ pick_throw
    coarse: list[float] = field(default_factory=list)
    plan: dict | None = None     # แผนตัดต่อที่บันทึกล่าสุด — เปิดลิงก์เดิมได้ค่าเดิมกลับมา

    @property
    def name(self) -> str:
        """ชื่อที่ใช้เก็บเข้าคลัง — ชื่อท่า ตัด (Attacker)/(Defender) ท้ายชื่อทิ้ง (เก็บเป็นฝั่งแล้ว)."""
        base = self.chapter or f"{self.title} {int(self.start)}s"
        return re.sub(r"\s*\((attackers?|defenders?)\)\s*$", "", base, flags=re.IGNORECASE).strip()

    def paths(self) -> list[Path]:
        return [Path(self.folder) / name for name in self.frames]


# ======================================================================
#  ลิงก์ + การเดา (ฟังก์ชันล้วน ทดสอบได้ไม่ต้องต่อเน็ต)
# ======================================================================
def parse_link(text: str) -> tuple[str, float]:
    """ลิงก์/รหัสวิดีโอ → (รหัส 11 ตัว, วินาทีเริ่ม) · รับ youtu.be, watch?v=, shorts/, embed/ และ t=6m16s."""
    text = text.strip()
    if VIDEO_ID.match(text):
        return text, 0.0
    url = urllib.parse.urlparse(text if "://" in text else f"https://{text}")
    query = urllib.parse.parse_qs(url.query)
    vid = ""
    if url.hostname and url.hostname.endswith("youtu.be"):
        vid = url.path.strip("/").split("/")[0]
    elif "v" in query:
        vid = query["v"][0]
    else:
        parts = [p for p in url.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            vid = parts[1]
    if not VIDEO_ID.match(vid or ""):
        raise ValueError("ไม่ใช่ลิงก์ YouTube — วางลิงก์ที่ได้จากปุ่มแชร์ (มี ?t= บอกเวลา)")
    stamp = (query.get("t") or query.get("start") or [""])[0] or url.fragment.removeprefix("t=")
    return vid, _seconds(stamp)


def _seconds(stamp: str) -> float:
    stamp = stamp.strip().lower()
    if not stamp:
        return 0.0
    if re.fullmatch(r"\d+(\.\d+)?s?", stamp):
        return float(stamp.rstrip("s"))
    total = 0.0
    for number, unit in re.findall(r"(\d+)([hms])", stamp):
        total += int(number) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def segment(chapters: list[dict] | None, t: float, duration: float | None) -> tuple[float, float, str]:
    """ช่วงของท่าที่ครอบเวลา ``t`` — (เริ่ม, จบ, ชื่อ chapter) · ไม่มี chapter ใช้ BEFORE/AFTER."""
    for chapter in chapters or []:
        start, end = float(chapter.get("start_time") or 0), float(chapter.get("end_time") or 0)
        if start <= t < end:
            return start, end, str(chapter.get("title") or "")
    start = max(0.0, t - BEFORE)
    end = t + AFTER if duration is None else min(float(duration), t + AFTER)
    return start, end, ""


def guess_side(text: str) -> str | None:
    low = text.lower()
    if re.search(r"\b(defen[dcs]\w*|retake|ct)\b", low):
        return "defense"
    if re.search(r"\b(attack\w*|t side|post.?plant|execute)\b", low):
        return "attack"
    return None


def guess_site(text: str) -> str | None:
    """ตัว A/B/C ตัวแรกที่ยืนเดี่ยวๆ ในชื่อท่า ("B Back Site Reveal" → b)."""
    found = re.search(r"(?<![A-Za-z])([ABC])(?![A-Za-z])", text)
    return found.group(1).lower() if found else None


def guess_key(text: str, table: dict) -> str | None:
    """เทียบชื่อในข้อความกับคีย์ของ aliases.yaml (maps/agents) — คำไหนโผล่ก่อนได้ก่อน."""
    low = f" {re.sub(r'[^a-z0-9]+', ' ', text.lower())} "
    best: tuple[int, str] | None = None
    for key, aliases in (table or {}).items():
        for word in [key, *(aliases or [])]:
            word = re.sub(r"[^a-z0-9]+", " ", str(word).lower()).strip()
            at = low.find(f" {word} ") if word else -1
            if at >= 0 and (best is None or at < best[0]):
                best = (at, key)
    return best[1] if best else None


# ======================================================================
#  โหลด + ถอดเฟรม
# ======================================================================
class _RangeReader(io.RawIOBase):
    """ไฟล์วิดีโอบนเน็ตที่ PyAV อ่านได้เหมือนไฟล์ในเครื่อง — ขอทีละก้อน (Range) เก็บก้อนที่เคยขอไว้."""

    BLOCK = 1 << 20
    RETRIES = 3

    def __init__(self, url: str, headers: dict, size: int,
                 refresh: Callable[[], tuple[str, dict]] | None = None) -> None:
        super().__init__()
        self.url, self.headers, self.size, self.pos = url, headers, size, 0
        self.refresh = refresh
        self._blocks: dict[int, bytes] = {}

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def _block(self, index: int) -> bytes:
        """ขอก้อนที่ ``index`` — YouTube ตอบ 403 กลางทางได้เป็นพักๆ (ลิงก์ไฟล์หมดอายุ/ถูกบล็อก
        เจอจริงใน exe 29/09/2026) จึงขอลิงก์ใหม่ผ่าน ``refresh`` แล้วอ่านต่อจากก้อนเดิม."""
        if index in self._blocks:
            return self._blocks[index]
        start = index * self.BLOCK
        end = min(self.size, start + self.BLOCK) - 1
        for attempt in range(self.RETRIES + 1):
            request = urllib.request.Request(self.url, headers={**self.headers, "Range": f"bytes={start}-{end}"})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    self._blocks[index] = response.read()
                return self._blocks[index]
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
                if attempt == self.RETRIES or self.refresh is None:
                    raise OSError(f"YouTube ไม่ให้โหลดวิดีโอต่อ ({error}) — ลองกดดึงเฟรมใหม่อีกครั้ง") from None
                time.sleep(1.0 + attempt)
                self.url, self.headers = self.refresh()
        raise AssertionError("unreachable")

    def readinto(self, buffer) -> int:
        if self.pos >= self.size:
            return 0
        index, offset = divmod(self.pos, self.BLOCK)
        data = self._block(index)[offset:offset + len(buffer)]
        buffer[:len(data)] = data
        self.pos += len(data)
        return len(data)


def _video_format(info: dict, heights: tuple[int, ...] = HEIGHTS) -> dict:
    """ไฟล์วิดีโอล้วน (ไม่มีเสียง) แบบ mp4/h264 ที่ขอเป็นช่วงได้ — ไม่เอา m3u8 (แบ่งเป็นชิ้นย่อย)."""
    usable = [f for f in info.get("formats") or []
              if f.get("vcodec", "none") != "none" and f.get("protocol") == "https"
              and f.get("ext") == "mp4" and str(f.get("vcodec", "")).startswith("avc")
              and (f.get("filesize") or f.get("filesize_approx"))]
    for height in heights:
        found = [f for f in usable if f.get("height") == height]
        if found:
            return found[-1]
    if usable:
        return max(usable, key=lambda f: f.get("height") or 0)
    raise OSError("คลิปนี้ไม่มีไฟล์วิดีโอแบบที่ถอดเฟรมได้ (อาจเป็นไลฟ์หรือถูกจำกัดสิทธิ์)")


def _subtitles(info: dict, start: float, end: float) -> list[str]:
    """ซับ (ของคนทำคลิป ไม่มีก็ใช้ซับอัตโนมัติ) เฉพาะช่วงนี้ — โหลดไม่ได้ก็ข้ามเงียบๆ ไม่ใช่เรื่องใหญ่."""
    for table in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
        tracks = table.get("en") or table.get("en-US") or next(iter(table.values()), None)
        url = next((t["url"] for t in tracks or [] if t.get("ext") == "json3"), None)
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                events = json.loads(response.read().decode("utf-8")).get("events") or []
        except (OSError, ValueError):
            return []
        lines = []
        for event in events:
            at = (event.get("tStartMs") or 0) / 1000
            text = "".join(seg.get("utf8", "") for seg in event.get("segs") or []).strip()
            if start <= at <= end and text and (not lines or lines[-1] != text):
                lines.append(text)
        return lines
    return []


def _save_frame(frame, target: Path) -> None:
    from PySide6.QtGui import QImage

    rgb = frame.reformat(format="rgb24")
    plane = rgb.planes[0]
    image = QImage(bytes(plane), rgb.width, rgb.height, plane.line_size, QImage.Format.Format_RGB888)
    if not image.save(str(target), "JPG", 90):
        raise OSError(f"เซฟเฟรมไม่สำเร็จ: {target.name}")


def _fetch_info(vid: str) -> dict:
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except yt_dlp.utils.DownloadError as error:
        raise OSError(f"เปิดคลิปไม่ได้: {str(error).split(':')[-1].strip()}") from None


def _decode(vid: str, info: dict, start: float, end: float, step: float):
    """เฟรม (av.VideoFrame, วินาที) ทุก ``step`` วิในช่วง start..end — อ่านผ่าน _RangeReader."""
    import av

    reader = _reader(vid, _video_format(info))
    with av.open(io.BufferedReader(reader, 1 << 20)) as container:
        stream = container.streams.video[0]
        container.seek(int(start / stream.time_base), stream=stream, backward=True)
        wanted = start
        for frame in container.decode(stream):
            at = float(frame.pts * stream.time_base)
            if at < wanted:
                continue
            if at > end:
                break
            yield frame, at
            wanted += step


def _reader(vid: str, fmt: dict) -> _RangeReader:
    """ตัวอ่านไฟล์วิดีโอ ``fmt`` ของคลิปนี้บนเน็ต — ลิงก์หมดอายุกลางทางก็ขอใหม่ให้เอง."""

    def refresh() -> tuple[str, dict]:
        """ลิงก์ไฟล์ใหม่ของ **ไฟล์เดิม** (format เดียวกัน ขนาดเท่าเดิม ตำแหน่งไบต์จึงใช้ต่อได้)."""
        again = next((f for f in _fetch_info(vid).get("formats") or []
                      if f.get("format_id") == fmt.get("format_id")), None)
        if again is None:
            raise OSError("YouTube เปลี่ยนไฟล์วิดีโอไปแล้ว — ลองกดดึงเฟรมใหม่อีกครั้ง")
        return again["url"], again.get("http_headers") or {}

    return _RangeReader(fmt["url"], fmt.get("http_headers") or {},
                        int(fmt.get("filesize") or fmt.get("filesize_approx")), refresh)


def load(link: str, root: Path, aliases: dict | None = None,
         progress: Callable[[str], None] | None = None) -> Clip:
    """ลิงก์ → เฟรมของท่านั้น (ใช้ของที่เคยถอดไว้ถ้ามี) · ยก ``ValueError``/``OSError`` เป็นภาษาไทย."""
    say = progress or (lambda _text: None)
    vid, t = parse_link(link)
    aliases = aliases or {}

    say("กำลังอ่านข้อมูลคลิป…")
    info = _fetch_info(vid)

    start, end, chapter = segment(info.get("chapters"), t, info.get("duration"))
    folder = root / ".cache" / "clips" / f"{vid}-{int(start)}"
    old = _read_cached(folder)
    # เปิดผ่านหน้าทำวิดีโอมาก่อน = มี clip.json แต่ไม่มีเฟรม — ต้องถอดเฟรมเพิ่ม (เก็บค่าอื่นไว้)
    if old is not None and old.frames and all(path.is_file() for path in old.paths()):
        return old
    clip = old or _new_clip(vid, info, start, end, chapter, folder, aliases)
    clip.frames, clip.times = [], []

    step = max(STEP, (end - start) / MAX_FRAMES)
    folder.mkdir(parents=True, exist_ok=True)
    say(f"กำลังถอดเฟรม {chapter or 'ช่วงนี้'} ({int(end - start)} วินาที)…")
    for frame, at in _decode(vid, info, start, end, step):
        name = f"f{len(clip.frames):03d}.jpg"
        _save_frame(frame, folder / name)
        clip.frames.append(name)
        clip.times.append(round(at, 2))
    if not clip.frames:
        raise OSError("ถอดเฟรมไม่ได้สักเฟรม — ลองลิงก์ใหม่อีกครั้ง")
    clip.subs = _subtitles(info, start, end)
    save_clip(clip)
    return clip


def _read_cached(folder: Path) -> Clip | None:
    try:
        data = json.loads((folder / "clip.json").read_text(encoding="utf-8"))
        return Clip(**{**data, "folder": str(folder)})
    except (OSError, ValueError, TypeError):
        return None


def _new_clip(vid: str, info: dict, start: float, end: float, chapter: str,
              folder: Path, aliases: dict) -> Clip:
    title = str(info.get("title") or vid)
    text = f"{title} {chapter}"
    return Clip(vid=vid, title=title, chapter=chapter, start=start, end=end, folder=str(folder),
                side=guess_side(chapter) or guess_side(title), site=guess_site(chapter),
                map=guess_key(text, aliases.get("maps") or {}),
                agent=guess_key(text, aliases.get("agents") or {}))


def save_clip(clip: Clip) -> None:
    """จด ``clip.json`` (ทุกอย่างยกเว้นที่อยู่โฟลเดอร์ — ย้ายเครื่อง/โฟลเดอร์แล้วยังใช้ได้)."""
    data = asdict(clip)
    data.pop("folder")
    folder = Path(clip.folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "clip.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ======================================================================
#  หน้าทำวิดีโอ — คลิปช่วงนี้เก็บในเครื่อง (proxy.mp4) + วัดการขยับ
# ======================================================================
def proxy_path(clip: Clip) -> Path:
    return Path(clip.folder) / PROXY_NAME


def _remux(source, target: Path, start: float, end: float) -> float:
    """คัดลอกวิดีโอช่วง start..end จาก ``source`` (ไฟล์/ตัวอ่าน) ลง mp4 **โดยไม่แปลงใหม่** — เร็วและชัดเท่าต้นฉบับ.

    เริ่มได้แค่ที่คีย์เฟรมก่อน ``start`` เลยเลื่อนเวลาให้ไฟล์ใหม่เริ่มที่ 0 แล้วคืน "เวลาในต้นฉบับ
    ของวินาทีที่ 0" ไว้แปลงกลับ · เขียนลง ``.part`` ก่อน เสร็จแล้วค่อยเปลี่ยนชื่อ (พังกลางทางไม่ถูกใช้)
    """
    import av

    temp = target.with_name(target.name + ".part")
    base = None
    with av.open(source) as src:
        stream = src.streams.video[0]
        tb = stream.time_base
        src.seek(int(start / tb), stream=stream, backward=True)
        with av.open(str(temp), "w", format="mp4", options={"movflags": "+faststart"}) as out:
            dst = out.add_stream_from_template(stream)
            for packet in src.demux(stream):
                if packet.dts is None:
                    continue
                if base is None:
                    base = packet.dts
                if float(packet.dts * tb) > end + 0.5:
                    break
                packet.dts -= base
                if packet.pts is not None:
                    packet.pts -= base
                packet.stream = dst
                out.mux(packet)
    if base is None:
        temp.unlink(missing_ok=True)
        raise OSError("ตัดคลิปช่วงนี้ไม่ได้ — ลองใหม่อีกครั้ง")
    temp.replace(target)
    return round(float(base * tb), 6)


def _gray(frame) -> bytes:
    """เฟรมย่อ 64×36 ขาวดำ — ไว้เทียบว่าภาพขยับแค่ไหน."""
    small = frame.reformat(width=64, height=36, format="gray")
    plane = small.planes[0]
    raw = bytes(plane)
    return b"".join(raw[row * plane.line_size:row * plane.line_size + 64] for row in range(36))


def _diff(one: bytes, two: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(one, two)) / max(1, len(one))


def measure(clip: Clip) -> None:
    """วัดการขยับจาก proxy.mp4 ในเครื่อง (ไม่ต่อเน็ต) → กราฟบนแถบเวลา + ข้อมูลให้ ✨ หาช่วง."""
    import av

    offset = float(clip.proxy_offset or 0.0)
    times, shots = [], []
    with av.open(str(proxy_path(clip))) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if stream.average_rate:
            clip.fps = round(float(stream.average_rate), 3)
        wanted = clip.start
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            at = float(frame.pts * stream.time_base) + offset
            if at < wanted - 1e-6:
                continue
            if at > clip.end:
                break
            times.append(round(at, 3))
            shots.append(_gray(frame))
            wanted += 1 / MOTION_FPS
    clip.motion_times = times
    clip.motion = [0.0, *(round(_diff(a, b), 2) for a, b in zip(shots, shots[1:]))] if shots else []
    every = max(1, round(STEP * MOTION_FPS))
    picks = list(range(0, len(shots), every))
    clip.coarse_times = [times[i] for i in picks]
    clip.coarse = [round(_diff(shots[i], shots[j]), 2) for i, j in zip(picks, picks[1:])]


def open_video(link: str, root: Path, aliases: dict | None = None,
               progress: Callable[[str], None] | None = None) -> Clip:
    """ลิงก์ → คลิปช่วงของท่านั้นในเครื่อง + การขยับ (ใช้ของเดิมถ้าเคยเปิดแล้ว)."""
    say = progress or (lambda _text: None)
    vid, t = parse_link(link)
    say("กำลังอ่านข้อมูลคลิป…")
    info = _fetch_info(vid)
    start, end, chapter = segment(info.get("chapters"), t, info.get("duration"))
    folder = root / ".cache" / "clips" / f"{vid}-{int(start)}"
    clip = _read_cached(folder) or _new_clip(vid, info, start, end, chapter, folder, aliases or {})
    proxy = proxy_path(clip)
    if not proxy.is_file() or clip.proxy_offset is None:
        say(f"กำลังโหลดคลิป {chapter or 'ช่วงนี้'} ({int(end - start)} วินาที)…")
        folder.mkdir(parents=True, exist_ok=True)
        reader = _reader(vid, _video_format(info, PROXY_HEIGHTS))
        clip.proxy_offset = _remux(io.BufferedReader(reader, 1 << 20), proxy, start, end)
        clip.motion_times = []
        if not clip.subs:
            clip.subs = _subtitles(info, start, end)
    if not clip.motion_times:
        measure(clip)
    save_clip(clip)
    proxy.touch()                    # นับเป็น "เพิ่งใช้" — ไม่โดนล้างตอนครบ 30 วัน
    return clip


def video_plan(clip: Clip) -> dict:
    """แผนที่บันทึกไว้ หรือแผนที่เดาให้จากการขยับของท่านี้."""
    if clip.plan:
        try:
            return clean_plan(clip.plan)
        except (KeyError, TypeError, ValueError):
            pass
    return suggest_plan(clip.coarse_times, clip.coarse, clip.start, clip.end)


def prune_proxies(root: Path, days: int = PROXY_DAYS) -> int:
    """ล้าง proxy.mp4 ที่ไม่ได้เปิดนานเกิน ``days`` วัน (และ .part ที่ค้างเกินชั่วโมง) — แคชล้วน ไม่ใช่ไลน์อัพ."""
    now = time.time()
    removed = 0
    for path in (root / ".cache" / "clips").glob(f"*/{PROXY_NAME}*"):
        try:
            age = now - path.stat().st_mtime
            if age > days * 86400 or (path.suffix == ".part" and age > 3600):
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def gif_path(clip: Clip, start: float, end: float) -> Path:
    """ไฟล์ภาพเคลื่อนไหวของช่วงนี้ในโฟลเดอร์คลิป — ชื่อมีค่าตั้ง (fps/คุณภาพ) เปลี่ยนค่าแล้วทำใหม่เอง."""
    return Path(clip.folder) / f"anim-{start:.2f}-{end:.2f}-{GIF_FPS}fps-q{ANIM_QUALITY}.webp"


def make_gif(clip: Clip, start: float, end: float) -> Path:
    """ภาพเคลื่อนไหวช่วงยิง start..end (วินาทีในคลิป) เป็น **WebP เคลื่อนไหว** — ทำครั้งเดียวแล้วเก็บไว้.

    เดิมทำเป็น GIF จริง (256 สี) ได้ 4.7 MB ต่อ 4 วิ · WebP เคลื่อนไหวคุณภาพ 75 ได้ ~1 MB สีสวยกว่า
    (วัดจริง 29/09/2026) ตัวเล่นในเกม (QMovie) และเบราว์เซอร์เปิดได้ทั้งคู่ · ยาวเกิน ``GIF_MAX`` ตัดท้าย

    ไฟล์พ่วงของรูปนิ่งยังตั้งชื่อ ``<ชื่อ>.gif`` เหมือนเดิม (ระบบจับคู่/ย้าย/รวมคลังรู้จักชื่อนี้อยู่แล้ว)
    แค่ข้างในเป็น WebP — Qt กับเบราว์เซอร์ดูชนิดไฟล์จากเนื้อไฟล์ ไม่ได้ดูจากนามสกุล
    """
    start, end = sorted((float(start), float(end)))
    end = min(end, start + GIF_MAX)
    if end - start < 0.3:
        raise ValueError("ช่วงภาพเคลื่อนไหวสั้นเกินไป — เลือกเฟรมเริ่มกับเฟรมจบให้ห่างกันหน่อย")
    target = gif_path(clip, start, end)
    if target.is_file() and target.stat().st_size > 0:
        return target

    frames = (frame for frame, _at in _decode(clip.vid, _fetch_info(clip.vid), start, end, 1 / GIF_FPS))
    _encode_anim(frames, target)
    return target


def _encode_anim(frames, target: Path) -> int:
    """เฟรม (av.VideoFrame) → WebP เคลื่อนไหว ``GIF_WIDTH`` กว้าง ``GIF_FPS`` ภาพ/วิ วนไม่รู้จบ · คืนจำนวนเฟรม."""
    from fractions import Fraction

    import av

    temp = target.with_name(target.name + ".part")
    rate = Fraction(1, GIF_FPS)
    count = 0
    with av.open(str(temp), "w", format="webp") as out:
        stream = None
        for frame in frames:
            height = round(frame.height * GIF_WIDTH / frame.width / 2) * 2
            frame = frame.reformat(width=GIF_WIDTH, height=height, format="yuv420p")
            if stream is None:
                stream = out.add_stream("libwebp_anim", rate=GIF_FPS)
                stream.width, stream.height, stream.pix_fmt = GIF_WIDTH, height, "yuv420p"
                stream.options = {"quality": str(ANIM_QUALITY), "loop": "0", "lossless": "0"}
            frame.pts, frame.time_base = count, rate
            count += 1
            for packet in stream.encode(frame):
                out.mux(packet)
        if stream is None:
            raise OSError("ถอดเฟรมช่วงนี้ไม่ได้ — ลองใหม่อีกครั้ง")
        for packet in stream.encode():
            out.mux(packet)
    temp.replace(target)
    return count


def render(clip: Clip, plan: dict) -> Path:
    """ทำภาพเคลื่อนไหวตามแผน (เร่ง/ตัด) จาก proxy.mp4 ในเครื่อง — แผนเดิมไม่ทำซ้ำ."""
    import av

    plan = clean_plan(plan)
    length = plan_length(plan)
    if length < 0.3:
        raise ValueError("ภาพเคลื่อนไหวสั้นเกินไป (ต่ำกว่า 0.3 วิ) — ขยายช่วงหรือลดส่วนที่ตัดออก")
    if length > GIF_MAX + 1e-6:
        raise ValueError(f"ภาพเคลื่อนไหวยาว {length:.1f} วิ เกิน {GIF_MAX:.0f} วิ — "
                         f"เร่งหรือตัดเพิ่มอีก {length - GIF_MAX:.1f} วิ")
    proxy = proxy_path(clip)
    if not proxy.is_file() or clip.proxy_offset is None:
        raise OSError("ไม่มีคลิปในเครื่องแล้ว — เปิดลิงก์นี้ใหม่อีกครั้ง")
    key = hashlib.sha1(json.dumps(plan, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    target = Path(clip.folder) / f"anim-plan-{key}-{GIF_FPS}fps-q{ANIM_QUALITY}.webp"
    if target.is_file() and target.stat().st_size > 0:
        return target

    wanted = plan_times(plan)
    offset = float(clip.proxy_offset)

    def frames():
        index = 0
        last = None
        with av.open(str(proxy)) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            slack = 0.5 / float(stream.average_rate or 30)
            container.seek(max(0, int((wanted[0] - offset) / stream.time_base)), stream=stream, backward=True)
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                at = float(frame.pts * stream.time_base) + offset
                while index < len(wanted) and at >= wanted[index] - slack:
                    yield frame
                    index += 1
                last = frame
                if index >= len(wanted):
                    return
        while last is not None and index < len(wanted):     # คลิปหมดก่อน — ค้างเฟรมสุดท้าย
            yield last
            index += 1

    _encode_anim(frames(), target)
    return target


# ======================================================================
#  หาช่วงยิงให้ (เดาจากเฟรมที่ถอดไว้แล้ว ไม่ต้องต่อเน็ต)
# ======================================================================
def pick_throw(times: list[float], diffs: list[float]) -> tuple[float, float] | None:
    """เดาช่วงยิงจาก "ภาพเปลี่ยนไปเท่าไหร่" ระหว่างเฟรมติดกัน (``diffs[i]`` = เฟรม i กับ i+1).

    คนทำคลิปจะ **เล็งนิ่ง** ก่อนปล่อยลูกเสมอ (ภาพแทบไม่เปลี่ยน) แล้วพอปล่อยภาพก็เปลี่ยนแรง
    (ลูกพุ่ง/หันตามลูก) → ช่วงนิ่งที่ยาวที่สุด (เท่ากันเอาอันหลัง) จบตรงไหน = จังหวะปล่อยลูก
    เลือก 1 วิก่อนปล่อยถึงรวม ``GIF_SPAN`` วิ · ไม่มีช่วงนิ่งเลย = คืน None (เดาไม่ได้ ให้เลือกเอง)
    วัดกับคลิปจริงสองท่าแล้วตรงจังหวะปล่อยทั้งคู่ (29/09/2026) แต่คลิปที่ตัดต่อหนักๆ อาจเดาผิด
    """
    if len(times) < 3 or len(diffs) != len(times) - 1:
        return None
    limit = _still_limit(diffs)
    best: tuple[int, int] | None = None          # (ความยาว, ดัชนีจบ)
    run = 0
    for index, diff in enumerate(diffs):
        run = run + 1 if diff < limit else 0
        if run >= 2 and (best is None or run >= best[0]):
            best = (run, index)
    if best is None:
        return None
    release = times[best[1] + 1]                  # เฟรมนิ่งเฟรมสุดท้าย (diff i = เฟรม i กับ i+1)
    start = max(times[0], release - GIF_LEAD)
    end = min(times[-1] + STEP, start + GIF_SPAN)
    return round(start, 2), round(end, 2)


def _still_limit(diffs: list[float]) -> float:
    """ต่างกันไม่ถึงเท่านี้ = "นิ่ง" — ปรับตามคลิป (คลิปที่ภาพไหวตลอดเกณฑ์ก็สูงตาม)."""
    ordered = sorted(diffs)
    return max(4.0, 0.35 * ordered[len(ordered) // 2])


# ======================================================================
#  แผนตัดต่อของหน้าทำวิดีโอ (ฟังก์ชันล้วน — หน้าเว็บ video.js มีสูตรเดียวกันไว้โชว์ความยาวสดๆ)
# ======================================================================
SPEEDS = (0, 1, 2, 4)            # 0 = ตัดข้าม · 1 = ปกติ (ใช้ล้างช่วงที่ตั้งไว้)
STILL_MIN = 1.0                  # นิ่งนานกว่านี้ถึงเร่งให้เอง
STILL_SPEED = 4
STILL_KEEP = 0.5                 # เหลือท้ายช่วงนิ่งไว้ความเร็วปกติ — จังหวะเล็งก่อนปล่อยต้องเห็นชัด


def _r(value: float) -> float:
    return round(float(value), 3)


def clean_plan(plan: dict) -> dict:
    """แผนที่ส่งมา → แผนมาตรฐาน: หนีบเข้าช่วง · ทับกันอันที่ตั้งทีหลังชนะ · ×1 = ล้าง · ต่อช่วงที่ติดกัน.

    ``{"start": s, "end": e, "parts": [{"from": a, "to": b, "speed": 0|2|4}, …]}`` (วินาทีในคลิป)
    """
    start, end = sorted((_r(plan["start"]), _r(plan["end"])))
    if end - start < 0.05:
        raise ValueError("ช่วงที่เก็บสั้นเกินไป — ตั้งจุดเริ่มกับจุดจบให้ห่างกันหน่อย")
    spans: list[list] = []                       # [from, to, speed] ไม่ทับกัน
    for part in plan.get("parts") or []:
        speed = int(part.get("speed", 1))
        if speed not in SPEEDS or float(part.get("speed", 1)) != speed:
            raise ValueError(f"ความเร็ว {part.get('speed')} ใช้ไม่ได้ (ได้แค่ ×1 ×2 ×4 หรือตัดข้าม)")
        a, b = sorted((_r(part["from"]), _r(part["to"])))
        a, b = max(a, start), min(b, end)
        if b - a < 0.05:
            continue
        kept = []
        for x, y, s in spans:                    # ตัดส่วนที่ทับกับช่วงใหม่ออก
            if y <= a or x >= b:
                kept.append([x, y, s])
                continue
            if x < a:
                kept.append([x, a, s])
            if y > b:
                kept.append([b, y, s])
        kept.append([a, b, speed])
        spans = sorted(kept)
    merged: list[list] = []
    for x, y, s in spans:
        if s == 1 or y - x < 0.05:
            continue
        if merged and merged[-1][2] == s and abs(merged[-1][1] - x) < 1e-6:
            merged[-1][1] = y
        else:
            merged.append([x, y, s])
    return {"start": start, "end": end,
            "parts": [{"from": _r(x), "to": _r(y), "speed": s} for x, y, s in merged]}


def plan_length(plan: dict) -> float:
    """ความยาวภาพเคลื่อนไหวที่จะได้ (วินาที) หลังเร่ง/ตัดแล้ว."""
    plan = clean_plan(plan)
    total = plan["end"] - plan["start"]
    for part in plan["parts"]:
        span = part["to"] - part["from"]
        total += (span / part["speed"] if part["speed"] else 0.0) - span
    return round(total, 3)


def plan_times(plan: dict, fps: int = GIF_FPS) -> list[float]:
    """เวลาในคลิปของทุกเฟรมที่ต้องหยิบ — เดินทีละ 1/fps วิของผลลัพธ์ ช่วงเร่งก้าวยาวขึ้น ช่วงตัดกระโดดข้าม."""
    plan = clean_plan(plan)
    parts = plan["parts"]
    out: list[float] = []
    t = plan["start"]
    while t < plan["end"] - 1e-9:
        part = next((p for p in parts if p["from"] - 1e-9 <= t < p["to"] - 1e-9), None)
        speed = part["speed"] if part else 1
        if speed == 0:
            t = part["to"]
            continue
        out.append(round(t, 6))
        t += speed / fps
    return out


def still_runs(times: list[float], diffs: list[float]) -> list[tuple[float, float]]:
    """ช่วงที่ภาพนิ่ง (เวลาเริ่ม, เวลาจบ) — ``diffs[i]`` = เฟรม i กับ i+1 แบบเดียวกับ ``pick_throw``."""
    if len(times) < 2 or len(diffs) != len(times) - 1:
        return []
    limit = _still_limit(diffs)
    runs, first = [], None
    for index, diff in enumerate([*diffs, limit + 1]):
        if diff < limit:
            first = index if first is None else first
        elif first is not None:
            runs.append((times[first], times[index]))
            first = None
    return runs


def suggest_plan(times: list[float], diffs: list[float], start: float, end: float) -> dict:
    """แผนเริ่มต้นให้ท่านี้: ตั้งแต่ต้นท่าถึง 3 วิหลังปล่อยลูก · ช่วงนิ่งนานกว่า 1 วิเร่ง ×4
    (เหลือครึ่งวิท้ายไว้ปกติ) · ยังยาวเกิน ``GIF_MAX`` ก็ขยับจุดเริ่มเข้ามาจนพอดี."""
    release = pick_throw(times, diffs)
    stop = min(end, release[0] + GIF_SPAN) if release else end
    parts = [{"from": a, "to": b - STILL_KEEP, "speed": STILL_SPEED}
             for a, b in still_runs(times, diffs) if b - a > STILL_MIN]
    plan = clean_plan({"start": start, "end": stop, "parts": parts})
    while plan_length(plan) > GIF_MAX and plan["end"] - plan["start"] > 1.0:
        plan = clean_plan({**plan, "start": plan["start"] + 0.5})
    return plan


def suggest_gif(clip: Clip) -> tuple[float, float] | None:
    """ช่วงยิงที่เดาได้จากเฟรมของคลิปนี้ (ย่อเหลือ 64×36 ขาวดำแล้วเทียบกัน — เร็ว ไม่ต่อเน็ต)."""
    from PySide6.QtGui import QImage

    shots = []
    for path in clip.paths():
        image = QImage(str(path)).scaled(64, 36).convertToFormat(QImage.Format.Format_Grayscale8)
        shots.append(bytes(image.constBits())[:image.sizeInBytes()])
    diffs = [sum(abs(a - b) for a, b in zip(one, two)) / max(1, len(one))
             for one, two in zip(shots, shots[1:])]
    return pick_throw(clip.times, diffs)

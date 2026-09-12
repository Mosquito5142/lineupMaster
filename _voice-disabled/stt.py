"""ห่อ faster-whisper: โหลดโมเดลบน GPU (ถ้าได้) แล้ว warm ไว้ให้พร้อมยิง."""

from __future__ import annotations

import ctypes
import os
import site
import sys
import threading
from pathlib import Path

import numpy as np


# เก็บ handle ไว้ไม่ให้ถูกเก็บกวาด และกัน DLL ถูก unload
_DLL_HANDLES: list = []
_DLL_DIRS: list = []
_PROBE: tuple[list[str], str | None] | None = None

# ลำดับสำคัญ: ตัวที่ถูกพึ่งพาต้องมาก่อน
_PRELOAD = (
    "nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll",
    "nvidia/cublas/bin/cublasLt64_12.dll",
    "nvidia/cublas/bin/cublas64_12.dll",
    "nvidia/cudnn/bin/cudnn_graph64_9.dll",
    "nvidia/cudnn/bin/cudnn_ops64_9.dll",
    "nvidia/cudnn/bin/cudnn64_9.dll",
)

# ctranslate2 ต้องใช้ แต่ไม่ได้แถมมาในแพ็กเกจตัวเอง — ขาดตัวใดตัวหนึ่ง = ใช้ GPU ไม่ได้
_REQUIRED = ("cublasLt64_12.dll", "cublas64_12.dll")


def _quiet_dll_errors() -> None:
    """ห้าม Windows เด้ง dialog 'ไม่พบ xxx.dll' ซึ่งจะทำให้โปรแกรมค้างรอคนกดปิด."""
    if os.name != "nt":
        return
    # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
    try:
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except OSError:
        pass


def _site_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in [*site.getsitepackages(), *sys.path]:
        try:
            path = Path(raw)
        except (TypeError, ValueError):
            continue
        key = str(path).lower()
        if key not in seen and path.is_dir():
            seen.add(key)
            roots.append(path)
    return roots


def _enable_cuda_dlls() -> tuple[list[str], str | None]:
    """เตรียม cuBLAS/cuDNN แล้วบอกว่า GPU ใช้ได้จริงไหม.

    คืน (รายชื่อ DLL ที่โหลดได้, เหตุผลที่ใช้ GPU ไม่ได้ / None ถ้าใช้ได้)

    ต้องเช็คตรงนี้ให้จบ เพราะถ้าปล่อยไปสร้าง WhisperModel(device="cuda")
    ทั้งที่ cuBLAS โหลดไม่ได้ มันจะ **ค้างถาวร** ไม่โยน exception ให้ดักเลย

    หมายเหตุ: `os.add_dll_directory` อย่างเดียวไม่พอ เพราะ ctranslate2.dll เรียก
    cublas64_12.dll แบบ delay-load ซึ่ง Windows resolve ด้วย LoadLibraryEx flag = 0
    path ที่เพิ่มไว้จะไม่ถูกค้น ต้องโหลดเข้า process ตรงๆ ด้วย full path ก่อน
    """
    global _PROBE
    if _PROBE is not None:
        return _PROBE
    if os.name != "nt":
        _PROBE = ([], None)
        return _PROBE

    _quiet_dll_errors()

    # ไม่มีไดรเวอร์ NVIDIA ก็จบตั้งแต่ตรงนี้ ไม่ต้องเสียเวลาลอง
    try:
        ctypes.WinDLL("nvcuda.dll")
    except OSError:
        _PROBE = ([], "ไม่พบไดรเวอร์ NVIDIA (nvcuda.dll)")
        return _PROBE

    roots = _site_roots()
    for root in roots:
        nvidia = root / "nvidia"
        if not nvidia.is_dir():
            continue
        for sub in nvidia.iterdir():
            bin_dir = sub / "bin"
            if bin_dir.is_dir():
                try:
                    _DLL_DIRS.append(os.add_dll_directory(str(bin_dir)))
                except OSError:
                    pass

    loaded: list[str] = []
    for rel in _PRELOAD:
        for root in roots:
            dll = root / rel
            if not dll.is_file():
                continue
            try:
                _DLL_HANDLES.append(ctypes.WinDLL(str(dll)))
                loaded.append(dll.name)
            except OSError:
                pass
            break

    missing = [name for name in _REQUIRED if name not in loaded]
    problem = f"โหลดไม่ได้/ไม่พบ: {', '.join(missing)}" if missing else None
    _PROBE = (loaded, problem)
    return _PROBE


def _with_timeout(fn, seconds: float):
    """เรียก fn แบบมีเพดานเวลา คืน (สำเร็จไหม, ผลลัพธ์, ข้อผิดพลาด).

    เผื่อกรณีที่ ctranslate2 ไปค้างในโค้ด C++ ซึ่ง Python ขัดจังหวะไม่ได้ —
    อย่างน้อยแอปจะได้เดินต่อไปใช้ CPU แทนที่จะค้างรอตลอดกาล
    """
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return False, None, TimeoutError(f"เกิน {seconds:.0f} วินาที")
    if "error" in box:
        return False, None, box["error"]
    return True, box.get("value"), None


def build_prompt(aliases: dict) -> str:
    """คำใบ้ให้ Whisper เอนไปทางศัพท์ในเกม ช่วยลดการถอดเพี้ยนมาก."""
    words: list[str] = []
    for key in ("maps", "agents", "abilities", "places"):
        for tag, alts in (aliases.get(key) or {}).items():
            words.append(tag.replace("-", " "))
            for alt in (alts or [])[:2]:
                alt = str(alt)
                if any("\u0e00" <= ch <= "\u0e7f" for ch in alt):
                    words.append(alt)
    seen: set[str] = set()
    uniq = [w for w in words if not (w in seen or seen.add(w))]
    return "ไลน์อัพ VALORANT: " + " ".join(uniq[:110])


class Transcriber:
    def __init__(self, stt_cfg: dict, aliases: dict) -> None:
        self.cfg = stt_cfg
        self.prompt = build_prompt(aliases)
        self.model = None
        self.backend = "loading"
        self.error: str | None = None
        self._lock = threading.Lock()

    # ── loading ────────────────────────────────────────────────────────
    def load(self) -> None:
        loaded, problem = _enable_cuda_dlls()
        if loaded:
            print("[stt] preloaded CUDA libs:", ", ".join(loaded))
        if problem:
            print(f"[stt] ใช้ GPU ไม่ได้ ({problem}) — จะใช้ CPU แทน")

        from faster_whisper import WhisperModel

        name = self.cfg.get("model", "small")
        want = (self.cfg.get("device") or "auto").lower()
        ctype = (self.cfg.get("compute_type") or "auto").lower()
        budget = float(self.cfg.get("load_timeout", 120))

        attempts: list[tuple[str, str]] = []
        if want in ("auto", "cuda") and problem is None:
            attempts.append(("cuda", "float16" if ctype == "auto" else ctype))
            attempts.append(("cuda", "int8_float16"))
        attempts.append(("cpu", "int8" if ctype in ("auto", "float16", "int8_float16") else ctype))

        last: BaseException | None = None
        for device, compute in attempts:
            ok, model, exc = _with_timeout(
                lambda d=device, c=compute: self._build(WhisperModel, name, d, c), budget
            )
            if ok:
                self.model = model
                self.backend = f"{device}/{compute}"
                self.error = None
                return
            last = exc
            print(f"[stt] {device}/{compute} ใช้ไม่ได้: {exc}")
        self.backend = "failed"
        self.error = str(last) if last else "unknown error"

    def _build(self, WhisperModel, name: str, device: str, compute: str):
        model = WhisperModel(name, device=device, compute_type=compute)
        self._warmup(model)
        return model

    def load_async(self, done=None) -> threading.Thread:
        def run() -> None:
            self.load()
            if done:
                done(self)

        t = threading.Thread(target=run, name="stt-load", daemon=True)
        t.start()
        return t

    @staticmethod
    def _warmup(model) -> None:
        """รันโมเดลจริง 1 รอบ.

        ต้อง "วน generator" ให้จบและปิด VAD ด้วย ไม่งั้นมันจะไม่คำนวณอะไรเลย
        แล้วเราจะไม่รู้ว่า GPU ใช้ได้จริงไหมจนกว่าจะพูดครั้งแรก (ซึ่งสายไปแล้ว)
        """
        t = np.arange(16000, dtype=np.float32) / 16000.0
        tone = (0.05 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
        segments, _info = model.transcribe(tone, language="en", beam_size=1, vad_filter=False)
        for _segment in segments:
            pass

    @property
    def ready(self) -> bool:
        return self.model is not None

    # ── inference ──────────────────────────────────────────────────────
    def transcribe(self, audio: np.ndarray) -> str:
        if self.model is None:
            raise RuntimeError(self.error or "โมเดลยังโหลดไม่เสร็จ")
        with self._lock:
            segments, _info = self.model.transcribe(
                audio,
                language=self.cfg.get("language", "th"),
                beam_size=int(self.cfg.get("beam_size", 1)),
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=self.prompt,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

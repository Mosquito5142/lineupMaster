"""เปิดหน้าจัดการคลัง (เว็บ) ตรงหน้าที่ต้องการ — ใช้ร่วมกันทั้งหน้าเข้าโปรแกรมและหน้าต่อรูป.

เซิร์ฟเวอร์เว็บที่เปิดอยู่แล้วจดที่อยู่ไว้ใน ``.cache/web.json`` — ยังตอบอยู่ก็เปิดแท็บใหม่ไปที่
``url#target`` เลย ไม่งั้นสั่งเปิดเซิร์ฟเวอร์ใหม่พร้อม ``--open target``

``parent`` = pid ของโปรแกรมที่เซิร์ฟเวอร์ต้องปิดตามเมื่อโปรแกรมนั้นปิด (กันเซิร์ฟเวอร์ค้างเงียบๆ
จนบิ้วโปรแกรมใหม่ไม่ได้)
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
import webbrowser

from .paths import APP, ROOT, is_frozen


def _live_url() -> str | None:
    try:
        url = json.loads((ROOT / ".cache" / "web.json").read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(url, str):
        return None
    try:
        with urllib.request.urlopen(url.split("?")[0], timeout=0.6):
            return url
    except OSError:
        return None


def open_web(target: str, parent: int) -> subprocess.Popen | None:
    """คืนโปรเซสเซิร์ฟเวอร์ถ้าต้องเปิดใหม่ (None = ใช้ตัวที่เปิดอยู่แล้ว)."""
    url = _live_url()
    if url:
        webbrowser.open(f"{url}#{target}")
        return None
    base = [sys.executable] if is_frozen() else [sys.executable, str(APP / "tools" / "entry.py")]
    cmd = [*base, "web", "--open", target, "--parent", str(parent)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(cmd, cwd=str(APP), creationflags=flags)

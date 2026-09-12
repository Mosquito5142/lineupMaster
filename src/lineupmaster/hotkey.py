"""ดักปุ่ม global แบบเดียวกับ Discord push-to-talk / OBS.

ใช้ hook ระดับ OS ที่ "ไม่ suppress" ปุ่ม — ปุ่มยังส่งต่อไปแอปอื่นตามปกติ
และเราไม่เคยส่ง input กลับเข้าไปที่ไหนทั้งสิ้น (อ่านอย่างเดียว)
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from pynput import keyboard, mouse

_KEY_NAMES: dict[object, str] = {
    keyboard.Key.ctrl_r: "right ctrl",
    keyboard.Key.ctrl_l: "left ctrl",
    keyboard.Key.alt_r: "right alt",
    keyboard.Key.alt_gr: "right alt",
    keyboard.Key.alt_l: "left alt",
    keyboard.Key.shift_r: "right shift",
    keyboard.Key.shift_l: "left shift",
    keyboard.Key.caps_lock: "caps lock",
    keyboard.Key.tab: "tab",
    keyboard.Key.esc: "esc",
    keyboard.Key.space: "space",
    keyboard.Key.insert: "insert",
    keyboard.Key.delete: "delete",
    keyboard.Key.home: "home",
    keyboard.Key.end: "end",
    keyboard.Key.page_up: "page up",
    keyboard.Key.page_down: "page down",
    keyboard.Key.left: "left",
    keyboard.Key.right: "right",
    keyboard.Key.up: "up",
    keyboard.Key.down: "down",
}
for _i in range(1, 25):
    _fk = getattr(keyboard.Key, f"f{_i}", None)
    if _fk is not None:
        _KEY_NAMES[_fk] = f"f{_i}"

_MOUSE_NAMES: dict[object, str] = {
    mouse.Button.x1: "mouse4",
    mouse.Button.x2: "mouse5",
    mouse.Button.middle: "mouse3",
}


# Numpad ส่ง "ตัวอักษร" ตัวเดียวกับแป้นเลขแถวบน (ซึ่งเป็นปุ่มเปลี่ยนอาวุธในเกม)
# แยกกันได้ที่ virtual key code เท่านั้น — ต้องเช็ค vk ก่อน char เสมอ
# ต้องเปิด NumLock ไว้ ไม่งั้น Windows จะส่งเป็นปุ่มลูกศร/End/PgDn แทน
_NUMPAD_VK = {
    96: "numpad0", 97: "numpad1", 98: "numpad2", 99: "numpad3", 100: "numpad4",
    101: "numpad5", 102: "numpad6", 103: "numpad7", 104: "numpad8", 105: "numpad9",
    106: "numpad*", 107: "numpad+", 109: "numpad-", 110: "numpad.", 111: "numpad/",
}


def _key_name(key) -> str | None:
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    vk = getattr(key, "vk", None)
    if vk in _NUMPAD_VK:
        return _NUMPAD_VK[vk]
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    if vk is not None:
        return f"vk{vk}"
    return None


def normalize_spec(spec: str) -> str:
    return " ".join(str(spec or "").strip().lower().split())


class HotkeyManager:
    """map ชื่อ action → ปุ่ม แล้วยิง callback ตอนกด/ปล่อย (ยิงครั้งเดียวต่อการกด).

    on_press ได้ทั้งชื่อ action และ**ชื่อปุ่มจริงที่กด** เพราะบางชั้นตีความปุ่มคนละแบบ
    (ชั้นแผนที่อ่านเลขจากปุ่ม numpad ตรงๆ ไม่ผ่านชื่อ action จะได้ไม่พังถ้าผู้ใช้เปลี่ยนปุ่ม)
    """

    def __init__(
        self,
        bindings: dict[str, str],
        on_press: Callable[[str, str], None],
        on_release: Callable[[str], None] | None = None,
    ) -> None:
        self.bindings = {normalize_spec(v): k for k, v in bindings.items() if v}
        self.on_press = on_press
        self.on_release = on_release
        self._held: set[str] = set()
        self._lock = threading.Lock()
        self._kb: keyboard.Listener | None = None
        self._ms: mouse.Listener | None = None

    @property
    def uses_mouse(self) -> bool:
        return any(spec.startswith("mouse") for spec in self.bindings)

    def _press(self, name: str | None) -> None:
        if name is None:
            return
        action = self.bindings.get(name)
        if action is None:
            return
        with self._lock:
            if name in self._held:   # กันปุ่ม auto-repeat ตอนกดค้าง
                return
            self._held.add(name)
        self.on_press(action, name)

    def _release(self, name: str | None) -> None:
        if name is None:
            return
        action = self.bindings.get(name)
        if action is None:
            return
        with self._lock:
            if name not in self._held:
                return
            self._held.discard(name)
        if self.on_release:
            self.on_release(action)

    def start(self) -> None:
        self._kb = keyboard.Listener(
            on_press=lambda k: self._press(_key_name(k)),
            on_release=lambda k: self._release(_key_name(k)),
        )
        self._kb.daemon = True
        self._kb.start()

        if self.uses_mouse:
            def on_click(_x, _y, button, pressed):
                name = _MOUSE_NAMES.get(button)
                self._press(name) if pressed else self._release(name)

            self._ms = mouse.Listener(on_click=on_click)
            self._ms.daemon = True
            self._ms.start()

    def stop(self) -> None:
        for listener in (self._kb, self._ms):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:  # noqa: BLE001
                    pass
        self._kb = self._ms = None

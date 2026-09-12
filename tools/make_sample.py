"""สร้างรูปตัวอย่าง (placeholder) ไว้ทดสอบว่าระบบทำงานครบวงจร.

ลบโฟลเดอร์ lineups/ascent/ ทิ้งได้เลยเมื่อเริ่มใส่รูปจริง
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]

# (โฟลเดอร์, ชื่อไฟล์, คำอธิบาย, สีพื้น) — 1 รูป = 1 ไลน์อัพ
SAMPLES = [
    (
        "ascent/attack/sova",
        "recon_a-main_to_a-site",
        "ชาร์จ 2 ขีด เด้ง 1 · ยืนชิดมุมกล่องซ้าย เล็งขอบเสาบน",
        "#1f2a44",
    ),
    (
        "ascent/attack/sova",
        "shock_a-main_to_a-heaven",
        "ชาร์จเต็ม เด้ง 0 · ยืนหลังกำแพง เล็งมุมหลังคา",
        "#432a1f",
    ),
    (
        "ascent/defense/sova",
        "recon_default_to_mid",
        "เด้ง 2 · ยืนที่จุด default เล็งขอบท่อ",
        "#1f4430",
    ),
    (
        "ascent/attack/sova",
        "recon_default_to_a-site",
        "เด้ง 2 · ยืนจุด default เล็งขอบกำแพง",
        "#3a1f44",
    ),
    (
        "ascent/attack/sova",
        "drone_a-main_to_a-site",
        "ปล่อยโดรนจากมุมซ้าย เลี้ยวขวา",
        "#1f4444",
    ),
    (
        "ascent/attack/sova",
        "shock_a-main_to_a-site",
        "ชาร์จ 1 ขีด เด้ง 2 · เล็งขอบป้าย",
        "#44251f",
    ),
]


def draw(path: Path, heading: str, subtitle: str, color: str) -> None:
    img = QImage(1280, 720, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    font = QFont()
    font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
    font.setPointSize(40)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(img.rect().adjusted(0, -60, 0, -60), Qt.AlignmentFlag.AlignCenter, heading)

    font.setPointSize(20)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QColor("#c9d1e6"))
    painter.drawText(img.rect().adjusted(0, 80, 0, 80), Qt.AlignmentFlag.AlignCenter, subtitle)
    painter.end()

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    QGuiApplication(sys.argv)  # ต้องมี instance ก่อนวาดฟอนต์

    base = ROOT / "lineups"
    for folder, name, note, color in SAMPLES:
        target = base / folder
        target.mkdir(parents=True, exist_ok=True)
        draw(target / f"{name}.png", name.replace("_", " "), note, color)
        (target / f"{name}.txt").write_text(note, encoding="utf-8")
        print("เขียน", target / f"{name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

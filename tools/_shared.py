"""ชิ้นส่วน Qt ที่ใช้ร่วมกันระหว่างเครื่องมือใน tools/ (manage.py, pin_lineups.py).

ไม่ใช่ส่วนหนึ่งของแพ็กเกจ ``lineupmaster`` เพราะเป็นของเฉพาะหน้าจอแก้ไข ไม่เกี่ยวกับ
ตัวแอปที่รันบนจอที่สอง — import ได้ตรงๆ จากไฟล์ในโฟลเดอร์ ``tools/`` ด้วยกันเพราะ Python
เติมโฟลเดอร์ของสคริปต์ที่กำลังรันเข้า ``sys.path`` ให้อัตโนมัติเสมอ
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImageReader, QPixmap

THUMB = QSize(190, 110)

STYLE = """
QWidget { background: #0b0e14; color: #e6e8ee; }
QLineEdit, QComboBox { background: #151b26; border: 1px solid #2a3444;
                       border-radius: 4px; padding: 6px 8px; }
QPushButton { background: #1d2634; border: 1px solid #2f3d51; border-radius: 4px;
              padding: 7px 14px; }
QPushButton:hover { background: #26324a; }
QPushButton:disabled { color: #55607a; border-color: #222b39; }
QListWidget { background: #0e131c; border: 1px solid #1d2634; }
QListWidget::item { color: #c3cbd9; padding: 4px; }
QListWidget::item:selected { background: #26324a; color: #ffffff; }
QCheckBox { padding: 4px; }
"""


def thumbnail(path: Path, size: QSize = THUMB) -> QIcon:
    """ย่อรูปตอนถอดรหัสเลย (setScaledSize) — เร็วกว่าโหลดเต็มแล้วค่อยย่อมาก."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source = reader.size()
    if source.isValid() and source.width() > 0:
        reader.setScaledSize(source.scaled(size, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return QIcon(QPixmap.fromImage(image)) if not image.isNull() else QIcon()

"""สร้าง assets/icon.ico (หลายขนาดในไฟล์เดียว) จากรูปต้นฉบับ.

    python tools/make_ico.py                  ใช้ assets/icon.png เป็นต้นฉบับ
    python tools/make_ico.py path/to/pic.jpg  ระบุรูปต้นฉบับเอง

path ทุกอย่างอิงจากรากโปรเจกต์ ไม่ใช่โฟลเดอร์ที่รันอยู่ และไม่ฝัง path ของเครื่องใครไว้
จะได้ย้ายเครื่องแล้วยังรันได้
"""

import sys
from pathlib import Path
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]

def make_ico():
    app = QApplication([])
    assets_dir = ROOT / "assets"
    assets_dir.mkdir(exist_ok=True)

    src_img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else assets_dir / "icon.png"
    if not src_img_path.is_file():
        print(f"Source image not found: {src_img_path}")
        print("Usage: python tools/make_ico.py [path/to/image]")
        return 1

    img = QImage(str(src_img_path))
    if img.isNull():
        print(f"Failed to load image: {src_img_path}")
        return 1

    # Save PNG
    png_path = assets_dir / "icon.png"
    img.save(str(png_path), "PNG")
    print(f"Saved PNG to {png_path}")

    # Build multi-size ICO using standard ICO format
    # ICO format header:
    # 2 bytes: 0 (reserved)
    # 2 bytes: 1 (type 1 = ICO)
    # 2 bytes: count of images
    # Directory entries (16 bytes each):
    #   1 byte: width (0 for 256)
    #   1 byte: height (0 for 256)
    #   1 byte: color count (0)
    #   1 byte: reserved (0)
    #   2 bytes: color planes (1)
    #   2 bytes: bits per pixel (32)
    #   4 bytes: size of image data in bytes
    #   4 bytes: offset of image data from beginning of file
    
    import struct
    from PySide6.QtCore import QBuffer, QIODevice

    sizes = [16, 32, 48, 64, 128, 256]
    png_data_list = []
    
    for s in sizes:
        scaled = img.scaled(s, s)
        buf = QBuffer()
        buf.open(QIODevice.ReadWrite)
        scaled.save(buf, "PNG")
        data = bytes(buf.data())
        png_data_list.append((s, data))
    
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    
    dir_entries = []
    for s, data in png_data_list:
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        size = len(data)
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, size, offset)
        dir_entries.append(entry)
        offset += size
    
    ico_bytes = header + b"".join(dir_entries) + b"".join([d for _, d in png_data_list])
    
    ico_path = assets_dir / "icon.ico"
    with open(ico_path, "wb") as f:
        f.write(ico_bytes)
    print(f"Saved ICO to {ico_path}")

    # Also save to root icon.ico
    root_ico = ROOT / "icon.ico"
    with open(root_ico, "wb") as f:
        f.write(ico_bytes)
    print(f"Saved {root_ico}")
    return 0

if __name__ == "__main__":
    raise SystemExit(make_ico())

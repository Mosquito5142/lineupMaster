# -*- mode: python ; coding: utf-8 -*-
"""สูตรบิ้ว LineupMaster เป็น exe แบบโฟลเดอร์ (onedir).

    .venv\\Scripts\\python.exe tools\\build_exe.py     <- ใช้ตัวนี้ ไม่ต้องเรียก spec เอง

ทำไมเป็น exe ตัวเดียว: PySide6 ใหญ่หลายร้อยเมกะไบต์ ถ้าบิ้วแยกตัวโปรแกรมกับตัวจัดการ
Qt จะถูกก๊อปซ้ำสองรอบ จึงบิ้วตัวเดียวแล้วแยกงานด้วยคำสั่งย่อย (manage / pin / maps)
ตามที่ __main__.py กำหนดไว้ แล้วทำ shortcut แยกไอคอนให้แต่ละคำสั่งแทน

ไม่ฝังข้อมูลผู้ใช้เข้าบันเดิล — lineups/, config.yaml, positions.json ฯลฯ อยู่ข้างๆ exe
เพราะเป็นของที่แก้ตลอด (ดู src/lineupmaster/paths.py)
"""

from pathlib import Path

ROOT = Path(SPECPATH)

# โมดูลของเครื่องมือย่อยถูกเรียกด้วย importlib จึงต้องบอก PyInstaller ตรงๆ
HIDDEN = [
    "manage",
    "pin_lineups",
    "fetch_maps",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
]

# ตัดส่วนของ Qt ที่ไม่ได้ใช้ออก ไม่งั้นบันเดิลจะใหญ่เกินจำเป็นมาก
EXCLUDE = [
    "tkinter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtRemoteObjects", "PySide6.QtTextToSpeech", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtNetworkAuth", "PySide6.QtHttpServer", "PySide6.QtLocation",
]

a = Analysis(
    [str(ROOT / "tools" / "entry.py")],
    pathex=[str(ROOT / "src"), str(ROOT / "tools")],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDE,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LineupMaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX บีบแล้วโดน antivirus จับง่ายขึ้นอีก จึงไม่ใช้
    console=True,              # ต้องมีคอนโซล คำสั่ง maps/--list ถึงจะเห็นผลลัพธ์
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LineupMaster",
)

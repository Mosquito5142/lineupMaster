"""ทดสอบหน้าเว็บส่วน "⚑ ต้องแก้" กับ "วาดทับรูป" (``Store`` ใน tools/web_manage.py).

- ธงที่โปรแกรมหลักกด (F8) ส่งออกไปหน้าเว็บ · ติ๊กออกได้ · เว็บเซฟแล้วไม่ทับธงที่เพิ่งกด
- วาดทับ: สำรองต้นฉบับครั้งแรกครั้งเดียว · กลับเป็นรูปเดิมได้เป๊ะ · ย้าย/เปลี่ยนชื่อ/ลบ ลากต้นฉบับตาม

ใช้คลังจำลองชุดเดียวกับ test_web_merge (web_manage อ่าน ROOT ตอน import)
รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import base64
import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402

from lineupmaster import library as lib  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402

web_manage = shared.web_manage
HERE = shared.HERE

A = "ascent/attack/kayo/A/ใบเอ.png"
B = "ascent/attack/kayo/B/ใบบี.png"
J = "ascent/attack/kayo/A/ใบเจ.jpg"
G = "ascent/attack/kayo/A/คลิป.gif"


def picture(fmt: str, color: str) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray
    from PySide6.QtGui import QColor, QImage

    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, fmt)
    buffer.close()
    return bytes(data)


def data_url(color: str) -> str:
    return "data:image/png;base64," + base64.b64encode(picture("PNG", color)).decode()


def sha(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


class WebFlagDrawTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(HERE, ignore_errors=True)
        shared.make(HERE, {A: picture("PNG", "red"), B: picture("PNG", "blue"),
                           J: picture("JPG", "green"), G: b"GIF89a"})
        shutil.copy2(shared.REPO / "aliases.yaml", HERE / "aliases.yaml")
        self.store = web_manage.Store()

    def item(self, rel: str) -> dict:
        return next(i for i in self.store.state()["lineups"] if i["rel"] == rel)

    def edit(self, rel: str, **extra) -> dict:
        lu = self.item(rel)
        body = {"rel": rel, "name": lu["stem"], "map": lu["map"], "side": lu["side"],
                "site": lu["site"], "agent": lu["agent"], "ability": lu["ability"],
                "fav": lu["fav"], "tags": lu["tags"], "note": lu["note"]}
        body.update(extra)
        return self.store.save_edits(body)

    # -- ⚑ ต้องแก้ -------------------------------------------------------
    def test_flag_from_main_app_shows_and_can_be_cleared(self) -> None:
        meta_mod.save(HERE / "meta.json", {A: {"flag": True}})     # โปรแกรมหลักกด F8
        self.assertTrue(self.item(A)["flag"], "รีเฟรชหน้าเว็บแล้วเห็นธงใหม่โดยไม่ต้องรีสตาร์ต")
        self.assertFalse(self.item(B)["flag"])
        self.edit(A, flag=False)
        self.assertNotIn(A, meta_mod.load(HERE / "meta.json"))

    def test_web_save_keeps_flag_set_meanwhile(self) -> None:
        self.store.state()
        meta_mod.save(HERE / "meta.json", {A: {"flag": True}})     # กด F8 ระหว่างเว็บเปิดค้าง
        self.edit(B, fav=True)                                     # แล้วเว็บเซฟใบอื่น
        data = meta_mod.load(HERE / "meta.json")
        self.assertTrue(data[A]["flag"], "ธงที่เพิ่งกดต้องไม่หาย")
        self.assertTrue(data[B]["fav"])

    def test_old_form_without_flag_leaves_flag_alone(self) -> None:
        meta_mod.save(HERE / "meta.json", {A: {"flag": True}})
        self.edit(A, fav=True)
        self.assertTrue(meta_mod.load(HERE / "meta.json")[A]["flag"])

    # -- วาดทับ ----------------------------------------------------------
    def test_draw_backs_up_first_original_only_and_reverts(self) -> None:
        image = HERE / "lineups" / A
        before = sha(image)
        self.store.save_drawing(A, data_url("yellow"))
        original = lib.original_of(HERE, A)
        self.assertEqual(sha(original), before)
        self.assertNotEqual(sha(image), before)
        self.assertTrue(self.item(A)["hasOriginal"])
        self.store.save_drawing(A, data_url("white"))
        self.assertEqual(sha(original), before, "วาดรอบสองต้นฉบับยังเป็นรูปก่อนวาดครั้งแรก")

        self.store.revert_drawing(A)
        self.assertEqual(sha(image), before)
        self.assertFalse(original.exists())
        self.assertFalse(self.item(A)["hasOriginal"])
        self.assertTrue(list((HERE / ".trash").glob("*-drawn/**/ใบเอ.png")), "รูปที่วาดเข้าถัง")

    def test_jpg_stays_jpg_and_gif_refused(self) -> None:
        self.store.save_drawing(J, data_url("yellow"))
        self.assertEqual((HERE / "lineups" / J).read_bytes()[:2], b"\xff\xd8", "ยังเป็นไฟล์ jpg")
        with self.assertRaises(ValueError):
            self.store.save_drawing(G, data_url("yellow"))

    def test_rename_move_delete_carry_original(self) -> None:
        self.store.save_drawing(A, data_url("yellow"))
        self.edit(A, name="ชื่อใหม่", site="b")
        new_rel = "ascent/attack/kayo/B/ชื่อใหม่.png"
        self.assertTrue(lib.original_of(HERE, new_rel).is_file())
        self.assertFalse(lib.original_of(HERE, A).exists())
        self.store.delete(new_rel)
        self.assertFalse(lib.original_of(HERE, new_rel).exists())
        self.assertTrue(list((HERE / ".trash").glob("*-original/**/ชื่อใหม่.png")))

    def test_image_version_changes_after_drawing(self) -> None:
        self.assertIn("v", self.item(A))
        self.store.save_drawing(A, data_url("yellow"))
        self.assertTrue(self.item(A)["hasOriginal"])


if __name__ == "__main__":
    unittest.main()

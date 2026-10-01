"""ทดสอบฝั่งเซิร์ฟเวอร์ของหน้าทำวิดีโอ (tools/web_manage.py).

- ส่ง proxy.mp4 แบบขอทีละส่วน (Range → 206) ให้ ``<video>`` กระโดดเวลาได้
- กดเก็บพร้อมแผนตัดต่อ → ทำภาพเคลื่อนไหวก่อนเข้าล็อก → เข้าคลังแบบภาพเคลื่อนไหวล้วน + หมุด + วิธียิง
- แผนผิด (ยาวเกิน) ตอบ 400 ไม่มีอะไรเข้าคลัง

ใช้คลังจำลองชุดเดียวกับ test_web_merge (web_manage อ่าน ROOT ตอน import)
รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import json
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402

from lineupmaster import clipgrab  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402

web_manage = shared.web_manage
HERE = shared.HERE
TOKEN = "tok"
# WebP เคลื่อนไหวจิ๋ว (หัวไฟล์ VP8X ติดธง animation) — พอให้คลังนับว่าเป็นภาพเคลื่อนไหว
ANIM = b"RIFF\x1e\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x12" + b"\x00" * 10


class WebVideoTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(HERE, ignore_errors=True)
        shared.make(HERE, {shared.A: b"a"})
        shutil.copy2(shared.REPO / "aliases.yaml", HERE / "aliases.yaml")
        self.store = web_manage.Store()
        self.source = web_manage.SourceBrowser()
        folder = HERE / ".cache" / "clips" / "Qlbwecza9GI-376"
        self.clip = clipgrab.Clip(vid="Qlbwecza9GI", title="Top Sova Sunset", chapter="A Alley Reveal (Attacker)",
                                  start=376.0, end=400.0, folder=str(folder), proxy_offset=375.0,
                                  side="attack", site="a", map="sunset", agent="sova")
        folder.mkdir(parents=True)
        self.proxy = clipgrab.proxy_path(self.clip)
        self.proxy.write_bytes(bytes(range(256)) * 4)          # 1024 ไบต์ เนื้อรู้ค่าทุกตำแหน่ง
        self.uid = self.source._clip_entry(self.clip, video=True)["uid"]

        handler = partial(web_manage.Handler, store=self.store, source=self.source, token=TOKEN)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path: str, headers: dict | None = None):
        request = urllib.request.Request(f"{self.base}{path}&t={TOKEN}", headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def post(self, path: str, body: dict):
        request = urllib.request.Request(f"{self.base}{path}?t={TOKEN}", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    # -- ส่งคลิปทีละส่วน --------------------------------------------------
    def test_full_file(self) -> None:
        code, headers, body = self.get(f"/api/video/file?uid={self.uid}")
        self.assertEqual(code, 200)
        self.assertEqual(body, self.proxy.read_bytes())
        self.assertEqual(headers.get("Accept-Ranges"), "bytes")

    def test_range(self) -> None:
        code, headers, body = self.get(f"/api/video/file?uid={self.uid}", {"Range": "bytes=100-199"})
        self.assertEqual(code, 206)
        self.assertEqual(body, self.proxy.read_bytes()[100:200])
        self.assertEqual(headers.get("Content-Range"), "bytes 100-199/1024")

    def test_open_ended_and_suffix(self) -> None:
        _code, _h, body = self.get(f"/api/video/file?uid={self.uid}", {"Range": "bytes=1000-"})
        self.assertEqual(body, self.proxy.read_bytes()[1000:])
        _code, _h, body = self.get(f"/api/video/file?uid={self.uid}", {"Range": "bytes=-24"})
        self.assertEqual(body, self.proxy.read_bytes()[-24:])

    def test_out_of_range(self) -> None:
        code, headers, _body = self.get(f"/api/video/file?uid={self.uid}", {"Range": "bytes=5000-"})
        self.assertEqual(code, 416)
        self.assertEqual(headers.get("Content-Range"), "bytes */1024")

    def test_unknown_clip(self) -> None:
        code, _h, _b = self.get("/api/video/file?uid=yt:nope-1")
        self.assertEqual(code, 404)

    # -- กดเก็บพร้อมแผน ---------------------------------------------------
    def fake_render(self, clip, plan):
        clipgrab.clean_plan(plan)
        if clipgrab.plan_length(plan) > clipgrab.GIF_MAX:
            raise ValueError("ยาวเกิน")
        out = Path(clip.folder) / "anim-plan-test.webp"
        out.write_bytes(ANIM)
        return out

    def test_take_with_plan(self) -> None:
        plan = {"start": 380, "end": 386, "parts": [{"from": 381, "to": 385, "speed": 4}]}
        original = clipgrab.render
        clipgrab.render = self.fake_render
        try:
            code, result = self.post("/api/source/take", {
                "uid": self.uid, "plan": plan, "name": "A Alley Reveal", "map": "sunset",
                "side": "attack", "site": "a", "agent": "sova", "ability": "recon",
                "howto": "ยืนชิดกล่อง เล็งขอบหลังคา", "pin": {"from": [0.2, 0.3], "to": [0.5, 0.6]},
            })
        finally:
            clipgrab.render = original
        self.assertEqual(code, 200, result)
        rel = result["rel"]
        self.assertTrue(rel.endswith(".webp"), "ภาพเคลื่อนไหวล้วน — ตัวไลน์อัพคือ webp")
        self.assertEqual((HERE / "lineups" / rel).read_bytes(), ANIM)
        self.assertFalse((HERE / "lineups" / rel).with_suffix(".gif").exists(), "ไม่มีไฟล์พ่วง")
        self.assertEqual(result["pin"], "full")
        meta = meta_mod.load(HERE / "meta.json")[rel]
        self.assertEqual(meta["howto"], "ยืนชิดกล่อง เล็งขอบหลังคา")
        self.assertEqual(meta["ability"], "recon")
        saved = json.loads((Path(self.clip.folder) / "clip.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["plan"], clipgrab.clean_plan(plan), "เปิดลิงก์เดิมได้แผนเดิมกลับมา")

    def test_take_rejects_long_plan(self) -> None:
        original = clipgrab.render
        clipgrab.render = self.fake_render
        try:
            code, result = self.post("/api/source/take", {
                "uid": self.uid, "plan": {"start": 376, "end": 400, "parts": []}, "map": "sunset"})
        finally:
            clipgrab.render = original
        self.assertEqual(code, 400)
        self.assertIn("ภาพเคลื่อนไหว", result["error"])
        self.assertFalse(list((HERE / "lineups").glob("sunset/**/*.webp")))


if __name__ == "__main__":
    unittest.main()

"""ทดสอบ tracker.gg เป็นแหล่งไลน์อัพที่สาม (tools/lineup_sources.py "tg" + tools/web_manage.py).

- แปลงรายการดิบของเว็บเป็นรูปแบบกลาง (uid tg:<id>, ฝั่ง all = ทั้งสองฝั่ง, ตัดใบไม่มีวิดีโอ)
- /api/tracker/push: ต้องมีรหัสลับของ bookmarklet + Origin จาก tracker.gg เท่านั้น · ตอบ CORS/preflight
- เปิดใบเป็นวิดีโอ (open_stream ถูกแทนด้วยของปลอม — ไม่ต่อเน็ต) แล้วกดเก็บพร้อมแผนตัดต่อ
ข้อมูลทั้งหมดสังเคราะห์ ไม่แตะคลังจริง · รัน: python -m unittest discover -s tests -p "test_*.py"
"""

import json
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402

from lineupmaster import clipgrab  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402

web_manage = shared.web_manage
source_mod = web_manage.source_mod
HERE = shared.HERE
TOKEN = "tok"
ORIGIN = "https://tracker.gg"
ANIM = b"RIFF\x1e\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x12" + b"\x00" * 10


def row(id_, **over):
    attrs = {"map": "Ascent", "agent": "Sova", "ability": "recon bolt", "side": "attack", "location": "10.5,20"}
    attrs.update(over.pop("attributes", {}))
    base = {"id": id_, "urlSlug": f"slug-{id_}", "title": "A Main to A Site", "description": "ยืนชิดกล่อง",
            "videoUrl": f"vid{id_}", "previewImageUrl": f"https://img/{id_}.jpg", "score": 5, "views": 9,
            "dateCreated": "2026-01-01", "attributes": attrs, "extra": "ทิ้ง"}
    base.update(over)
    return base


class TrackerSourceTest(unittest.TestCase):
    def test_normalise(self) -> None:
        entry = source_mod._norm_tg(row("g1"))
        self.assertEqual((entry["uid"], entry["src"], entry["a"], entry["m"]), ("tg:g1", "tg", "sova", "ascent"))
        self.assertEqual((entry["side"], entry["both"], entry["st"]), ("attack", False, "A"))
        self.assertEqual((entry["video"], entry["thumb"], entry["desc"]), ("vidg1", "https://img/g1.jpg", "ยืนชิดกล่อง"))
        self.assertEqual((entry["n"], entry["xy"]), (0, (10.5, 20.0)))
        self.assertEqual(source_mod.ability_tag(entry["ab"]), "recon")

    def test_side_all_and_missing_location_and_defense(self) -> None:
        both = source_mod._norm_tg(row("g2", attributes={"side": "all", "location": "-1,-1"}))
        self.assertTrue(both["both"])
        self.assertIsNone(both["xy"])
        self.assertEqual(source_mod._norm_tg(row("g3", attributes={"side": "defense"}))["side"], "defense")

    def test_rows_without_video_are_dropped(self) -> None:
        self.assertIsNone(source_mod._norm_tg(row("g4", videoUrl="")))
        self.assertIsNone(source_mod.tg_clean(row("g4", videoUrl=None)))
        self.assertIsNone(source_mod.tg_clean("junk"))

    def test_clean_keeps_only_known_fields(self) -> None:
        cleaned = source_mod.tg_clean(row("g5"))
        self.assertNotIn("extra", cleaned)
        self.assertEqual(set(cleaned["attributes"]), {"map", "agent", "ability", "side", "location"})

    def test_registered_with_thumb(self) -> None:
        self.assertIn("tg", source_mod.SOURCES)
        self.assertEqual(source_mod.SOURCES["tg"].thumb(source_mod._norm_tg(row("g6"))), "https://img/g6.jpg")
        self.assertEqual(source_mod.SOURCES["tg"].steps(source_mod._norm_tg(row("g6"))), [])

    def test_stream_url_and_slug(self) -> None:
        self.assertEqual(source_mod.tg_stream_url("abc"),
                         "https://customer-9h7e8ahl6hivmjb6.cloudflarestream.com/abc/manifest/video.m3u8")
        self.assertEqual(source_mod.tg_slug("../Sova X"), "sova-x")
        self.assertEqual(source_mod.tg_slug("///"), "")


class TrackerWebTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(HERE, ignore_errors=True)
        shared.make(HERE, {shared.A: b"a"})
        shutil.copy2(shared.REPO / "aliases.yaml", HERE / "aliases.yaml")
        self.store = web_manage.Store()
        self.source = web_manage.SourceBrowser()
        self.key = source_mod.tg_key()
        # แคตตาล็อกเอาแค่ tracker.gg — ไม่ให้เทสต์ไปต่อเน็ตหา ValoLineups/ValCompanion
        self.real_fetch = source_mod.fetch_catalog
        source_mod.fetch_catalog = lambda force=False: self.real_fetch(force, ("tg",))
        handler = partial(web_manage.Handler, store=self.store, source=self.source, token=TOKEN)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self) -> None:
        source_mod.fetch_catalog = self.real_fetch
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, method: str, path: str, body=None, headers: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def push(self, items, key=None, origin=ORIGIN, agent="sova"):
        headers = {"Content-Type": "text/plain"}
        if origin:
            headers["Origin"] = origin
        return self.call("POST", f"/api/tracker/push?k={key or self.key}", {"agent": agent, "items": items}, headers)

    def catalog(self) -> list[dict]:
        _c, _h, raw = self.call("GET", f"/api/source/catalog?t={TOKEN}")
        return [l for l in json.loads(raw)["lineups"] if l["src"] == "tg"]

    # -- รับรายการจาก bookmarklet ----------------------------------------
    def test_key_is_persistent(self) -> None:
        self.assertEqual(source_mod.tg_key(), self.key)
        self.assertGreaterEqual(len(self.key), 16)

    def test_push_stores_and_shows_in_catalog(self) -> None:
        self.assertEqual(self.catalog(), [])
        code, headers, raw = self.push([row("g1"), row("g2", attributes={"side": "all"}), row("g3", videoUrl="")])
        self.assertEqual(code, 200, raw)
        self.assertEqual(json.loads(raw), {"ok": True, "agent": "sova", "count": 2})
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        self.assertEqual(sorted(l["uid"] for l in self.catalog()), ["tg:g1", "tg:g2"])
        self.assertTrue((HERE / ".cache" / "tracker" / "guides-sova.json").is_file())
        # ส่งซ้ำ = ทับทั้งชุดของตัวละครนั้น
        self.push([row("g9")])
        self.assertEqual([l["uid"] for l in self.catalog()], ["tg:g9"])

    def test_push_refused_without_key_or_from_other_origin(self) -> None:
        self.assertEqual(self.push([row("g1")], key="wrong")[0], 403)
        self.assertEqual(self.push([row("g1")], origin="https://evil.example")[0], 403)
        self.assertEqual(self.catalog(), [])

    def test_push_rejects_garbage(self) -> None:
        self.assertEqual(self.push([])[0], 400)
        self.assertEqual(self.push([row("g1")], agent="///")[0], 400)
        code, _h, _b = self.call("POST", f"/api/tracker/push?k={self.key}", None, {"Origin": ORIGIN})
        self.assertEqual(code, 413, "ไม่มีเนื้อหา")

    def test_ping_and_preflight(self) -> None:
        code, headers, raw = self.call("GET", f"/api/tracker/ping?k={self.key}", None, {"Origin": ORIGIN})
        self.assertEqual((code, json.loads(raw)["app"]), (200, "LineupMaster"))
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(self.call("GET", "/api/tracker/ping?k=nope", None, {"Origin": ORIGIN})[0], 403)

        code, headers, _raw = self.call("OPTIONS", "/api/tracker/push", None, {
            "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(code, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        self.assertEqual(self.call("OPTIONS", "/api/tracker/push", None, {"Origin": "https://evil.example"})[0], 404)
        self.assertEqual(self.call("OPTIONS", "/api/save", None, {"Origin": ORIGIN})[0], 404)

    def test_status_and_bookmarklet_need_page_token(self) -> None:
        self.assertEqual(self.call("GET", "/api/tracker/status")[0], 403)
        self.push([row("g1")])
        code, _h, raw = self.call("GET", f"/api/tracker/status?t={TOKEN}")
        data = json.loads(raw)
        self.assertEqual((code, data["agents"][0]["agent"], data["agents"][0]["count"]), (200, "sova", 1))
        href = data["bookmarklet"]
        self.assertTrue(href.startswith("javascript:"))
        code_text = urllib.parse.unquote(href[len("javascript:"):])
        self.assertIn(self.key, code_text)
        self.assertNotIn("__KEY__", code_text)
        self.assertNotIn("__PORT_", code_text)
        self.assertIn("8760", code_text)

    # -- เปิดเป็นวิดีโอ + เก็บเข้าคลัง ------------------------------------
    def fake_stream(self, url, root, key, **kwargs):
        self.opened = (url, key, kwargs)
        folder = Path(root) / ".cache" / "clips" / key
        folder.mkdir(parents=True, exist_ok=True)
        return clipgrab.Clip(vid=key, title=kwargs["title"], chapter=kwargs["title"], start=0.0, end=12.0,
                             folder=str(folder), proxy_offset=0.0, motion_times=[0.0, 0.1], motion=[0.0, 1.0],
                             coarse_times=[0.0, 0.5], coarse=[1.0])

    def fake_render(self, clip, plan):
        clipgrab.clean_plan(plan)
        out = Path(clip.folder) / "anim-plan-test.webp"
        out.write_bytes(ANIM)
        return out

    def test_open_entry_then_take_with_plan(self) -> None:
        self.push([row("g1", description="ยืนชิดกล่อง เล็งขอบหลังคา")])
        original = (clipgrab.open_stream, clipgrab.render)
        clipgrab.open_stream, clipgrab.render = self.fake_stream, self.fake_render
        try:
            code, _h, raw = self.call("POST", f"/api/video/open?t={TOKEN}", {"uid": "tg:g1"},
                                      {"Content-Type": "application/json"})
            self.assertEqual(code, 200, raw)
            opened = json.loads(raw)
            self.assertEqual(opened["entry"]["uid"], "tg:g1", "ยังเป็นใบเดิมของแคตตาล็อก")
            self.assertEqual(opened["howto"], "ยืนชิดกล่อง เล็งขอบหลังคา")
            self.assertEqual((opened["start"], opened["end"], opened["offset"]), (0.0, 12.0, 0.0))
            self.assertEqual(self.opened[0], source_mod.tg_stream_url("vidg1"))
            self.assertEqual((self.opened[1], self.opened[2]["map_"], self.opened[2]["agent"]), ("tg-g1", "ascent", "sova"))

            proxy = Path(HERE / ".cache" / "clips" / "tg-g1" / "proxy.mp4")
            proxy.write_bytes(b"x" * 10)
            self.assertEqual(self.call("GET", f"/api/video/file?uid=tg:g1&t={TOKEN}")[0], 200)

            body = {"uid": "tg:g1", "plan": {"start": 1, "end": 5, "parts": []}, "name": "A Main",
                    "map": "ascent", "side": "attack", "site": "a", "agent": "sova", "ability": "recon",
                    "howto": "ยืนชิดกล่อง", "pin": {"from": [0.2, 0.3], "to": [0.5, 0.6]}}
            code, _h, raw = self.call("POST", f"/api/source/take?t={TOKEN}", body, {"Content-Type": "application/json"})
        finally:
            clipgrab.open_stream, clipgrab.render = original
        self.assertEqual(code, 200, raw)
        result = json.loads(raw)
        self.assertTrue(result["rel"].endswith(".webp"))
        self.assertEqual(meta_mod.load(HERE / "meta.json")[result["rel"]]["howto"], "ยืนชิดกล่อง")
        taken = source_mod.read_decisions(HERE / "browse.json")["taken"]
        self.assertIn("tg:g1", taken, "ใบจากแคตตาล็อกถูกจดว่าเอาแล้ว")

    def test_open_entry_unknown_or_other_source(self) -> None:
        self.push([row("g1")])
        for uid in ("tg:nope", "vlp:1"):
            code, _h, _raw = self.call("POST", f"/api/video/open?t={TOKEN}", {"uid": uid},
                                       {"Content-Type": "application/json"})
            self.assertEqual(code, 404, uid)


if __name__ == "__main__":
    unittest.main()

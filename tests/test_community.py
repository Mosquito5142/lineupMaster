"""ทดสอบคอมมูนิตี้ (lineupmaster/community.py + tools/community_web.py) กับ Supabase จำลองในหน่วยความจำ.

- ล็อกอิน PKCE · ต่ออายุ token เอง · token เสีย = ต้องล็อกอินใหม่
- แชร์ → เพื่อนเห็น → เอาเข้าคลัง (รูป+หมุด+สกิล+cid) → F7/F8 ในเกม → หน้าเว็บส่งโหวตที่ค้าง
- ใบที่ดึงมาจากเว็บอื่นแชร์ไม่ได้ แม้ถูกเปลี่ยนชื่อไปแล้ว

รัน: python -m unittest discover -s tests -p "test_*.py"   (จากรากโปรเจกต์)
"""

import io
import json
import shutil
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_web_merge as shared  # noqa: E402

from community_web import CommunityWeb  # noqa: E402
from lineupmaster import community as community_mod  # noqa: E402
from lineupmaster import library as lib  # noqa: E402
from lineupmaster import meta as meta_mod  # noqa: E402
from lineupmaster.browser import Browser  # noqa: E402

web_manage = shared.web_manage
HERE = shared.HERE
URL = "https://demo.supabase.co"

MINE = "ascent/attack/sova/A/ทำเอง.png"
WEB = "ascent/attack/kayo/A/จากเว็บ.png"


class FakeSupabase:
    """พอให้ community.py คุยได้: auth (pkce/refresh), rest (lineups/votes/lineup_feed), storage."""

    def __init__(self) -> None:
        self.users = {"code-a": "user-a", "code-b": "user-b"}
        self.tokens: dict[str, str] = {}
        self.lineups: list[dict] = []
        self.votes: dict[tuple, int] = {}
        self.objects: dict[str, bytes] = {}
        self.n = 0

    def _user(self, uid):
        return {"id": uid, "user_metadata": {"full_name": uid.upper()}}

    def _session(self, uid):
        self.n += 1
        token = f"tok{self.n}"
        self.tokens[token] = uid
        return {"access_token": token, "refresh_token": f"ref-{uid}", "expires_in": 3600,
                "user": self._user(uid)}

    def __call__(self, request, timeout=None):
        url = urllib.parse.urlparse(request.full_url)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        body = json.loads(request.data) if request.data and request.headers.get("Content-type") == "application/json" else None
        method = request.get_method()
        path = url.path
        uid = self.tokens.get(request.headers.get("Authorization", "").removeprefix("Bearer "))

        def ok(data):
            return io.BytesIO(json.dumps(data).encode() if data is not None else b"")

        def fail(code):
            raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(b"{}"))

        if path == "/auth/v1/token":
            if query["grant_type"] == "pkce":
                return ok(self._session(self.users[body["auth_code"]]))
            if query["grant_type"] == "refresh_token":
                return ok(self._session(body["refresh_token"].removeprefix("ref-")))
        if path.startswith("/storage/v1/object/public/"):
            return io.BytesIO(self.objects[path.split("/lineups/", 1)[1]])
        if uid is None:
            fail(401)
        if path.startswith("/storage/v1/object/lineups/"):
            name = urllib.parse.unquote(path.split("/lineups/", 1)[1])
            if not name.startswith(uid + "/"):
                fail(403)
            self.objects[name] = request.data
            return ok({})
        if path == "/rest/v1/lineups" and method == "POST":
            row = dict(body, id=f"L{len(self.lineups) + 1}", owner=uid)
            self.lineups.append(row)
            return ok([row])
        if path == "/rest/v1/lineups":
            return ok([r for r in self.lineups if r["owner"] == query["owner"][3:] and r["sha1"] == query["sha1"][3:]])
        if path == "/rest/v1/lineup_feed":
            rows = []
            for r in self.lineups:
                if "agent" in query and r["agent"] != query["agent"][3:]:
                    continue
                works = sum(1 for (lid, _u), v in self.votes.items() if lid == r["id"] and v == 1)
                broken = sum(1 for (lid, _u), v in self.votes.items() if lid == r["id"] and v == -1)
                rows.append(dict(r, works=works, broken=broken, score=works - broken))
            return ok(rows)
        if path == "/rest/v1/votes" and method == "GET":
            return ok([{"lineup_id": lid, "value": v} for (lid, u), v in self.votes.items() if u == uid])
        if path == "/rest/v1/votes" and method == "POST":
            assert body["user_id"] == uid
            self.votes[(body["lineup_id"], uid)] = body["value"]
            return ok(None)
        if path == "/rest/v1/votes" and method == "DELETE":
            self.votes.pop((query["lineup_id"][3:], uid), None)
            return ok(None)
        fail(404)


class CommunityTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(HERE, ignore_errors=True)
        shared.make(HERE, {MINE: b"my own png", WEB: b"scraped png"})
        shutil.copy2(shared.REPO / "aliases.yaml", HERE / "aliases.yaml")
        (HERE / "positions.json").write_text(json.dumps({
            MINE: {"from": [0.1, 0.2], "to": [0.3, 0.4]}, WEB: {"from": [0.5, 0.5]}}), encoding="utf-8")
        (HERE / "browse.json").write_text(json.dumps({"taken": {"vlp:9": WEB}, "skipped": []}),
                                          encoding="utf-8")
        (HERE / "community.json").write_text(json.dumps({"url": URL, "anon_key": "anon"}), encoding="utf-8")
        self.fake = FakeSupabase()
        self.clock = [1000.0]
        self.store = web_manage.Store()
        self.web = self.as_user("code-a")

    def as_user(self, code) -> CommunityWeb:
        client = community_mod.Community(HERE, opener=self.fake, now=lambda: self.clock[0])
        client.login_url("http://127.0.0.1:8760/community/callback")
        client.finish_login(code)
        return CommunityWeb(self.store, HERE, client)

    def test_login_saves_session_and_name(self) -> None:
        self.assertEqual(self.web.state()["user"], {"id": "user-a", "name": "USER-A"})
        self.assertFalse((HERE / ".community" / "pkce.json").exists())

    def test_expired_token_refreshes_itself(self) -> None:
        before = self.web.client.session["access_token"]
        self.clock[0] += 7200
        self.web.feed(None, None)
        self.assertNotEqual(self.web.client.session["access_token"], before)

    def test_logged_out_is_401_style_error(self) -> None:
        self.web.logout()
        with self.assertRaises(community_mod.NotLoggedIn):
            self.web.feed(None, None)

    def test_share_blocks_web_images_even_after_rename(self) -> None:
        with self.store.lock:
            renamed = lib.rename(HERE, self.store.cfg.lineups_dir, HERE / "lineups" / WEB, "ชื่อใหม่").path
            self.store.reload()
        new_rel = lib.rel_of(self.store.cfg.lineups_dir, renamed)
        result = self.web.share([MINE, new_rel])
        self.assertEqual(result["shared"], [MINE])
        self.assertIn("ลิขสิทธิ์", result["skipped"][0]["why"])
        self.assertEqual(len(self.fake.lineups), 1)
        row = self.fake.lineups[0]
        self.assertEqual((row["stand_x"], row["target_y"], row["owner_name"]), (0.1, 0.4, "USER-A"))
        self.assertTrue(meta_mod.load(HERE / "meta.json")[MINE]["cid"], "ใบที่แชร์แล้วผูก cid ไว้")
        self.assertEqual(self.web.share([MINE])["skipped"][0]["why"], "อยู่บนคอมมูนิตี้แล้ว")

    def test_friend_takes_votes_in_game_and_web_syncs(self) -> None:
        self.web.share([MINE])
        cid = self.fake.lineups[0]["id"]
        # เพื่อน (B) เปิดคลังของเขา — จำลองด้วยการลบใบเดิมออกจากคลังนี้ก่อน
        with self.store.lock:
            lib.remove(HERE, self.store.cfg.lineups_dir, HERE / "lineups" / MINE)
            self.store.reload()
        friend = self.as_user("code-b")
        rel = friend.take(cid)["rel"]
        self.assertTrue((HERE / "lineups" / rel).is_file())
        entry = meta_mod.load(HERE / "meta.json")[rel]
        self.assertEqual(entry["cid"], cid)
        self.assertEqual(json.loads((HERE / "positions.json").read_text(encoding="utf-8"))[rel]["to"], [0.3, 0.4])
        self.assertEqual(friend.take(cid)["message"], "มีใบนี้ในคลังอยู่แล้ว")

        # ในเกม: เลือกใบนั้นแล้วกด F7 (ใช้ได้จริง) — โปรแกรมหลักจดลง meta เฉยๆ ไม่ต่อเน็ต
        game = Browser(HERE / "last-view.json", HERE / "positions.json", HERE / "callouts.json",
                       HERE / "meta.json")
        game.set_lineups(self.store.lineups)
        game.reload_meta()
        game.map, game.side, game.map_view = "ascent", "attack", False
        game.f_agent = "sova"                                # ใบที่เอามาจากเพื่อนเป็นใบเดียวของโซวา
        self.assertIn("✓", game.vote_works())
        self.assertEqual(self.fake.votes, {}, "ยังไม่ส่งจนกว่าจะเปิดหน้าเว็บ")

        items = friend.feed(None, None)["items"]           # เปิดหน้าเว็บ = ส่งโหวตที่ค้าง
        self.assertEqual(self.fake.votes, {(cid, "user-b"): 1})
        self.assertEqual((items[0]["works"], items[0]["mine"], items[0]["have"]), (1, 1, rel))
        self.assertEqual(community_mod.cached_scores(HERE)[cid], (1, 0), "แคชคะแนนให้โปรแกรมหลัก")

        game.reload_meta()
        game.toggle_flag()                                  # F8 บนใบคอมมูนิตี้ = ใช้ไม่ได้
        friend.sync()
        self.assertEqual(self.fake.votes, {(cid, "user-b"): -1})
        game.toggle_flag()                                  # เอาธงออก = ถอนเสียง
        friend.sync()
        self.assertEqual(self.fake.votes, {})

    def test_unsent_votes_stay_queued_after_network_error(self) -> None:
        self.web.share([MINE])
        cid = self.fake.lineups[0]["id"]
        with self.store.lock:
            meta_mod.set_fields(self.store.fresh_meta(), MINE, vote=1)
            meta_mod.save(HERE / "meta.json", self.store.meta)
        broken = community_mod.Community(HERE, opener=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")),
                                         now=lambda: self.clock[0])
        with self.assertRaises(community_mod.CommunityError):
            CommunityWeb(self.store, HERE, broken).sync()
        self.assertEqual(self.web.client.pending(meta_mod.load(HERE / "meta.json")), {cid: 1})
        self.web.sync()
        self.assertEqual(self.web.client.pending(meta_mod.load(HERE / "meta.json")), {})


if __name__ == "__main__":
    unittest.main()

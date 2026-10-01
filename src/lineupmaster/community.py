"""คอมมูนิตี้: แชร์ไลน์อัพให้เพื่อน + คะแนน "ใช้ได้จริง" ผ่าน Supabase (ฟรี).

คุยกับ Supabase ด้วย REST ล้วน (``urllib``) ไม่เพิ่ม dependency — ใช้แค่ 3 ส่วนของมัน:

    /auth/v1     ล็อกอินด้วย Discord (OAuth แบบ PKCE — ไม่ต้องมีรหัสลับฝั่งโปรแกรม)
    /rest/v1     ตาราง lineups, votes และ view lineup_feed (ดู docs/community/schema.sql)
    /storage/v1  รูปไลน์อัพใน bucket "lineups" ที่ <uid>/<ชื่อ>.png

ไฟล์ที่เกี่ยวข้อง (อยู่ข้าง exe เหมือนข้อมูลอื่น)::

    community.json          {"url": ..., "anon_key": ...} ของโปรเจกต์ Supabase — แจกไปกับโปรแกรมได้
                            (anon key ไม่ใช่ความลับ สิทธิ์จริงคุมด้วย RLS ในฐานข้อมูล)
    .community/session.json  token ของคนที่ล็อกอินบนเครื่องนี้ — **ห้ามแจก** (build --release ตัดทิ้ง)
    .community/sent.json     โหวตที่ส่งขึ้นไปแล้ว {cid: ค่า} — ใช้หาว่าโหวตไหนยังค้างส่ง
    .community/scores.json   คะแนนล่าสุด {cid: [ใช้ได้, ใช้ไม่ได้]} ให้โปรแกรมหลักโชว์ (ไม่ต่อเน็ตเอง)

โปรแกรมหลัก (เกม) **ไม่ต่อเน็ต** — กด F7/F8 แค่จดลง meta.json แล้วหน้าเว็บส่งให้ตอนเปิด
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "lineups"
TIMEOUT = 30


class CommunityError(Exception):
    """ข้อผิดพลาดที่โชว์ผู้ใช้ได้ตรงๆ (ภาษาไทย)."""


class NotLoggedIn(CommunityError):
    pass


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


class Community:
    def __init__(self, root: Path, opener=None, now=time.time) -> None:
        self.root = root
        self.dir = root / ".community"
        self._open = opener or urllib.request.urlopen
        self._now = now
        cfg = _read(root / "community.json")
        self.url = str(cfg.get("url") or "").rstrip("/")
        self.key = str(cfg.get("anon_key") or "")

    # -- ตั้งค่า / สถานะ -------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def configure(self, url: str, anon_key: str) -> None:
        url = str(url or "").strip().rstrip("/")
        if not url.startswith("https://"):
            raise CommunityError("URL ของ Supabase ต้องขึ้นต้นด้วย https://")
        if not str(anon_key or "").strip():
            raise CommunityError("ต้องใส่ anon key ด้วย")
        _write(self.root / "community.json", {"url": url, "anon_key": anon_key.strip()})
        self.url, self.key = url, anon_key.strip()

    @property
    def session(self) -> dict:
        return _read(self.dir / "session.json")

    def user(self) -> dict | None:
        """คนที่ล็อกอินอยู่ {id, name} — None = ยังไม่ล็อกอิน."""
        user = self.session.get("user")
        if not isinstance(user, dict) or not user.get("id"):
            return None
        meta = user.get("user_metadata") or {}
        name = (meta.get("custom_claims") or {}).get("global_name") or meta.get("full_name") \
            or meta.get("name") or meta.get("user_name") or user.get("email") or "?"
        return {"id": user["id"], "name": str(name)}

    def logout(self) -> None:
        (self.dir / "session.json").unlink(missing_ok=True)

    # -- ล็อกอิน Discord (PKCE) -----------------------------------------
    def login_url(self, redirect: str) -> str:
        """ลิงก์ให้เปิดในเบราว์เซอร์ — Discord ถามยืนยัน แล้วเด้งกลับ ``redirect?code=...``."""
        self._need_config()
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        _write(self.dir / "pkce.json", {"verifier": verifier})
        query = urllib.parse.urlencode({
            "provider": "discord", "redirect_to": redirect,
            "code_challenge": challenge, "code_challenge_method": "s256",
        })
        return f"{self.url}/auth/v1/authorize?{query}"

    def finish_login(self, code: str) -> dict:
        verifier = _read(self.dir / "pkce.json").get("verifier")
        if not verifier:
            raise CommunityError("ไม่เจอขั้นตอนล็อกอินที่ค้างไว้ — กดล็อกอินใหม่อีกครั้ง")
        data = self._call("POST", "/auth/v1/token?grant_type=pkce",
                          {"auth_code": code, "code_verifier": verifier}, auth=False)
        (self.dir / "pkce.json").unlink(missing_ok=True)
        self._save_session(data)
        return self.user() or {}

    def _save_session(self, data: dict) -> None:
        if not data.get("access_token"):
            raise CommunityError("ล็อกอินไม่สำเร็จ (ไม่ได้ token กลับมา)")
        expires = data.get("expires_at") or (self._now() + int(data.get("expires_in") or 3600))
        _write(self.dir / "session.json", {
            "access_token": data["access_token"], "refresh_token": data.get("refresh_token"),
            "expires_at": expires, "user": data.get("user") or self.session.get("user"),
        })

    def _token(self) -> str:
        session = self.session
        if not session.get("access_token"):
            raise NotLoggedIn("ยังไม่ได้ล็อกอิน — กด 'ล็อกอินด้วย Discord' ก่อน")
        if float(session.get("expires_at") or 0) - 60 < self._now():
            if not session.get("refresh_token"):
                raise NotLoggedIn("หมดเวลาล็อกอิน — ล็อกอินใหม่อีกครั้ง")
            try:
                data = self._call("POST", "/auth/v1/token?grant_type=refresh_token",
                                  {"refresh_token": session["refresh_token"]}, auth=False)
            except CommunityError as error:
                self.logout()
                raise NotLoggedIn("หมดเวลาล็อกอิน — ล็อกอินใหม่อีกครั้ง") from error
            self._save_session(data)
            session = self.session
        return session["access_token"]

    # -- ตัวยิงคำขอ ------------------------------------------------------
    def _need_config(self) -> None:
        if not self.configured:
            raise CommunityError("ยังไม่ได้ตั้งค่าเซิร์ฟเวอร์คอมมูนิตี้ (URL + anon key ของ Supabase)")

    def _call(self, method: str, path: str, body=None, auth: bool = True,
              headers: dict | None = None, raw: bytes | None = None, content_type: str = ""):
        self._need_config()
        head = {"apikey": self.key, "Accept": "application/json"}
        head["Authorization"] = f"Bearer {self._token() if auth else self.key}"
        data = None
        if raw is not None:
            data = raw
            head["Content-Type"] = content_type
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            head["Content-Type"] = "application/json"
        head.update(headers or {})
        request = urllib.request.Request(self.url + path, data=data, headers=head, method=method)
        try:
            with self._open(request, timeout=TIMEOUT) as response:
                text = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            if error.code == 401:
                raise NotLoggedIn("เซิร์ฟเวอร์ไม่รับการล็อกอินนี้ — ล็อกอินใหม่อีกครั้ง") from error
            raise CommunityError(f"เซิร์ฟเวอร์ตอบ {error.code}: {detail}") from error
        except (urllib.error.URLError, OSError) as error:
            raise CommunityError(f"ต่อเซิร์ฟเวอร์คอมมูนิตี้ไม่ได้ ({error})") from error
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    def _uid(self) -> str:
        user = self.user()
        if user is None:
            raise NotLoggedIn("ยังไม่ได้ล็อกอิน — กด 'ล็อกอินด้วย Discord' ก่อน")
        return user["id"]

    # -- ไลน์อัพ --------------------------------------------------------
    def feed(self, agent: str | None = None, map_: str | None = None) -> list[dict]:
        """ไลน์อัพทั้งหมด (ตามตัวกรอง) เรียงคะแนนมากไปน้อย พร้อม ``mine`` = เสียงของเราเอง."""
        query = {"select": "*", "order": "score.desc,created_at.desc"}
        if agent:
            query["agent"] = f"eq.{agent}"
        if map_:
            query["map"] = f"eq.{map_}"
        items = self._call("GET", "/rest/v1/lineup_feed?" + urllib.parse.urlencode(query)) or []
        mine = self.my_votes()
        for item in items:
            item["mine"] = mine.get(item["id"], 0)
            item["image_url"] = self.image_url(item["image"])
        self._cache_scores(items)
        return items

    def my_votes(self) -> dict[str, int]:
        uid = self._uid()
        rows = self._call("GET", f"/rest/v1/votes?select=lineup_id,value&user_id=eq.{uid}") or []
        return {row["lineup_id"]: int(row["value"]) for row in rows}

    def image_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{BUCKET}/{urllib.parse.quote(path)}"

    def download_image(self, path: str) -> bytes:
        request = urllib.request.Request(self.image_url(path), headers={"apikey": self.key})
        try:
            with self._open(request, timeout=TIMEOUT) as response:
                return response.read()
        except (urllib.error.URLError, OSError) as error:
            raise CommunityError(f"โหลดรูปไม่ได้ ({error})") from error

    def share(self, fields: dict, image: bytes, suffix: str) -> dict:
        """อัปโหลดรูปแล้วเพิ่มแถว — คืนแถวที่สร้าง (มี id) · รูปเดิมของคนเดิมซ้ำ = เอาแถวเดิม."""
        uid = self._uid()
        sha1 = hashlib.sha1(image).hexdigest()
        existing = self._call("GET", f"/rest/v1/lineups?select=*&owner=eq.{uid}&sha1=eq.{sha1}") or []
        if existing:
            return existing[0]
        path = f"{uid}/{sha1}{suffix.lower()}"
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".gif": "image/gif"}.get(suffix.lower(), "application/octet-stream")
        self._call("POST", f"/storage/v1/object/{BUCKET}/{path}", raw=image, content_type=ctype,
                   headers={"x-upsert": "true"})
        row = dict(fields, image=path, sha1=sha1, owner_name=(self.user() or {}).get("name", ""))
        created = self._call("POST", "/rest/v1/lineups", row, headers={"Prefer": "return=representation"})
        return created[0] if isinstance(created, list) and created else created

    def vote(self, lineup_id: str, value: int) -> None:
        """+1 ใช้ได้จริง / -1 ใช้ไม่ได้ / 0 = ถอนเสียง."""
        uid = self._uid()
        if value == 0:
            self._call("DELETE", f"/rest/v1/votes?lineup_id=eq.{lineup_id}&user_id=eq.{uid}")
            return
        self._call("POST", "/rest/v1/votes?on_conflict=lineup_id,user_id",
                   {"lineup_id": lineup_id, "user_id": uid, "value": 1 if value > 0 else -1},
                   headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    # -- คิวโหวตจากในเกม + แคชคะแนนให้โปรแกรมหลัก -----------------------
    def pending(self, meta: dict) -> dict[str, int]:
        """โหวตที่ยังไม่ได้ส่ง {cid: ค่า (0 = ถอน)} — เทียบ meta.json กับที่ส่งไปแล้ว."""
        wanted = {e["cid"]: int(e.get("vote") or 0) for e in meta.values() if e.get("cid")}
        sent = {k: int(v) for k, v in _read(self.dir / "sent.json").items()}
        return {cid: value for cid, value in wanted.items() if sent.get(cid, 0) != value}

    def sync_votes(self, meta: dict) -> int:
        """ส่งโหวตที่ค้าง — ส่งไม่สำเร็จใบไหนก็ค้างไว้รอบหน้า (ไม่หาย)."""
        sent = _read(self.dir / "sent.json")
        done = 0
        for cid, value in self.pending(meta).items():
            self.vote(cid, value)
            sent[cid] = value
            _write(self.dir / "sent.json", sent)
            done += 1
        return done

    def _cache_scores(self, items: list[dict]) -> None:
        scores = _read(self.dir / "scores.json")
        seen = _read(self.dir / "feed.json")
        for item in items:
            scores[item["id"]] = [int(item.get("works") or 0), int(item.get("broken") or 0)]
            seen[item["id"]] = str(item.get("created_at") or "")
        _write(self.dir / "scores.json", scores)
        _write(self.dir / "feed.json", seen)     # หน้าเข้าโปรแกรมนับ "ใหม่จากเพื่อน" จากไฟล์นี้


def cached_feed(root: Path) -> dict[str, str]:
    """ไลน์อัพบนคอมมูนิตี้ที่เคยเห็นล่าสุด {id: created_at (ISO)} — ไม่ต่อเน็ต."""
    return {k: str(v) for k, v in _read(root / ".community" / "feed.json").items()}


def cached_scores(root: Path) -> dict[str, tuple[int, int]]:
    """คะแนนล่าสุดที่หน้าเว็บดึงมา — ให้โปรแกรมหลักอ่าน (ไม่ต่อเน็ตเอง)."""
    out = {}
    for cid, pair in _read(root / ".community" / "scores.json").items():
        if isinstance(pair, list) and len(pair) == 2:
            out[cid] = (int(pair[0]), int(pair[1]))
    return out

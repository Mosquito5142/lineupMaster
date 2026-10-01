"""แท็บ "คอมมูนิตี้" ของหน้าเว็บ — ต่อคลังในเครื่องเข้ากับ Supabase (ตัวคุยจริงอยู่ที่ lineupmaster/community.py).

แยกจาก web_manage.py เพราะทุกคำสั่งตรงนี้ต่อเน็ต (ช้าได้หลายวินาที) — **ห้ามถือล็อกของ Store ระหว่างรอเน็ต**
ไม่งั้นหน้าเว็บทั้งหน้าค้างตาม ถือล็อกเฉพาะตอนแตะไฟล์ในคลังเท่านั้น

กติกาลิขสิทธิ์: ใบที่เอามาจากเว็บไลน์อัพอื่น (browse.json → taken ตามชื่อล่าสุดใน changes.json) **แชร์ไม่ได้**
แชร์ได้เฉพาะรูปที่ผู้ใช้ทำเอง
"""

from __future__ import annotations

from pathlib import Path

import lineup_sources as source_mod
from lineupmaster import community as community_mod
from lineupmaster import journal
from lineupmaster import library as lib
from lineupmaster import meta as meta_mod
from lineupmaster import positions as pos_mod
from lineupmaster.browser import SITES


class CommunityWeb:
    def __init__(self, store, root: Path, client: community_mod.Community | None = None) -> None:
        self.store = store
        self.root = root
        self.client = client or community_mod.Community(root)

    # -- สถานะ / ตั้งค่า / ล็อกอิน --------------------------------------
    def state(self) -> dict:
        return {"configured": self.client.configured, "url": self.client.url,
                "user": self.client.user() if self.client.configured else None}

    def configure(self, body: dict) -> dict:
        self.client.configure(body.get("url"), body.get("anon_key"))
        return self.state()

    def login(self, redirect: str) -> dict:
        return {"url": self.client.login_url(redirect)}

    def finish_login(self, code: str) -> dict:
        return self.client.finish_login(code)

    def logout(self) -> dict:
        self.client.logout()
        return self.state()

    # -- ดู / เอาเข้าคลัง ------------------------------------------------
    def _local_cids(self) -> dict[str, str]:
        with self.store.lock:
            meta = self.store.fresh_meta()
        return {entry["cid"]: rel for rel, entry in meta.items() if entry.get("cid")}

    def feed(self, agent: str | None, map_: str | None) -> dict:
        self.sync()                               # โหวตที่ค้างจากในเกม ส่งก่อนดึงคะแนนใหม่
        items = self.client.feed(agent or None, map_ or None)
        have = self._local_cids()
        user = self.client.user() or {}
        for item in items:
            item["have"] = have.get(item["id"])
            item["own"] = item.get("owner") == user.get("id")
        return {"items": items, "user": user}

    def take(self, lineup_id: str) -> dict:
        """เอาใบของเพื่อนเข้าคลัง: รูป + หมุดยืน/ตก + แท็กสกิล + ผูก cid ไว้ให้โหวตย้อนกลับได้."""
        have = self._local_cids()
        if lineup_id in have:
            return {"rel": have[lineup_id], "message": "มีใบนี้ในคลังอยู่แล้ว"}
        rows = [r for r in self.client.feed() if r["id"] == lineup_id]
        if not rows:
            raise KeyError("ไม่เจอไลน์อัพนี้บนคอมมูนิตี้ (อาจถูกลบไปแล้ว)")
        row = rows[0]
        image = self.client.download_image(row["image"])
        suffix = Path(row["image"]).suffix or ".png"

        with self.store.lock:
            store = self.store
            if row["map"] not in set(store.cfg.aliases.get("maps") or {}):
                raise ValueError(f"แมพ {row['map']} ไม่มีในคลังเรา")
            temp = self.root / ".cache" / f"community-take{suffix}"
            temp.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(image)
            site = str(row.get("site") or "a").lower()
            result = lib.add(store.cfg.lineups_dir, temp, row["map"], row["side"],
                             site if site in SITES else "a", row["title"], row["agent"], move_file=True)
            rel = lib.rel_of(store.cfg.lineups_dir, result.path)
            if row.get("note"):
                result.path.with_suffix(".txt").write_text(row["note"], encoding="utf-8")
            store.reload()
            if row.get("stand_x") is not None:
                target = [row["target_x"], row["target_y"]] if row.get("target_x") is not None else None
                store.set_pin(rel, [row["stand_x"], row["stand_y"]], target)
            meta_mod.set_fields(store.fresh_meta(), rel, ability=row.get("ability"), cid=row["id"])
            meta_mod.save(self.root / "meta.json", store.meta)
            store.reload()
        return {"rel": rel, "message": f"เอาเข้าคลังแล้ว: {result.path.stem}"}

    # -- แชร์ขึ้นคอมมูนิตี้ ------------------------------------------------
    def from_web(self) -> set[str]:
        """rel ปัจจุบันของใบที่ดึงมาจากเว็บไลน์อัพอื่น — ตามการเปลี่ยนชื่อ/ย้ายใน changes.json ด้วย."""
        taken = source_mod.read_decisions(self.root / "browse.json")["taken"]
        entries = journal.load(self.root)
        out = set()
        for rel in taken.values():
            final = journal.fate(entries, rel)[1]
            if final:
                out.add(final)
        return out

    def share(self, rels: list[str]) -> dict:
        user = self.client.user()
        if user is None:
            raise community_mod.NotLoggedIn("ยังไม่ได้ล็อกอิน — กด 'ล็อกอินด้วย Discord' ก่อน")
        blocked_web = self.from_web()
        shared, skipped = [], []
        for rel in rels:
            with self.store.lock:
                lu = self.store.find(rel)
                pin = self.store.positions.get(rel) or {}
                entry = meta_mod.entry(self.store.fresh_meta(), rel)
            if lu is None:
                skipped.append({"rel": rel, "why": "ไม่เจอในคลัง"})
                continue
            if rel in blocked_web:
                skipped.append({"rel": rel, "why": "รูปจากเว็บไลน์อัพอื่น (ลิขสิทธิ์) — แชร์ได้เฉพาะรูปที่ทำเอง"})
                continue
            if entry.get("cid"):
                skipped.append({"rel": rel, "why": "อยู่บนคอมมูนิตี้แล้ว"})
                continue
            stand = pos_mod.point_of(pin, "from") if pin else None
            if stand is None:
                skipped.append({"rel": rel, "why": "ยังไม่ได้ปักหมุดจุดยืน"})
                continue
            target = pos_mod.point_of(pin, "to")
            fields = {"map": lu.map, "side": lu.side, "site": lu.site or "a", "agent": lu.agent or "sova",
                      "ability": lu.ability, "title": lu.stem, "note": lu.note or "",
                      "stand_x": stand[0], "stand_y": stand[1],
                      "target_x": target[0] if target else None, "target_y": target[1] if target else None}
            row = self.client.share(fields, lu.path.read_bytes(), lu.path.suffix)
            with self.store.lock:
                meta_mod.set_fields(self.store.fresh_meta(), rel, cid=row["id"])
                meta_mod.save(self.root / "meta.json", self.store.meta)
                self.store.reload()
            shared.append(rel)
        return {"shared": shared, "skipped": skipped}

    # -- โหวต ------------------------------------------------------------
    def vote(self, lineup_id: str, value: int) -> dict:
        """กดโหวตจากหน้าเว็บ — ใบที่อยู่ในคลังจดลง meta ด้วย (ให้ตรงกับที่กดในเกม)."""
        rel = self._local_cids().get(lineup_id)
        if rel:
            with self.store.lock:
                meta_mod.set_fields(self.store.fresh_meta(), rel, vote=value)
                meta_mod.save(self.root / "meta.json", self.store.meta)
                self.store.reload()
            self.sync()
        else:
            self.client.vote(lineup_id, value)
        return {"ok": True}

    def sync(self) -> int:
        if self.client.user() is None:
            return 0
        with self.store.lock:
            meta = self.store.fresh_meta()
        return self.client.sync_votes(meta)

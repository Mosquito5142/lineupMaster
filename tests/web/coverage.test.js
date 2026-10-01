// ทดสอบหน้า "ไลน์อัพที่ยังขาด" (assets/web/coverage.js) — ต้องจัดใบเข้าสถานการณ์ตรงกับ F10 (intent.purpose)
// กรณีเดียวกับ PurposeRankTest ใน tests/test_intent.py · รัน: node --test "tests/web/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const { nameRegion, coverWorld, lineupPurpose } = require("../../assets/web/coverage.js");

const CALLOUTS = [
  ["A Site", [0.30, 0.20]], ["A Main", [0.50, 0.20]], ["A Lobby", [0.65, 0.25]],
  ["B Site", [0.30, 0.80]], ["B Main", [0.50, 0.80]], ["B Lobby", [0.65, 0.75]],
  ["Mid Top", [0.60, 0.50]], ["Mid Courtyard", [0.45, 0.50]],
  ["Attacker Spawn", [0.85, 0.50]], ["Defender Spawn", [0.10, 0.50]], ["Heaven", [0.28, 0.16]],
].map(([label, xy]) => ({ label, xy }));
const P = Object.fromEntries(CALLOUTS.map((c) => [c.label, c.xy]));
const world = coverWorld(CALLOUTS);

test("แบ่งพื้นที่จากชื่อ (รวม summit ที่ตั้งชื่อกลับด้าน)", () => {
  assert.equal(nameRegion("A Main"), "a");
  assert.equal(nameRegion("Lobby B"), "b");
  assert.equal(nameRegion("Top Mid"), "mid");
  assert.equal(nameRegion("Attacker Spawn"), "atk");
  assert.equal(nameRegion("Heaven"), null);
});

test("ไซต์ของจุด — ชื่อไม่บอกใช้ไซต์ที่ใกล้สุด · Mid = ไม่มีไซต์", () => {
  assert.equal(world.siteAt(P["Heaven"]), "a");
  assert.equal(world.siteAt(P["B Main"]), "b");
  assert.equal(world.siteAt(P["Mid Top"]), null);
});

test("ใช้ตอนไหน — ตรงกับ intent.purpose", () => {
  assert.deepEqual(lineupPurpose(world, "attack", P["Heaven"], P["A Site"]), { purpose: "post", site: "a" });
  assert.deepEqual(lineupPurpose(world, "attack", P["A Lobby"], P["A Site"]), { purpose: "entry", site: "a" });
  assert.equal(lineupPurpose(world, "attack", P["A Lobby"], P["Mid Top"]).purpose, "info");
  assert.deepEqual(lineupPurpose(world, "defense", P["Heaven"], P["A Main"]), { purpose: "hold", site: "a" });
  assert.deepEqual(lineupPurpose(world, "defense", P["A Site"], P["B Site"]), { purpose: "retake", site: "b" },
                   "ยืน A ยิงช่วย B");
  assert.equal(lineupPurpose(world, "attack", P["A Lobby"], null).purpose, null, "ไม่มีจุดตก = ไม่รู้");
});

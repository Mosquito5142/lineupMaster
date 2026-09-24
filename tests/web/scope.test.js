// ทดสอบ assets/web/scope.js — รัน: node --test "tests/web/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const { sourceAbilityChoices, keptValue } = require("../../assets/web/scope.js");

// ย่อจากแคตตาล็อกจริง: ชื่อสกิลของเว็บไม่ซ้ำข้ามตัวละคร (วัดแล้ว 87 ชื่อ ไม่มีชื่อไหนมีสองตัว)
const CATALOG = [
  { a: "sova", ab: "Recon Bolt" }, { a: "sova", ab: "Recon Bolt" }, { a: "sova", ab: "Shock Bolt" },
  { a: "cypher", ab: "Trapwire" }, { a: "cypher", ab: "Cyber Cage" }, { a: "cypher", ab: "Cyber Cage" },
  { a: "cypher", ab: "Spycam" },
  { a: "cypher" },               // ใบที่เว็บไม่ได้ระบุสกิล — ต้องไม่โผล่เป็นตัวเลือกว่างๆ
];
const TH = { sova: "โซวา", cypher: "ไซเฟอร์" };
const name = (id) => TH[id] || id;

test("เลือกไซเฟอร์ -> เหลือแค่สกิลไซเฟอร์ ใช้มากก่อน จำนวนเท่ากันเรียงตามชื่อ", () => {
  assert.deepEqual(sourceAbilityChoices(CATALOG, "cypher", name), [
    ["Cyber Cage", "Cyber Cage (2)"],
    ["Spycam", "Spycam (1)"],
    ["Trapwire", "Trapwire (1)"],
  ]);
});

test("ไม่มีสกิลของตัวอื่นปนเลย", () => {
  const ids = sourceAbilityChoices(CATALOG, "cypher", name).map(([id]) => id);
  assert.ok(!ids.includes("Recon Bolt") && !ids.includes("Shock Bolt"));
});

test("ทั้งหมด -> ครบทุกสกิล จัดกลุ่มตามตัวละคร ป้ายบอกว่าเป็นของใคร", () => {
  assert.deepEqual(sourceAbilityChoices(CATALOG, "", name), [
    ["Cyber Cage", "Cyber Cage · ไซเฟอร์ (2)"],
    ["Spycam", "Spycam · ไซเฟอร์ (1)"],
    ["Trapwire", "Trapwire · ไซเฟอร์ (1)"],
    ["Recon Bolt", "Recon Bolt · โซวา (2)"],
    ["Shock Bolt", "Shock Bolt · โซวา (1)"],
  ]);
});

test("ตัวละครที่ไม่มีในแคตตาล็อก -> ว่าง ไม่พัง", () => {
  assert.deepEqual(sourceAbilityChoices(CATALOG, "neon", name), []);
});

test("ไม่ส่ง agentName มา -> ใช้ id แทน", () => {
  assert.equal(sourceAbilityChoices(CATALOG, "")[3][1], "Recon Bolt · sova (2)");
});

test("keptValue: ยังเป็นของตัวนี้ = คงไว้, ไม่ใช่ = กลับเป็นทั้งหมด", () => {
  const cypher = sourceAbilityChoices(CATALOG, "cypher", name);
  assert.equal(keptValue(cypher, "Trapwire"), "Trapwire");
  assert.equal(keptValue(cypher, "Recon Bolt"), "");
  assert.equal(keptValue(cypher, ""), "");
});

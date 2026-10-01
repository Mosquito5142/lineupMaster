// ทดสอบสูตรแผนตัดต่อของหน้าทำวิดีโอ (assets/web/video.js) — ต้องได้ผลเดียวกับ clipgrab.clean_plan / plan_length
// (กรณีเดียวกับ PlanTest ใน tests/test_clipgrab.py) · รัน: node --test "tests/web/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const { cleanPlan, planLength } = require("../../assets/web/video.js");

const plan = (start, end, ...parts) =>
  ({ start, end, parts: parts.map(([from, to, speed]) => ({ from, to, speed })) });

test("ช่วงที่ล้นถูกหนีบเข้าในช่วงที่เก็บ", () => {
  assert.deepEqual(cleanPlan(plan(10, 20, [5, 12, 4])).parts, [{ from: 10, to: 12, speed: 4 }]);
});

test("ทับกัน อันที่ตั้งทีหลังชนะ", () => {
  assert.deepEqual(cleanPlan(plan(10, 20, [10, 16, 4], [14, 18, 0])).parts,
    [{ from: 10, to: 14, speed: 4 }, { from: 14, to: 18, speed: 0 }]);
});

test("×1 = ล้างช่วงนั้น", () => {
  assert.deepEqual(cleanPlan(plan(10, 20, [10, 20, 2], [12, 14, 1])).parts,
    [{ from: 10, to: 12, speed: 2 }, { from: 14, to: 20, speed: 2 }]);
});

test("ต่อช่วงที่ติดกัน · ทิ้งช่วงว่าง", () => {
  assert.deepEqual(cleanPlan(plan(10, 20, [10, 12, 4], [12, 14, 4], [15, 15, 2])).parts,
    [{ from: 10, to: 14, speed: 4 }]);
});

test("ค่าผิดโยน error", () => {
  assert.throws(() => cleanPlan(plan(10, 20, [11, 12, 3])));
  assert.throws(() => cleanPlan(plan(10, 10)));
});

test("ความยาวผลลัพธ์", () => {
  assert.equal(planLength(plan(10, 20, [12, 16, 4], [18, 19, 0])), 6);
  assert.equal(planLength(plan(10, 20)), 10);
  assert.equal(planLength(plan(10, 20, [0, 12, 2])), 9);
});

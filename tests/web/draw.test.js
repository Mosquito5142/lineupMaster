// ทดสอบส่วนคำนวณของตัววาดทับรูป (assets/web/draw.js) — รัน: node --test "tests/web/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const { drawWidths, toImagePoint, arrowHead } = require("../../assets/web/draw.js");

test("จุดบนจอแปลงเป็นพิกเซลของรูปจริง (canvas ถูกย่อด้วย CSS)", () => {
  const rect = { left: 100, top: 50, width: 640, height: 360 };
  assert.deepEqual(toImagePoint(420, 230, rect, 2560, 1440), [1280, 720]);
});

test("คลิกเลยขอบรูปถูกหนีบไว้ในรูป", () => {
  const rect = { left: 0, top: 0, width: 100, height: 100 };
  assert.deepEqual(toImagePoint(-20, 150, rect, 1000, 1000), [0, 1000]);
});

test("เส้นหนาขึ้นตามขนาดรูป — รูปรวม 4 ขั้นกว้าง 2560px เส้นต้องไม่บางจนมองไม่เห็น", () => {
  const [thin, mid, thick] = drawWidths(2560);
  assert.ok(thin >= 5 && mid > thin && thick > mid);
  assert.equal(drawWidths(300)[0], 2, "รูปเล็กยังมีเส้นขั้นต่ำ");
});

test("หัวลูกศรสองขาอยู่หลังปลายลูกศร สมมาตรกัน", () => {
  const [left, right] = arrowHead([0, 0], [100, 0], 20);
  assert.ok(left[0] < 100 && right[0] < 100);
  assert.ok(Math.abs(left[1] + right[1]) < 1e-9);
});

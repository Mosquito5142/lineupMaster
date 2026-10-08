// ทดสอบ bookmarklet "ส่งเข้า LineupMaster" (assets/web/bookmarklet.js) ใน sandbox ปลอม — ไม่ต่อเน็ตจริง
// รัน: node --test "tests/web/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(path.join(__dirname, "../../assets/web/bookmarklet.js"), "utf8")
  .replace(/__KEY__/g, "SECRET").replace(/__PORT_FIRST__/g, "8760").replace(/__PORT_LAST__/g, "8763");

const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

/** รัน bookmarklet บนหน้า ``href`` โดยมีเซิร์ฟเวอร์ LineupMaster ปลอมอยู่ที่พอร์ต ``livePort`` (null = ไม่มี) */
async function run({ href, pages, livePort = 8762, promptAnswer = "", pushStatus = 200 }) {
  const alerts = [], calls = [], pushed = [];
  const sandbox = {
    URL, URLSearchParams, Promise, JSON, Set, Array, Error, TypeError, AbortController, encodeURIComponent,
    setTimeout, clearTimeout,
    location: new URL(href),
    alert: (text) => alerts.push(text),
    prompt: () => promptAnswer,
    fetch: async (url, init = {}) => {
      calls.push(url);
      const local = url.match(/^http:\/\/127\.0\.0\.1:(\d+)(\/.*)$/);
      if (local) {
        if (Number(local[1]) !== livePort) throw new TypeError("Failed to fetch");
        if (local[2].startsWith("/api/tracker/ping")) return json({ ok: true });
        pushed.push({ url, init, body: JSON.parse(init.body) });
        return json({ ok: pushStatus === 200, count: pushed.at(-1).body.items.length, agent: pushed.at(-1).body.agent,
                      error: "พัง" }, pushStatus);
      }
      const page = Number(new URL(url).searchParams.get("page") || 1);
      return page > pages.length ? json({ data: [] }) : json({ data: pages[page - 1] });
    },
  };
  vm.createContext(sandbox);
  await vm.runInContext(SOURCE, sandbox);
  return { alerts, calls, pushed };
}

const guides = (...ids) => ids.map((id) => ({ id, videoUrl: `v${id}` }));

test("ดึงทุกหน้าของตัวละครใน URL แล้วส่งครั้งเดียวพร้อมรหัสลับ", async () => {
  const { pushed, calls, alerts } = await run({
    href: "https://tracker.gg/valorant/guides?agent=Sova&map=all", pages: [guides(1, 2), guides(3)],
  });
  assert.equal(pushed.length, 1);
  assert.deepEqual(pushed[0].body.items.map((i) => i.id), [1, 2, 3]);
  assert.equal(pushed[0].body.agent, "sova");
  assert.match(pushed[0].url, /^http:\/\/127\.0\.0\.1:8762\/api\/tracker\/push\?k=SECRET$/);
  assert.equal(pushed[0].init.headers["Content-Type"], "text/plain", "ไม่ให้เกิด preflight");
  const api = calls.filter((u) => u.startsWith("https://api.tracker.gg/"));
  assert.equal(api.length, 3);
  assert.match(api[0], /agent=sova&map=all&objective=all&sort=ranking&date=all$/);
  assert.match(api[1], /&page=2$/);
  assert.match(alerts.at(-1), /ส่งแล้ว 3 ใบ/);
});

test("หน้าที่ซ้ำกับหน้าก่อน = จบ ไม่วนไม่รู้จบ", async () => {
  const { pushed } = await run({ href: "https://tracker.gg/valorant/guides?agent=sova", pages: Array(50).fill(guides(1, 2)) });
  assert.deepEqual(pushed[0].body.items.map((i) => i.id), [1, 2]);
});

test("รับรูปทรงคำตอบอื่นของเว็บ (data.guides / อาเรย์ล้วน)", async () => {
  const { pushed } = await run({ href: "https://tracker.gg/x?agent=sova", pages: [{ guides: guides(7) }] });
  assert.deepEqual(pushed[0].body.items.map((i) => i.id), [7]);
});

test("ไม่มี ?agent= ถามชื่อตัวละคร · ไม่ตอบ = เลิก", async () => {
  const ok = await run({ href: "https://tracker.gg/valorant/guides", pages: [guides(1)], promptAnswer: " Cypher " });
  assert.equal(ok.pushed[0].body.agent, "cypher");
  const cancelled = await run({ href: "https://tracker.gg/valorant/guides?agent=all", pages: [guides(1)] });
  assert.equal(cancelled.calls.length, 0);
  assert.equal(cancelled.pushed.length, 0);
});

test("หาเซิร์ฟเวอร์ไม่เจอ → บอกวิธีแก้ ไม่ดึงรายการทิ้งเปล่า", async () => {
  const { alerts, calls } = await run({ href: "https://tracker.gg/x?agent=sova", pages: [guides(1)], livePort: null });
  assert.match(alerts[0], /หาหน้าจัดการคลังไม่เจอ/);
  assert.equal(calls.filter((u) => u.startsWith("https://api.tracker.gg/")).length, 0);
});

test("เซิร์ฟเวอร์ปฏิเสธ → แจ้งข้อความผิดพลาด", async () => {
  const { alerts } = await run({ href: "https://tracker.gg/x?agent=sova", pages: [guides(1)], pushStatus: 403 });
  assert.match(alerts.at(-1), /ส่งเข้า LineupMaster ไม่สำเร็จ: พัง/);
});

test("ตัวละครที่ไม่มีไลน์อัพ → แจ้ง ไม่ส่งอะไร", async () => {
  const { alerts, pushed } = await run({ href: "https://tracker.gg/x?agent=sova", pages: [] });
  assert.equal(pushed.length, 0);
  assert.match(alerts.at(-1), /ไม่เจอไลน์อัพของ "sova"/);
});

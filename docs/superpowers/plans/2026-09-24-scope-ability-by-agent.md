# ช่องสกิลแคบตามตัวละคร (หน้าจัดการคลังแบบเว็บ) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เลือกตัวละคร (เช่น ไซเฟอร์) แล้วช่อง "สกิล" ต้องเหลือเฉพาะสกิลของตัวนั้น ทั้งในแท็บ "หาไลน์อัพใหม่" และแท็บคลัง

**Architecture:** แท็บ "หาไลน์อัพใหม่" (`source.js`) เติม `s-ability` ครั้งเดียวจากชื่อสกิลดิบของ**ทุกตัวในแคตตาล็อก** (87 ชื่อ จาก 11,625 ใบ) และไม่เคยเติมใหม่ตอนเปลี่ยนตัวละคร นี่คือบั๊กที่ผู้ใช้เจอ วัดจากข้อมูลจริงแล้วว่าชื่อสกิลในแคตตาล็อก**ไม่ซ้ำข้ามตัวละครเลย** จึงสโคปจากตัวแคตตาล็อกเองได้ โดยไม่ต้องพึ่ง `AGENT_ABILITIES`:
- `AGENT_ABILITIES` เก็บแท็กของเรา (`cage`, `trapwire`) ไม่ใช่ชื่อของเว็บ (`Cyber Cage`)
- มันมีข้อมูลแค่ 4 ตัว

แยกตรรกะเป็นฟังก์ชันล้วนใน `assets/web/scope.js` ที่ node ทดสอบได้ แท็บคลัง (`f-ability`, `bulk-ability`) มีปัญหาแบบเดียวกันแต่เบากว่า (11 แท็ก) จึงใช้ `abilityOptions()` ที่มีอยู่แล้วมาสโคปให้ตรงกับเวอร์ชันเดสก์ท็อป (`tools/manage.py` ทำไว้แล้วตั้งแต่ f0d08aa)

**Tech Stack:** JS ธรรมดาในเบราว์เซอร์ (ไม่มี bundler, ใช้ global function ข้ามไฟล์ผ่าน `<script>`), Node 22 (`node --test`) สำหรับทดสอบ, `tools/web_manage.py` เป็นเซิร์ฟเวอร์

## Global Constraints

- โปรแกรมหลัก (PySide6) ห้ามเปลี่ยน · งานนี้แตะเฉพาะ `assets/web/*` และไฟล์ทดสอบใหม่
- ห้ามแตะ `.venv/pyvenv.cfg` (อีกเครื่องใช้อยู่)
- ตัวที่ผู้ใช้ใช้จริงคือ `dist/LineupMaster/` · `assets/web/` ใน dist อยู่นอก exe แค่ก๊อปไฟล์ทับแล้วกด refresh ก็ได้ผล ไม่ต้องบิ้วใหม่
- `assets/web/` ยัง **untracked** ใน git · commit แรกจะรวมหน้าเว็บทั้งชุด (รวมงานรีดีไซน์ก่อนหน้า) **ขั้น commit ให้ถามผู้ใช้ก่อน** ถ้าไม่อนุมัติให้ข้ามขั้น commit ได้
- ข้อความ UI/คอมเมนต์เป็นภาษาไทยตามสไตล์ไฟล์เดิม ชื่อสกิลจากเว็บคงเป็นภาษาอังกฤษตามต้นฉบับ
- ค่าที่ผู้ใช้เลือกไว้ต้องไม่หายเงียบๆ: เปลี่ยนตัวละครแล้วสกิลเดิมยังเป็นของตัวนั้น = คงไว้ ถ้าไม่ใช่ = กลับเป็น "ทั้งหมด"
- ห้ามรันคำสั่ง Python ด้วย `.venv` ของเครื่องนี้ (พัง) ให้ใช้ `C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe` + `PYTHONPATH=.venv/Lib/site-packages`

---

## File Structure

| ไฟล์ | หน้าที่ |
|---|---|
| Create `assets/web/scope.js` | ฟังก์ชันล้วน ไม่แตะ DOM: `sourceAbilityChoices()`, `keptValue()` ใช้ได้ทั้งเบราว์เซอร์ (global) และ node (`module.exports`) |
| Create `tests/web/scope.test.js` | ทดสอบ `scope.js` ด้วย `node --test` |
| Modify `assets/web/index.html:346` | โหลด `scope.js` ก่อน `mapview.js`/`app.js`/`source.js` |
| Modify `assets/web/source.js:341-367, 1025-1028` | เติม `s-ability` ใหม่ทุกครั้งที่เปลี่ยน `s-agent` |
| Modify `assets/web/app.js:78-99, 540-553` | เติม `f-ability`/`bulk-ability` ใหม่ทุกครั้งที่เปลี่ยน `f-agent` |

---

### Task 1: ฟังก์ชันสโคปสกิล (`scope.js`) + ทดสอบ

**Files:**
- Create: `assets/web/scope.js`
- Test: `tests/web/scope.test.js`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `sourceAbilityChoices(catalog: Array<{a: string, ab?: string}>, agent: string, agentName?: (id: string) => string): Array<[string, string]>`
    - คืน `[ชื่อสกิล, ป้าย]`
    - `agent === ""` = ทุกตัว: เรียงตาม id ตัวละคร แล้วใช้มากก่อน ป้ายเป็น `"Recon Bolt · โซวา (848)"`
    - ระบุตัว: เฉพาะของตัวนั้น ใช้มากก่อน ป้ายเป็น `"Cyber Cage (199)"`
    - จำนวนเท่ากันให้เรียงตามชื่อ
  - `keptValue(choices: Array<[string, string]>, value: string): string` คืน `value` ถ้ายังอยู่ใน `choices` ไม่งั้นคืน `""`

- [ ] **Step 1: เขียนเทสต์ที่ต้องล้ม**

สร้าง `tests/web/scope.test.js`:

```js
// ทดสอบ assets/web/scope.js — รัน: node --test tests/web/
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
```

- [ ] **Step 2: รันให้เห็นว่าล้ม**

Run: `node --test "tests/web/*.test.js"`
Expected: FAIL ด้วย `Cannot find module '../../assets/web/scope.js'`

- [ ] **Step 3: เขียนโค้ดขั้นต่ำให้ผ่าน**

สร้าง `assets/web/scope.js`:

```js
/* ช่อง "สกิล" แคบตามตัวละคร — ฟังก์ชันล้วน ไม่แตะ DOM จะได้ทดสอบด้วย node ได้
 * (tests/web/scope.test.js) · ในเบราว์เซอร์กลายเป็นฟังก์ชัน global ให้ app.js/source.js เรียก
 */

/** ตัวเลือกช่องสกิลของแท็บ "หาไลน์อัพใหม่" จากแคตตาล็อกของเว็บ
 *
 * แคตตาล็อกมีชื่อสกิลของทุกตัวรวมกัน 87 ชื่อ เลือกไซเฟอร์แล้วยังเห็น Recon Bolt/Snake Bite
 * ปนเต็มไปหมด · ชื่อสกิลของเว็บไม่ซ้ำข้ามตัวละคร (วัดจากข้อมูลจริงแล้ว) จึงดูจากแคตตาล็อก
 * เองได้เลย ไม่ต้องพึ่ง AGENT_ABILITIES ที่เก็บแท็กของเรา (cage) ไม่ใช่ชื่อของเว็บ (Cyber Cage)
 *
 * agent ว่าง = ทุกตัว: จัดกลุ่มตามตัวละครและบอกในป้ายว่าเป็นของใคร จะได้ไม่งงว่าชื่อไหนของตัวไหน
 */
function sourceAbilityChoices(catalog, agent, agentName = (id) => id) {
  const tally = new Map();   // ชื่อสกิล -> { who, n }
  for (const l of catalog) {
    if (!l.ab || (agent && l.a !== agent)) continue;
    const hit = tally.get(l.ab);
    if (hit) hit.n += 1;
    else tally.set(l.ab, { who: l.a, n: 1 });
  }
  return [...tally]
    .sort(([abA, x], [abB, y]) =>
      (agent ? 0 : x.who.localeCompare(y.who)) || y.n - x.n || abA.localeCompare(abB))
    .map(([ab, { who, n }]) =>
      [ab, agent ? `${ab} (${n})` : `${ab} · ${agentName(who)} (${n})`]);
}

/** ค่าที่เลือกไว้เดิมยังอยู่ในตัวเลือกใหม่ไหม — อยู่ = คงไว้, ไม่อยู่ = "" (ทั้งหมด)
 *
 * กันค้างค่าที่มองไม่เห็นในช่อง: เปลี่ยนตัวละครแล้วสกิลเดิมเป็นของตัวอื่น ถ้าไม่ล้าง รายการจะ
 * ว่างเปล่าโดยที่ช่องสกิลดูเหมือนไม่ได้กรองอะไรอยู่
 */
function keptValue(choices, value) {
  return value && choices.some(([id]) => id === value) ? value : "";
}

if (typeof module !== "undefined") module.exports = { sourceAbilityChoices, keptValue };
```

- [ ] **Step 4: รันให้เห็นว่าผ่าน**

Run: `node --test "tests/web/*.test.js"`
Expected: `# pass 6` และ `# fail 0`

- [ ] **Step 5: Commit (ถามผู้ใช้ก่อน ดู Global Constraints)**

```bash
git add assets/web/scope.js tests/web/scope.test.js
git commit -m "เว็บ: ฟังก์ชันสโคปช่องสกิลตามตัวละคร (scope.js) + ทดสอบด้วย node"
```

---

### Task 2: แท็บ "หาไลน์อัพใหม่" ช่องสกิลตามตัวละคร (บั๊กที่ผู้ใช้เจอ)

**Files:**
- Modify: `assets/web/index.html:346` (เพิ่ม script)
- Modify: `assets/web/source.js:341-367` (`buildSourceFilters`)
- Modify: `assets/web/source.js:1025-1028` (ต่อสาย event)

**Interfaces:**
- Consumes: `sourceAbilityChoices`, `keptValue` จาก Task 1 (global) · ของเดิม: `fill(select, items, {blank, value})` ใน app.js, `ALL`, `STATE.agents: Array<{id, th}>`, `SRC.catalog`, `refilterSource()`
- Produces: `scopeSourceAbility(): void` (source.js) เติม `s-ability` ใหม่ตาม `s-agent` ปัจจุบัน · `agentTh(id: string): string`

- [ ] **Step 1: โหลด scope.js ในหน้าเว็บ**

`assets/web/index.html` แก้บรรทัดนี้:

```html
<script src="mapview.js"></script>
```

เป็น:

```html
<script src="scope.js"></script>
<script src="mapview.js"></script>
```

- [ ] **Step 2: เติมช่องสกิลตามตัวละครใน `buildSourceFilters`**

`assets/web/source.js` แทนที่บล็อกนี้ (บรรทัด 341-355):

```js
function buildSourceFilters() {
  const agents = [...new Set(SRC.catalog.map((l) => l.a))].sort();
  const maps = [...new Set(SRC.catalog.map((l) => l.m))].sort();
  const abilities = [...new Set(SRC.catalog.map((l) => l.ab).filter(Boolean))].sort();
  const diffs = [...new Set(SRC.catalog.map((l) => l.diff).filter(Boolean))];
  const known = new Set(STATE.maps);

  fill($("s-agent"), agents.map((a) => {
    const th = (STATE.agents.find((x) => x.id === a) || {}).th || a;
    return [a, `${th} (${SRC.catalog.filter((l) => l.a === a).length})`];
  }), { blank: ALL });
  fill($("s-map"), maps.map((m) => [m, known.has(m) ? m : `${m} (ไม่มีในคลังเรา)`]), { blank: ALL });
  fill($("s-side"), [["attack", "บุก"], ["defense", "ตั้งรับ"]], { blank: ALL });
  fill($("s-site"), [["A", "A"], ["B", "B"], ["C", "C"], ["MID", "MID"]], { blank: ALL });
  fill($("s-ability"), abilities.map((a) => [a, a]), { blank: ALL });
```

ด้วย:

```js
const agentTh = (id) => (STATE.agents.find((x) => x.id === id) || {}).th || id;

/** ช่องสกิลของแท็บนี้ แคบตามตัวละครที่เลือก — ต้องเรียกใหม่ทุกครั้งที่เปลี่ยน s-agent
 * (ดู sourceAbilityChoices ใน scope.js) สกิลเดิมยังเป็นของตัวใหม่ก็คงไว้ ไม่ใช่ก็กลับเป็นทั้งหมด
 */
function scopeSourceAbility() {
  const choices = sourceAbilityChoices(SRC.catalog, $("s-agent").value, agentTh);
  fill($("s-ability"), choices, { blank: ALL, value: keptValue(choices, $("s-ability").value) });
}

function buildSourceFilters() {
  const agents = [...new Set(SRC.catalog.map((l) => l.a))].sort();
  const maps = [...new Set(SRC.catalog.map((l) => l.m))].sort();
  const diffs = [...new Set(SRC.catalog.map((l) => l.diff).filter(Boolean))];
  const known = new Set(STATE.maps);

  fill($("s-agent"), agents.map((a) =>
    [a, `${agentTh(a)} (${SRC.catalog.filter((l) => l.a === a).length})`]), { blank: ALL });
  fill($("s-map"), maps.map((m) => [m, known.has(m) ? m : `${m} (ไม่มีในคลังเรา)`]), { blank: ALL });
  fill($("s-side"), [["attack", "บุก"], ["defense", "ตั้งรับ"]], { blank: ALL });
  fill($("s-site"), [["A", "A"], ["B", "B"], ["C", "C"], ["MID", "MID"]], { blank: ALL });
```

แล้วตรงที่ตั้งค่าเริ่มต้นเป็นโซวา (บรรทัด 359-361 เดิม):

```js
  const sova = $("s-agent").querySelector('option[value="sova"]');
  if (sova) $("s-agent").value = "sova";
  buildRouteFilters();
```

เปลี่ยนเป็น:

```js
  const sova = $("s-agent").querySelector('option[value="sova"]');
  if (sova) $("s-agent").value = "sova";
  scopeSourceAbility();          // หลังตั้งตัวละครเริ่มต้น ช่องสกิลจะได้เป็นของโซวาตั้งแต่เปิดแท็บ
  buildRouteFilters();
```

- [ ] **Step 3: เปลี่ยนตัวละคร = เติมช่องสกิลใหม่ก่อนกรอง**

`assets/web/source.js` บรรทัด 1025-1028 จาก:

```js
  for (const id of ["s-agent", "s-side", "s-site", "s-ability", "s-from", "s-to",
                    "s-steps", "s-diff", "s-src", "s-owned"]) {
    $(id).addEventListener("change", refilterSource);
  }
```

เป็น:

```js
  for (const id of ["s-side", "s-site", "s-ability", "s-from", "s-to",
                    "s-steps", "s-diff", "s-src", "s-owned"]) {
    $(id).addEventListener("change", refilterSource);
  }
  // เปลี่ยนตัวละคร = ช่องสกิลต้องเหลือแค่ของตัวนั้นก่อน แล้วค่อยกรอง (ไม่งั้นสกิลตัวเก่าค้างกรองอยู่)
  $("s-agent").addEventListener("change", () => { scopeSourceAbility(); refilterSource(); });
```

- [ ] **Step 4: ทดสอบในเบราว์เซอร์จริง**

รันเซิร์ฟเวอร์เบื้องหลัง (มันพิมพ์ URL ที่มี token ออกมา แล้วเปิดเบราว์เซอร์ของระบบให้ด้วย):

```bash
PYTHONPATH=".venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 tools/web_manage.py
```

นำ URL `http://127.0.0.1:<port>/?t=<token>` จาก stdout ไปเปิดในเบราว์เซอร์ในแอป แล้วเข้าแท็บ "หาไลน์อัพใหม่" รอแคตตาล็อกโหลด แล้วรันใน `javascript_tool`:

```js
const opts = () => [...$("s-ability").options].map((o) => o.value).filter(Boolean);
const r = { sova: opts() };
$("s-agent").value = "cypher"; $("s-agent").dispatchEvent(new Event("change"));
r.cypher = opts();
$("s-ability").value = "Trapwire"; $("s-ability").dispatchEvent(new Event("change"));
r.cypherShown = SRC.shown.length; r.allTrap = SRC.shown.every((l) => l.a === "cypher" && l.ab === "Trapwire");
$("s-agent").value = "sova"; $("s-agent").dispatchEvent(new Event("change"));
r.afterSwitch = $("s-ability").value; r.sovaShown = SRC.shown.length;
$("s-agent").value = ""; $("s-agent").dispatchEvent(new Event("change"));
r.allCount = opts().length;
r
```

Expected:
- `sova` = `["Recon Bolt","Recon Dart","Shock Bolt","Shock Dart","Double Shock Dart","Owl Drone"]` (ลำดับอาจต่างถ้าแคตตาล็อกอัปเดต แต่ต้องเป็นของโซวาล้วน)
- `cypher` = `["Cyber Cage","Trapwire","Spycam","Cypher Setup"]`
- `cypherShown > 0`, `allTrap === true`
- `afterSwitch === ""` (Trapwire ไม่ใช่ของโซวา จึงกลับเป็นทั้งหมด), `sovaShown > 0`
- `allCount === 87` (หรือเท่าจำนวนชื่อสกิลทั้งหมดในแคตตาล็อก ณ ตอนนั้น)
- `read_console_messages` ต้องไม่มี error

ถ่าย screenshot ตอนเปิดดรอปดาวน์สกิลขณะเลือกไซเฟอร์ไว้ให้ผู้ใช้ดู

- [ ] **Step 5: Commit (ถามผู้ใช้ก่อน)**

```bash
git add assets/web/index.html assets/web/source.js
git commit -m "เว็บ/หาไลน์อัพใหม่: ช่องสกิลเหลือเฉพาะของตัวละครที่เลือก"
```

---

### Task 3: แท็บคลัง ช่องสกิลของตัวกรองและ "ตั้งสกิลให้ทุกใบ" ตามตัวละคร

ให้ตรงกับเวอร์ชันเดสก์ท็อป (`tools/manage.py` `_ability_options` ซึ่งสโคปทั้งตัวกรองบนสุดและปุ่มตั้งสกิลทุกใบ) · ช่องแก้ไขต่อรูป (`e-ability`) สโคปอยู่แล้ว ไม่ต้องแตะ

**Files:**
- Modify: `assets/web/app.js:78-99` (`buildFilterOptions`)
- Modify: `assets/web/app.js:540-553` (`wire`: ตัวกรอง + ปุ่มล้าง)

**Interfaces:**
- Consumes: `keptValue` (Task 1) · ของเดิม: `abilityOptions(agent: string): Array<[string, string]>` (app.js:55 ตัวละครที่ไม่อยู่ใน `STATE.agentAbilities` รวมถึง `""` จะได้ทั้งหมด), `fill`, `ALL`, `render()`
- Produces: `scopeLibraryAbility(): void` (app.js) เติม `f-ability` (คงค่าเดิมถ้ายังใช้ได้) และ `bulk-ability` (รีเซ็ตเป็นช่องว่างเสมอ เพราะเป็นปุ่มสั่งงาน ไม่ใช่ค่าที่ค้างไว้) ใหม่ตาม `f-agent`

- [ ] **Step 1: เพิ่ม `scopeLibraryAbility` แล้วใช้แทนการเติมแบบตายตัว**

`assets/web/app.js` ใต้ฟังก์ชัน `abilityOptions` (หลังบรรทัด 61) เพิ่ม:

```js
/** ช่องสกิลของตัวกรองบนสุด + "ตั้งสกิลให้ทุกใบ" แคบตามตัวละครที่กรองอยู่ (เหมือน tools/manage.py)
 * ต้องเรียกใหม่ทุกครั้งที่เปลี่ยน f-agent · ตั้งสกิลทุกใบรีเซ็ตเป็นว่างเสมอ เพราะเป็นปุ่มสั่งงาน
 */
function scopeLibraryAbility() {
  const choices = abilityOptions($("f-agent").value);
  fill($("f-ability"), choices, { blank: ALL, value: keptValue(choices, $("f-ability").value) });
  fill($("bulk-ability"), choices, { blank: "— เลือกสกิล —", value: "" });
}
```

ใน `buildFilterOptions` ลบบรรทัดนี้:

```js
  const abilities = STATE.abilities.map((a) => [a.id, a.th]);
```

แล้วในบล็อก `if (!filtersBuilt)` แทน:

```js
    fill($("f-ability"), abilities, { blank: ALL });
```

ด้วย:

```js
    scopeLibraryAbility();
```

และลบบรรทัดนี้ทิ้ง (scopeLibraryAbility เติมให้แล้ว):

```js
    fill($("bulk-ability"), abilities, { blank: "— เลือกสกิล —" });
```

- [ ] **Step 2: ต่อสาย: เปลี่ยนตัวละคร/กดล้างตัวกรอง = เติมช่องสกิลใหม่**

`assets/web/app.js` ใน `wire()` จาก:

```js
  for (const id of ["f-map", "f-side", "f-site", "f-agent", "f-ability", "f-tag"]) {
    $(id).addEventListener("change", render);
  }
```

เป็น:

```js
  for (const id of ["f-map", "f-side", "f-site", "f-ability", "f-tag"]) {
    $(id).addEventListener("change", render);
  }
  $("f-agent").addEventListener("change", () => { scopeLibraryAbility(); render(); });
```

และในตัวจัดการปุ่ม `f-reset` จาก:

```js
    for (const id of ["f-map", "f-side", "f-site", "f-agent", "f-ability", "f-tag"]) $(id).value = "";
```

เป็น:

```js
    for (const id of ["f-map", "f-side", "f-site", "f-agent", "f-ability", "f-tag"]) $(id).value = "";
    scopeLibraryAbility();   // ตัวละครกลับเป็นทั้งหมด ช่องสกิลต้องกลับมาครบด้วย
```

- [ ] **Step 3: ทดสอบในเบราว์เซอร์จริง**

refresh หน้าเว็บ (เซิร์ฟเวอร์จาก Task 2 ยังรันอยู่ ไฟล์เว็บไม่ต้องรีสตาร์ต) อยู่แท็บคลัง แล้วรันใน `javascript_tool`:

```js
const ids = (id) => [...$(id).options].map((o) => o.value).filter(Boolean);
const pick = (id, v) => { $(id).value = v; $(id).dispatchEvent(new Event("change")); };
const r = { all: ids("f-ability").length };
pick("f-agent", "cypher");
r.cypher = ids("f-ability"); r.bulk = ids("bulk-ability");
pick("f-ability", "cage");
r.cards = $("grid").children.length;   // render() ใส่การ์ดเป็นลูกตรงของ #grid
pick("f-agent", "sova");
r.afterSwitch = $("f-ability").value; r.sova = ids("f-ability");
pick("f-ability", "recon"); pick("f-agent", "sova");
r.keep = $("f-ability").value;
$("f-reset").click();
r.afterReset = ids("f-ability").length;
r
```

Expected:
- `all === 11` (จำนวน `ABILITY_TH`)
- `cypher` = `["trapwire","cage","camera"]`, `bulk` = `["trapwire","cage","camera"]`
- `cards > 0` (คลังมีรูปกรงควันของไซเฟอร์อยู่แล้ว)
- `afterSwitch === ""`, `sova` = `["recon","shock","drone","ult"]`
- `keep === "recon"`
- `afterReset === 11`
- console ไม่มี error

แล้วเช็คว่าช่องแก้ไขต่อรูป `e-ability` ยังทำงานเหมือนเดิม: คลิกการ์ดไซเฟอร์ใบหนึ่ง แล้วดูว่า `e-ability` มีแค่สกิลไซเฟอร์ + ค่าเดิมของใบนั้น

- [ ] **Step 4: Commit (ถามผู้ใช้ก่อน)**

```bash
git add assets/web/app.js
git commit -m "เว็บ/คลัง: ช่องสกิลของตัวกรองและตั้งสกิลทุกใบ แคบตามตัวละครเหมือนเวอร์ชันเดสก์ท็อป"
```

> **แก้ไขหลังรีวิว:** ข้อความข้างบน (สโคป `bulk-ability` ตาม `f-agent` ให้ตรงกับเดสก์ท็อป) เปลี่ยนใจ
> ทีหลัง — เว็บมี `picked` (Set ของการ์ดที่ติ๊กไว้) ที่ค้างอยู่ข้ามการเปลี่ยนตัวกรองได้ ซึ่งเดสก์ท็อป
> ไม่มีแนวคิดนี้ ถ้า `bulk-ability` ยังอิงตัวกรองอยู่ ติ๊กการ์ดของตัวละครหนึ่งไว้แล้วสลับตัวกรองไป
> ตัวละครอื่น จะกลายเป็นเสนอสกิลผิดตัวแล้วกดยิงใส่การ์ดที่ซ่อนอยู่ทันทีโดยไม่มีการยืนยัน จึงเปลี่ยน
> ให้ `bulk-ability` สโคปตาม **การ์ดที่ติ๊กไว้** แทน ผ่านฟังก์ชันใหม่ `scopeBulkAbility()` (เรียกจาก
> `syncBulk()` และหลัง `load()`) ไม่ใช่ `scopeLibraryAbility()` อีกต่อไป — ดูรายละเอียดใน commit ที่
> ตามหลัง commit ของ Task นี้

---

### Task 4: ส่งให้ตัวที่ใช้จริง (`dist`)

**Files:**
- Copy: `assets/web/{scope.js,index.html,source.js,app.js}` → `dist/LineupMaster/assets/web/`

**Interfaces:**
- Consumes: ผลของ Task 1-3
- Produces: ไม่มี

- [ ] **Step 1: ปิดเซิร์ฟเวอร์ทดสอบ** ที่รันไว้ใน Task 2 (ตัวที่ Claude เปิดเองเท่านั้น ห้ามปิด `LineupMaster.exe` ของผู้ใช้)

- [ ] **Step 2: ก๊อปไฟล์เว็บลง dist** (อยู่นอก exe ไม่ต้องบิ้วใหม่)

```bash
cp assets/web/scope.js assets/web/index.html assets/web/source.js assets/web/app.js dist/LineupMaster/assets/web/
```

- [ ] **Step 3: ยืนยันว่าตรงกัน**

Run: `diff -rq assets/web dist/LineupMaster/assets/web`
Expected: ไม่มี output

- [ ] **Step 4: รันเทสต์ทั้งหมดอีกรอบ**

Run: `node --test "tests/web/*.test.js"`
Expected: `# pass 6`, `# fail 0`

- [ ] **Step 5: บอกผู้ใช้** ว่าถ้าเปิดหน้าจัดการคลังค้างไว้อยู่ ให้กด refresh (Ctrl+F5) ก็ได้ผลเลย ไม่ต้องปิดโปรแกรม

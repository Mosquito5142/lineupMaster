/* แท็บ "หาไลน์อัพจากเว็บ" — เลือกไลน์อัพจากเว็บต้นทาง → จัดหน้า → เขียนทับ → เก็บเข้าคลัง
 *
 * **ประกอบรูปที่ฝั่งเบราว์เซอร์ทั้งหมด** (canvas) แล้วค่อยส่ง PNG ที่ได้ไปให้เซิร์ฟเวอร์เก็บ
 * ทำแบบนี้เพราะการเขียนด้วยปากกาต้องเห็นผลทันทีตอนลาก ถ้าให้ฝั่ง Python วาดจะต้องส่งพิกัด
 * ไป-กลับทุกเส้น หน่วงจนเขียนไม่ลื่น — และได้ผลลัพธ์ตรงกับที่เห็นบนจอเป๊ะ (WYSIWYG)
 *
 * **ที่เขียนทับเก็บเป็นสัดส่วนของช่องนั้นๆ (0..1) ไม่ใช่พิกเซลบนแผ่น** — เปลี่ยนจำนวนคอลัมน์
 * หรือขนาดออกทีหลัง สิ่งที่เขียนไว้จึงยังอยู่ตรงจุดเดิมของภาพเสมอ (แนวคิดเดียวกับ compose_lineup.py)
 */

const SRC = {
  catalog: [],
  shown: [],
  pool: [],           // ผ่านทุกตัวกรองยกเว้นต้นทาง/ปลายทาง — แผนที่ใช้นับจำนวนต่อโซนจากชุดนี้
  cursor: 0,
  decided: { taken: {}, skipped: [] },
  steps: [],          // HTMLImageElement ของแต่ละขั้นของใบที่กำลังดู
  marks: [],          // marks[i] = รอยที่เขียนบนช่องที่ i
  // ตำแหน่ง/ขนาดของแต่ละช่อง เก็บเป็น **สัดส่วนของความกว้างแผ่น** (ทั้ง x y w h)
  // ไม่ใช่พิกเซล — เปลี่ยน "ความกว้างรูปที่ออก" ทีหลังทุกอย่างจึงขยายตามพร้อมกันได้เป๊ะ
  layout: [],
  rects: [],          // กรอบของแต่ละช่องเป็นพิกเซลจริงบนแผ่น (คำนวณจาก layout ทุกครั้งที่วาด)
  sheetSize: { w: 0, h: 0 },
  tool: "none",
  color: "#ff4d4d",
  drawing: null,
  selected: -1,       // ช่องที่เลือกไว้ตอนใช้เครื่องมือ "เลือก" (ลากย้าย/ย่อขยายได้)
  drag: null,
  trash: [],          // รูปที่ลบไป เก็บไว้ให้กดคืนได้ (ไม่ได้หายถาวร)
  map: null,          // ตัวแผนที่ของแท็บนี้ (mapview.js)
  pin: null,          // หมุดที่จิ้มไว้ {from, to} — ส่งไปพร้อมตอนกดเก็บเข้าคลัง
  autoPinned: false,  // หมุดที่เห็นอยู่มาจากการเดาชื่อโซน ไม่ใช่ที่ผู้ใช้จิ้มเอง
  pinPending: null,   // จุดยืนที่คลิกไว้ รอคลิกจุดที่ 2
  manual: false,      // ผู้ใช้ลากจัดหน้าเองแล้วหรือยัง — ถ้าใช่ ลบรูปแล้วจะไม่จัดตารางใหม่ทับ
  loaded: false,

  // -- โหมดตาราง (คัดทีละหลายใบ) --
  grid: true,         // true = ตาราง · false = ดูทีละใบ (แต่งรูปได้)
  page: 0,
  picked: new Set(),  // uid ที่ติ๊กเลือกไว้ในตาราง (คนละเรื่องกับ SRC.selected ซึ่งคือช่องรูป)
  stopBulk: false,
  sources: [],        // [{id, name, site}] รายชื่อเว็บต้นทางที่ดึงมาได้
  owned: new Set(),   // เส้นทางที่คลังเรามีแล้ว — ไว้ติดป้าย "มีแล้ว" / ซ่อนทิ้ง

  // -- แผนที่กรอง (จิ้มโซนแทนการเลือกจาก dropdown) --
  zmap: null,
  zones: [],          // [{label, xy, count}] ของแมพที่เลือกอยู่
};

const PAGE_SIZE = 24;
const THUMB_LANES = 3;   // โหลดรูปย่อพร้อมกันได้กี่เส้น — มากกว่านี้คือยิงถี่ใส่เว็บเขา

const HANDLE = 22;    // ขนาดจุดจับมุมสำหรับย่อขยาย (หน่วยเดียวกับ unit ด้านล่าง)

const COLORS = ["#ff4d4d", "#ffd479", "#4ade80", "#7dd3fc", "#ffffff", "#111111"];

/* ---------- จัดหน้า (ตรรกะเดียวกับ compose_lineup.py) ---------- */
function autoColumns(count) {
  if (count <= 1) return 1;
  if (count <= 4) return 2;
  if (count <= 9) return 3;
  return 4;
}

function loadedImages() {
  return SRC.steps;      // กรองใบที่โหลดไม่ขึ้นทิ้งไปตั้งแต่ loadSteps แล้ว ที่เหลือใช้ได้ทุกใบ
}

/** จัดเรียงใหม่เป็นตารางอัตโนมัติ — เขียนทับตำแหน่งที่เคยลากไว้เองทั้งหมด */
function autoLayout() {
  const images = loadedImages();
  const opts = sheetOptions();
  const count = images.length;
  SRC.layout = [];
  if (!count) return;

  const aspect = images.reduce((sum, img) => sum + img.naturalWidth / img.naturalHeight, 0) / count;
  const cols = Math.max(1, Math.min(opts.columns || autoColumns(count), count));
  const gapU = opts.gap / opts.width;                 // ช่องไฟเป็นหน่วยความกว้างเหมือนกัน
  const cellW = (1 - gapU * (cols + 1)) / cols;
  const cellH = cellW / Math.max(aspect, 0.05);

  for (let i = 0; i < count; i++) {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const inRow = Math.min(cols, count - row * cols);
    // แถวสุดท้ายที่ไม่เต็มให้อยู่กึ่งกลาง ไม่งั้นดูเบี้ยวไปทางซ้าย
    const rowW = inRow * cellW + gapU * (inRow - 1);
    SRC.layout.push({
      x: (1 - rowW) / 2 + col * (cellW + gapU),
      y: gapU + row * (cellH + gapU),
      w: cellW, h: cellH,
    });
  }
}

/** ความสูงแผ่นเป็นหน่วยความกว้าง — โตตามช่องที่ถูกลากลงไปต่ำสุด */
function sheetHeightUnits() {
  if (!SRC.layout.length) return 0.1;
  const opts = sheetOptions();
  const bottom = Math.max(...SRC.layout.map((l) => l.y + l.h));
  return bottom + opts.gap / opts.width;
}

function sheetOptions() {
  return {
    columns: +$("s-cols").value,
    gap: +$("s-gap").value,
    width: +$("s-size").value,
    numbers: $("s-numbers").checked,
  };
}

/* ---------- วาดแผ่น ---------- */
/** วาดแผ่นทั้งใบ — แยกเป็นชั้นๆ ตามลำดับ: รูป → เลขกำกับ → รอยที่เขียน → จุดจับ
 *
 * **รอยที่เขียนต้องวาดหลังรูปครบทุกใบเสมอ** ไม่ใช่วาดคู่กับรูปทีละช่อง — เพราะลากเขียนเลย
 * ออกนอกช่องได้ ถ้าวาดทีละช่องรอยที่ล้นจากช่องก่อนหน้าจะโดนรูปช่องถัดไปทับหายไป (เจอจริง)
 * ส่วน `preview` = วาดจุดจับสำหรับลากย่อขยายด้วยไหม — ตอนส่งออกไฟล์จริงต้องไม่วาด
 */
function drawSheet(preview = true) {
  const canvas = $("sheet");
  const images = loadedImages();
  if (!images.length) { SRC.rects = []; return; }
  if (SRC.layout.length !== images.length) autoLayout();

  const opts = sheetOptions();
  const W = opts.width;
  const H = Math.max(1, Math.round(sheetHeightUnits() * W));
  SRC.rects = SRC.layout.map((l) => ({ x: l.x * W, y: l.y * W, w: l.w * W, h: l.h * W }));
  SRC.sheetSize = { w: W, h: H };

  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#0b0e14";
  ctx.fillRect(0, 0, W, H);
  ctx.imageSmoothingQuality = "high";

  // ชั้น 1: รูปทุกใบ
  images.forEach((img, i) => {
    const cell = SRC.rects[i];
    // ย่อให้พอดีช่องโดยไม่บิดสัดส่วน แล้วจัดกึ่งกลางช่อง
    const scale = Math.min(cell.w / img.naturalWidth, cell.h / img.naturalHeight);
    const w = img.naturalWidth * scale;
    const h = img.naturalHeight * scale;
    ctx.drawImage(img, cell.x + (cell.w - w) / 2, cell.y + (cell.h - h) / 2, w, h);
  });

  // ชั้น 2: เลขกำกับขั้น
  if (opts.numbers && images.length > 1) {
    SRC.rects.forEach((cell, i) => drawNumber(ctx, cell, i + 1));
  }

  // ชั้น 3: รอยที่เขียน — บนสุดเสมอ ไม่โดนรูปใบไหนทับ
  SRC.rects.forEach((cell, i) => drawMarks(ctx, cell, SRC.marks[i] || []));

  // ชั้น 4: จุดจับ (เฉพาะตอนดูบนจอ ไม่ติดไปกับไฟล์ที่เก็บเข้าคลัง)
  if (preview && SRC.tool === "none" && SRC.selected >= 0 && SRC.rects[SRC.selected]) {
    drawHandles(ctx, SRC.rects[SRC.selected], W);
  }

  $("s-dims").textContent = `${W}×${H}   ${images.length} ขั้น`;
}

function drawHandles(ctx, cell, W) {
  const unit = W / 1000;
  const size = HANDLE * unit;
  ctx.save();
  ctx.strokeStyle = "#ffd479";
  ctx.lineWidth = 2.5 * unit;
  ctx.setLineDash([9 * unit, 6 * unit]);
  ctx.strokeRect(cell.x, cell.y, cell.w, cell.h);
  ctx.setLineDash([]);
  ctx.fillStyle = "#ffd479";
  for (const [cx, cy] of corners(cell)) {
    ctx.fillRect(cx - size / 2, cy - size / 2, size, size);
  }
  ctx.restore();
}

const corners = (cell) => [
  [cell.x, cell.y], [cell.x + cell.w, cell.y],
  [cell.x, cell.y + cell.h], [cell.x + cell.w, cell.y + cell.h],
];

function drawNumber(ctx, cell, number) {
  const size = Math.max(26, Math.min(72, cell.h / 9));
  const margin = Math.max(6, size / 4);
  const cx = cell.x + margin + size / 2;
  const cy = cell.y + margin + size / 2;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(11,14,20,.84)";
  ctx.fill();
  ctx.lineWidth = Math.max(2, size / 14);
  ctx.strokeStyle = "#ffd479";
  ctx.stroke();
  ctx.fillStyle = "#ffd479";
  ctx.font = `700 ${Math.round(size * 0.58)}px "Segoe UI", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(number), cx, cy + 1);
  ctx.restore();
}

function drawMarks(ctx, cell, marks) {
  const unit = cell.w / 1000;        // ความหนาอิงความกว้างช่อง จะได้เท่ากันทุกขนาดออก
  const at = (p) => [cell.x + p[0] * cell.w, cell.y + p[1] * cell.h];
  ctx.save();
  for (const mark of marks) {
    ctx.strokeStyle = mark.color;
    ctx.fillStyle = mark.color;
    ctx.lineWidth = mark.size * unit;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    if (mark.kind === "pen" && mark.pts.length > 1) {
      ctx.beginPath();
      const [x0, y0] = at(mark.pts[0]);
      ctx.moveTo(x0, y0);
      for (const p of mark.pts.slice(1)) ctx.lineTo(...at(p));
      ctx.stroke();
    } else if (mark.kind === "line" && mark.pts.length === 2) {
      ctx.beginPath();
      ctx.moveTo(...at(mark.pts[0]));
      ctx.lineTo(...at(mark.pts[1]));
      ctx.stroke();
    } else if (mark.kind === "arrow" && mark.pts.length === 2) {
      drawArrow(ctx, at(mark.pts[0]), at(mark.pts[1]), mark.size * unit, mark.color);
    } else if (mark.kind === "text" && mark.text) {
      const px = mark.size * unit * 5;
      ctx.font = `700 ${px}px "Segoe UI", "Leelawadee UI", sans-serif`;
      ctx.textBaseline = "middle";
      const [x, y] = at(mark.pts[0]);
      // ขอบดำบางๆ รอบตัวอักษร ให้อ่านออกทั้งบนพื้นสว่างและพื้นมืดของภาพเกม
      ctx.lineWidth = Math.max(2, px / 10);
      ctx.strokeStyle = "rgba(0,0,0,.75)";
      ctx.strokeText(mark.text, x, y);
      ctx.fillStyle = mark.color;
      ctx.fillText(mark.text, x, y);
    }
  }
  ctx.restore();
}

function drawArrow(ctx, a, b, thickness, color) {
  const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const head = thickness * 3.4;
  if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1) return;
  // หดปลายเส้นเข้ามาเท่าหัวลูกศร ไม่งั้นเส้นโผล่ทะลุหัวเป็นติ่ง
  const tail = [b[0] - Math.cos(angle) * head * 0.8, b[1] - Math.sin(angle) * head * 0.8];
  ctx.beginPath();
  ctx.moveTo(a[0], a[1]);
  ctx.lineTo(tail[0], tail[1]);
  ctx.stroke();
  const spread = 0.42;
  ctx.beginPath();
  ctx.moveTo(b[0], b[1]);
  ctx.lineTo(b[0] - Math.cos(angle - spread) * head, b[1] - Math.sin(angle - spread) * head);
  ctx.lineTo(b[0] - Math.cos(angle + spread) * head, b[1] - Math.sin(angle + spread) * head);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

/* ---------- แปลงพิกัดเมาส์ -> ช่องไหน + สัดส่วนในช่อง ---------- */
/** พิกัดเมาส์ -> พิกเซลบนแผ่น (ไม่ใช่พิกเซลบนจอ เพราะแผ่นถูกย่อลงมาแสดง) */
function toSheet(event) {
  const canvas = $("sheet");
  const box = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - box.left) / box.width * canvas.width,
    y: (event.clientY - box.top) / box.height * canvas.height,
  };
}

function hit(event) {
  const { x, y } = toSheet(event);
  // ไล่จากใบหลังมาหน้า — ใบที่วาดทีหลังอยู่บนสุด ถ้าลากมาซ้อนกันต้องได้ใบบนก่อน
  for (let i = SRC.rects.length - 1; i >= 0; i--) {
    const c = SRC.rects[i];
    if (x >= c.x && x <= c.x + c.w && y >= c.y && y <= c.y + c.h) {
      return { index: i, point: [(x - c.x) / c.w, (y - c.y) / c.h] };
    }
  }
  return null;
}

/** จุดจับมุมของช่องที่เลือกอยู่ที่โดนคลิก — คืน index มุม 0..3 หรือ -1 */
function hitHandle(event) {
  if (SRC.selected < 0 || !SRC.rects[SRC.selected]) return -1;
  const { x, y } = toSheet(event);
  const reach = HANDLE * (sheetOptions().width / 1000);
  return corners(SRC.rects[SRC.selected])
    .findIndex(([cx, cy]) => Math.abs(x - cx) <= reach && Math.abs(y - cy) <= reach);
}

/* ---------- รายการจากเว็บ ---------- */
async function loadCatalog(force = false) {
  toastSource("กำลังโหลดรายการจากเว็บ…", "warn");
  const data = await api(`source/catalog${force ? "?force=1" : ""}`);
  SRC.catalog = data.lineups;
  SRC.decided = data.decisions;
  SRC.sources = data.sources || [];
  SRC.loaded = true;
  buildOwned();
  buildSourceFilters();
  refilterSource();
  const per = SRC.sources
    .map((s) => `${s.name} ${SRC.catalog.filter((l) => l.src === s.id).length.toLocaleString()}`)
    .join(" + ");
  toastSource(`ได้รายการมา ${SRC.catalog.length.toLocaleString()} ใบ (${per})`, "ok");
}

/** คีย์เส้นทางของไลน์อัพหนึ่งใบ — ใช้เทียบว่าคลังเรามีท่าเดียวกันอยู่แล้วหรือยัง */
function routeKey(map_, agent, from, to) {
  const flat = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!from || !to) return "";
  return `${map_}|${agent}|${flat(from)}>${flat(to)}`;
}

/** เส้นทางที่คลังเรามีแล้ว — อ่านจากชื่อไฟล์ ซึ่งอยู่ในรูป "A Lobby to A Site (attack) #2" */
function buildOwned() {
  SRC.owned = new Set();
  for (const lu of STATE.lineups) {
    const stem = (lu.stem || "")
      .replace(/\s*#\d+\s*$/, "")
      .replace(/\s*\((attack|defense)\)\s*/gi, " ");
    const parts = stem.split(/\s+to\s+|→|->/i);
    if (parts.length !== 2) continue;
    const key = routeKey(lu.map, lu.agent, parts[0], parts[1]);
    if (key) SRC.owned.add(key);
  }
}

const ownedKey = (l) => routeKey(l.m, l.a, l.from, l.to);
const isOwned = (l) => { const k = ownedKey(l); return !!k && SRC.owned.has(k); };

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
  fill($("s-diff"), diffs.map((d) => [d, d]), { blank: ALL });
  fill($("s-src"), SRC.sources.map((s) => [s.id, s.name]), { blank: ALL });

  const sova = $("s-agent").querySelector('option[value="sova"]');
  if (sova) $("s-agent").value = "sova";
  scopeSourceAbility();          // หลังตั้งตัวละครเริ่มต้น ช่องสกิลจะได้เป็นของโซวาตั้งแต่เปิดแท็บ
  buildRouteFilters();

  fill($("s-destmap"), STATE.maps.map((m) => [m, m]));
  fill($("s-destside"), STATE.sides.map((s) => [s.id, s.th]));
  fill($("s-destsite"), STATE.sites.map((s) => [s, s.toUpperCase()]));
  fill($("s-destagent"), STATE.agents.map((a) => [a.id, a.th]));
}

/** ช่องต้นทาง/ปลายทาง — สร้างจากโซนที่มีอยู่จริงในแมพที่เลือก พร้อมจำนวนใบต่อโซน
 *
 * ต้องสร้างใหม่ทุกครั้งที่เปลี่ยนแมพ ไม่งั้นจะมีชื่อโซนของแมพอื่นค้างให้เลือกจนงง
 */
function buildRouteFilters() {
  const map_ = $("s-map").value;
  const pool = SRC.catalog.filter((l) => (!map_ || l.m === map_) && l.from && l.to);
  const tally = (key) => {
    const count = new Map();
    for (const l of pool) count.set(l[key], (count.get(l[key]) || 0) + 1);
    return [...count].sort((a, b) => b[1] - a[1]).map(([name, n]) => [name, `${name} (${n})`]);
  };
  for (const [id, key] of [["s-from", "from"], ["s-to", "to"]]) {
    const keep = $(id).value;
    fill($(id), tally(key), { blank: ALL });
    if ([...$(id).options].some((o) => o.value === keep)) $(id).value = keep;
  }
  $("s-from").disabled = $("s-to").disabled = !pool.length;
}

function refilterSource() {
  const taken = new Set(Object.keys(SRC.decided.taken));
  const skipped = new Set(SRC.decided.skipped);
  const [agent, map_, side, site, ability, from, to, steps, diff, source] =
    ["s-agent", "s-map", "s-side", "s-site", "s-ability", "s-from", "s-to",
     "s-steps", "s-diff", "s-src"].map((id) => $(id).value);
  const query = $("s-q").value.trim().toLowerCase();
  const hideOwned = $("s-owned").checked;
  const [lowStep, highStep] = steps ? steps.split("-").map(Number) : [0, 0];

  // กรองสองชั้น: ชั้นแรกไม่รวมต้นทาง/ปลายทาง เก็บไว้เป็น SRC.pool ให้แผนที่ใช้นับ —
  // ไม่งั้นพอเลือกต้นทางแล้ววงอื่นจะกลายเป็น 0 หมด มองไม่ออกว่าไปต่อตรงไหนได้บ้าง
  SRC.pool = SRC.catalog.filter((l) =>
    (!agent || l.a === agent) &&
    (!map_ || l.m === map_) &&
    (!side || l.side === side) &&
    (!site || String(l.st || "").toUpperCase() === site) &&
    (!ability || l.ab === ability) &&
    (!source || l.src === source) &&
    (!diff || l.diff === diff) &&
    (!steps || (l.n >= lowStep && l.n <= (highStep || lowStep))) &&
    (!query || `${l.t} ${l.desc || ""} ${l.d || ""}`.toLowerCase().includes(query)) &&
    (!hideOwned || !isOwned(l)) &&
    !taken.has(l.uid) && !skipped.has(l.uid));
  SRC.shown = SRC.pool.filter((l) => (!from || l.from === from) && (!to || l.to === to));
  SRC.cursor = 0;
  SRC.page = 0;
  drawZones();
  if (SRC.grid) renderGrid(); else showCurrent();
  updateSourceCount();
}

function updateSourceCount() {
  const total = SRC.shown.length;
  $("s-count").textContent = total
    ? `เหลือให้ดู ${total.toLocaleString()} ใบ`
    : "ดูครบทุกใบของตัวกรองนี้แล้ว";
}

/* ---------- แสดงใบปัจจุบัน ---------- */
function currentSource() {
  if (!SRC.shown.length) return null;
  SRC.cursor = Math.max(0, Math.min(SRC.cursor, SRC.shown.length - 1));
  return SRC.shown[SRC.cursor];
}

async function showCurrent() {
  const lineup = currentSource();
  const total = SRC.shown.length;
  updateSourceCount();
  $("s-progress").textContent = total
    ? `ใบที่ ${SRC.cursor + 1} จาก ${total}   เอาแล้ว ${Object.keys(SRC.decided.taken).length}   ไม่เอา ${SRC.decided.skipped.length}`
    : "";
  for (const id of ["s-skip", "s-take", "s-name"]) $(id).disabled = !lineup;

  if (!lineup) {
    $("s-title").textContent = "ไม่มีใบให้ดูแล้ว";
    $("s-meta").textContent = "เปลี่ยนตัวกรองด้านบนเพื่อดูชุดอื่น";
    SRC.steps = []; SRC.marks = [];
    const canvas = $("sheet");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const known = STATE.maps.includes(lineup.m);
  $("s-title").textContent = lineup.t || "(ไม่มีชื่อ)";
  $("s-meta").textContent =
    [lineup.m, lineup.side === "defense" ? "ตั้งรับ" : "บุก", `จุด ${lineup.st || "—"}`,
     lineup.ab || "—", `${lineup.n || 1} ขั้น`, sourceName(lineup)].join("   ") +
    (lineup.d || lineup.desc ? `\n${lineup.d || lineup.desc}` : "") +
    (known ? "" : "\n⚠ แมพนี้ไม่มีในคลังเรา เก็บไม่ได้");

  $("s-name").value = (lineup.t || `lineup-${lineup.i}`).replace(/[<>:"/\\|?*]/g, "_");
  $("s-destmap").value = known ? lineup.m : STATE.maps[0];
  $("s-destside").value = lineup.side;
  const site = String(lineup.st || "").toLowerCase();
  $("s-destsite").value = STATE.sites.includes(site) ? site : "a";
  if (STATE.agents.some((a) => a.id === lineup.a)) $("s-destagent").value = lineup.a;
  updateSourceDest();

  SRC.marks = Array.from({ length: lineup.n || 1 }, () => []);
  SRC.steps = [];
  SRC.layout = [];
  SRC.selected = -1;
  SRC.manual = false;
  SRC.trash = [];
  SRC.pin = null;
  SRC.pinPending = null;
  SRC.autoPinned = false;
  loadSourceMap(lineup);
  $("s-loading").hidden = false;
  await loadSteps(lineup);
  $("s-loading").hidden = true;
  autoLayout();
  drawSheet();
  syncPanelButtons();

  // โหลดใบถัดๆ ไปรอไว้ กดข้ามรัวๆ แล้วไม่ต้องรอทีละใบ
  for (let ahead = 1; ahead <= 3; ahead++) {
    const next = SRC.shown[SRC.cursor + ahead];
    if (next) api(`source/prepare?uid=${encodeURIComponent(next.uid)}`).catch(() => {});
  }
}

async function loadSteps(lineup) {
  try {
    await api(`source/prepare?uid=${encodeURIComponent(lineup.uid)}`);
  } catch (error) {
    toastSource("โหลดรูปจากเว็บไม่ได้: " + error.message, "err");
    return;
  }
  const count = lineup.n || 1;
  const loaded = await Promise.all(Array.from({ length: count }, (_, i) => new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = `/api/source/step?uid=${encodeURIComponent(lineup.uid)}&i=${i + 1}&t=${TOKEN}`;
  })));
  // **ตัดใบที่โหลดไม่ขึ้นทิ้งตั้งแต่ตรงนี้ แล้วสร้าง marks ให้ยาวเท่ากันเป๊ะ** — ทุกอาเรย์
  // (steps/marks/layout) ต้องอ้างอิงด้วย index เดียวกันเสมอ ถ้าปล่อยให้ยาวไม่เท่ากันเมื่อไหร่
  // รอยที่เขียนจะไปโผล่ผิดช่องทันที
  SRC.steps = loaded.filter(Boolean);
  SRC.marks = SRC.steps.map(() => []);
  SRC.trash = [];
  if (SRC.steps.length < count) {
    toastSource(`รูปโหลดไม่ขึ้น ${count - SRC.steps.length} ขั้น — ใช้เท่าที่ได้`, "warn");
  }
}

function updateSourceDest() {
  const name = $("s-name").value.trim() || "ชื่อ";
  $("s-dest").textContent =
    `lineups/${$("s-destmap").value}/${$("s-destside").value}/${$("s-destagent").value}/` +
    `${$("s-destsite").value.toUpperCase()}/${name}.png`;
}

/* ---------- แผนที่ + จิ้มหมุด (จิ้มได้เลยก่อนเก็บ ไม่ต้องไปตามจิ้มทีหลัง) ---------- */
async function loadSourceMap(lineup) {
  if (!SRC.map) return;
  const map_ = $("s-destmap").value || lineup.m;
  const known = STATE.maps.includes(map_);
  $("s-pinbox").hidden = !known;
  if (!known) return;
  SRC.map.setMap(map_, TOKEN);
  let extras = { labels: {}, callouts: [] };
  try {
    extras = await api(`map-extras?map=${encodeURIComponent(map_)}&side=${$("s-destside").value}`);
  } catch { /* ไม่มีชื่อโซนก็จิ้มได้ตามปกติ */ }
  // หมุดของใบที่มีอยู่แล้วในคลัง แมพ/ฝั่งเดียวกัน — ไว้เทียบว่าจุดยืนนี้เคยมีท่าอื่นไหม
  const others = STATE.lineups
    .filter((o) => o.map === map_ && o.side === $("s-destside").value && o.pin && o.pin.from)
    .map((o) => o.pin.from);
  SRC.map.setData({ pins: others, labels: extras.labels || {}, callouts: extras.callouts || [] });
  drawSourcePin();
  await prefillAutoPin(lineup, map_);
}

/** เอาหมุดที่ระบบเดาจากชื่อโซนมาโชว์ไว้ก่อน — จะได้เห็นว่ามันจะปักตรงไหนและแก้ทันถ้าไม่ตรง
 *
 * ถามเซิร์ฟเวอร์เอาแทนที่จะคิดเองในหน้าเว็บ **เพื่อให้ได้ผลเดียวกับตอนกดเก็บเป๊ะ** —
 * ถ้าเขียนสูตรจับคู่ไว้สองที่เมื่อไหร่ วันหนึ่งมันจะให้คนละคำตอบแล้วหาสาเหตุไม่เจอ
 */
async function prefillAutoPin(lineup, map_) {
  if (SRC.pin || SRC.pinPending) return;             // ผู้ใช้จิ้มเองไว้แล้ว อย่าไปทับ
  if (!lineup.from && !lineup.to) return;            // เว็บที่ไม่บอกโซน เดาให้ไม่ได้
  try {
    const guess = await api(
      `source/autopin?uid=${encodeURIComponent(lineup.uid)}&map=${encodeURIComponent(map_)}`);
    if (currentSource() !== lineup) return;          // ผู้ใช้กดข้ามไปใบอื่นระหว่างรอ
    if (!guess.pin || !guess.pin.from) return;
    SRC.pin = guess.pin;
    SRC.autoPinned = true;
    drawSourcePin();
  } catch { /* เดาไม่ได้ก็จิ้มเองตามปกติ */ }
}

function drawSourcePin() {
  if (!SRC.map) return;
  SRC.map.setData({ current: SRC.pin, pending: SRC.pinPending });
  const done = SRC.pin && SRC.pin.from && SRC.pin.to;
  const auto = SRC.autoPinned && SRC.pin;
  $("s-pinstate").textContent = !SRC.pin ? "ยังไม่จิ้ม"
    : auto ? (done ? "ปักให้อัตโนมัติ ✓" : "ปักให้อัตโนมัติ (ได้แค่จุดยืน)")
      : (done ? "จิ้มแล้ว ✓" : "จิ้มแล้ว (ยังไม่มีปลายทาง)");
  $("s-pinstate").style.color = SRC.pin ? (auto ? "var(--warn, #e2b464)" : "var(--ok)") : "";
  $("s-pinhint").textContent = SRC.pinPending
    ? "รับจุดยืนแล้ว · คลิกที่ 2 เพื่อบอกจุดที่ลูกไปตก"
    : auto ? "เดาจากชื่อโซนที่เว็บต้นทางบอก — ไม่ตรงก็คลิกจิ้มทับได้เลย"
      : (done ? "จิ้มแล้ว · คลิกใหม่เพื่อจิ้มทับ" : "คลิก 2 ครั้ง: จุดยืน → จุดที่ลูกไปตก");
}

function onSourcePick(point) {
  SRC.autoPinned = false;          // ผู้ใช้จิ้มเอง = ไม่ใช่ของที่ระบบเดาแล้ว
  if (!SRC.pinPending) {
    SRC.pinPending = point;
  } else {
    SRC.pin = { from: SRC.pinPending, to: point };
    SRC.pinPending = null;
  }
  drawSourcePin();
}

/* ---------- ตัดสินใจ ---------- */
async function skipCurrent() {
  const lineup = currentSource();
  if (!lineup) return;
  try {
    await api("source/skip", { uid: lineup.uid });
    SRC.decided.skipped.push(lineup.uid);
    SRC.shown.splice(SRC.cursor, 1);
    showCurrent();
    updateSourceCount();
  } catch (error) { toastSource(error.message, "err"); }
}

async function takeCurrent() {
  const lineup = currentSource();
  if (!lineup) return;
  if (!SRC.steps.some((img) => img)) { toastSource("รูปยังโหลดไม่เสร็จ", "warn"); return; }
  const wasAuto = SRC.autoPinned;   // จำไว้ก่อน เดี๋ยว showCurrent() ข้างล่างล้างทิ้ง
  drawSheet(false);            // วาดใหม่แบบไม่มีจุดจับ/กรอบไข่ปลา ไม่ให้ติดไปในไฟล์จริง
  const data = $("sheet").toDataURL("image/png");
  drawSheet();                 // แล้ววาดกลับเป็นแบบมีจุดจับให้ดูต่อบนจอ
  try {
    const result = await api("source/take", {
      uid: lineup.uid, data,
      name: $("s-name").value.trim(),
      map: $("s-destmap").value, side: $("s-destside").value,
      site: $("s-destsite").value, agent: $("s-destagent").value,
      pin: SRC.pin,
    });
    SRC.decided.taken[lineup.uid] = result.rel;
    SRC.shown.splice(SRC.cursor, 1);
    showCurrent();
    await load();                                // คลังของเรามีใบใหม่แล้ว โหลดแท็บนั้นใหม่ด้วย
    buildOwned();
    updateSourceCount();
    toastSource(`เก็บเข้าคลังแล้ว: ${result.rel}` +
                (result.ability ? ` · ติดสกิล ${result.ability}` : "") +
                " · " + pinWord({ ...result, autoPin: result.autoPin || wasAuto }), "ok");
  } catch (error) { toastSource(error.message, "err"); }
}


/* ---------- โหมดตาราง: คัดทีละหลายใบ ----------
 *
 * ดูทีละใบไล่ไปเรื่อยๆ ไม่ไหวกับของ 11,000+ ใบ (ของจริงคัดไปได้แค่ 1.5% ในหลายเดือน) —
 * โหมดนี้จึงโชว์รูปย่อทีละ 24 ใบให้กวาดตาแล้วติ๊กเอาหลายใบรวดเดียว
 *
 * **รูปย่อโหลดแบบ lazy และจำกัดคิวไว้** (ดู THUMB_LANES) เพราะการเปิดหน้าเดียวแล้วยิงขอรูป
 * 24 เส้นรวดใส่เซิร์ฟเวอร์ของเว็บต้นทางพร้อมกันนั้นไม่สุภาพ — ปล่อยทีละ 3 เส้นก็พอ
 */
const sourceName = (l) =>
  (SRC.sources.find((s) => s.id === l.src) || {}).name || l.src || "";

const pinWord = (result) =>
  result.pin === "full" ? (result.autoPin ? "ปักหมุดอัตโนมัติให้แล้ว" : "จิ้มหมุดให้แล้ว")
    : result.pin === "half" ? "ได้แค่จุดยืน (ปลายทางหาโซนไม่เจอ)"
      : "ยังไม่ได้ปักหมุด";

const PIN_BADGE = {
  full: ["pin-full", "📍", "ปักหมุดอัตโนมัติได้ครบทั้งจุดยืนและปลายทาง"],
  half: ["pin-half", "📍½", "ได้แค่จุดยืน — ปลายทางหาโซนในแผนที่เราไม่เจอ"],
  none: ["pin-none", "—", "ปักหมุดอัตโนมัติไม่ได้ ต้องจิ้มเอง"],
};

let thumbQueue = [];
let thumbBusy = 0;
let thumbWatcher = null;

function pumpThumbs() {
  while (thumbBusy < THUMB_LANES && thumbQueue.length) {
    const img = thumbQueue.shift();
    if (!img.isConnected || img.dataset.done) continue;
    thumbBusy += 1;
    img.dataset.done = "1";
    const release = () => { thumbBusy -= 1; pumpThumbs(); };
    img.addEventListener("load", release, { once: true });
    img.addEventListener("error", () => { img.classList.add("broken"); release(); }, { once: true });
    img.src = `/api/source/thumb?uid=${encodeURIComponent(img.dataset.uid)}&t=${TOKEN}`;
  }
}

function pageItems() {
  const start = SRC.page * PAGE_SIZE;
  return SRC.shown.slice(start, start + PAGE_SIZE);
}

function renderGrid() {
  const host = $("s-grid");
  thumbQueue = [];
  if (thumbWatcher) thumbWatcher.disconnect();
  thumbWatcher = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      thumbWatcher.unobserve(entry.target);
      thumbQueue.push(entry.target);
    }
    pumpThumbs();
  }, { root: host, rootMargin: "300px" });

  host.textContent = "";
  const items = pageItems();
  const pages = Math.max(1, Math.ceil(SRC.shown.length / PAGE_SIZE));
  $("s-pageinfo").textContent = SRC.shown.length
    ? `หน้า ${SRC.page + 1}/${pages}   ทั้งหมด ${SRC.shown.length.toLocaleString()} ใบ`
    : "ไม่มีใบให้ดูแล้ว — เปลี่ยนตัวกรองด้านบน";
  $("s-prevpage").disabled = SRC.page <= 0;
  $("s-nextpage").disabled = SRC.page >= pages - 1;

  for (const lineup of items) {
    const cell = document.createElement("div");
    const owned = isOwned(lineup);
    cell.className = "srccell" + (SRC.picked.has(lineup.uid) ? " on" : "") + (owned ? " owned" : "");
    cell.title = "คลิกเพื่อเปิดใบนี้แบบเต็ม (แต่งรูป/จิ้มหมุดเองได้)";

    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.className = "tick";
    tick.checked = SRC.picked.has(lineup.uid);
    tick.title = "ติ๊กเพื่อเก็บใบนี้พร้อมกับใบอื่นที่เลือกไว้";
    tick.addEventListener("click", (event) => event.stopPropagation());
    tick.addEventListener("change", () => {
      if (tick.checked) SRC.picked.add(lineup.uid); else SRC.picked.delete(lineup.uid);
      cell.classList.toggle("on", tick.checked);
      updatePicked();
    });

    const img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    img.dataset.uid = lineup.uid;

    const badges = document.createElement("div");
    badges.className = "badges";
    const [cls, mark, tip] = PIN_BADGE[lineup.pin] || PIN_BADGE.none;
    badges.append(chipEl(`badge ${cls}`, mark, tip));
    if (owned) badges.append(chipEl("badge owned", "มีแล้ว", "คลังเรามีเส้นทางนี้ของตัวละครนี้อยู่แล้ว"));

    const cap = document.createElement("div");
    cap.className = "cap";
    const name = document.createElement("b");
    name.textContent = lineup.t || "(ไม่มีชื่อ)";
    const route = document.createElement("div");
    route.className = "route";
    route.textContent = lineup.from && lineup.to
      ? `${lineup.from} ▸ ${lineup.to}`
      : (lineup.desc || lineup.m);
    const slots = document.createElement("div");
    slots.className = "slots";
    slots.append(
      slotEl("site", (lineup.st || "").toUpperCase()),
      slotEl("", lineup.side === "defense" ? "ตั้งรับ" : "บุก"),
      slotEl("abil", lineup.ab || ""),
      slotEl("", lineup.n > 1 ? `${lineup.n} ขั้น` : sourceShort(lineup)),
    );
    cap.append(name, route, slots);

    cell.append(tick, img, badges, cap);
    cell.addEventListener("click", () => openInSingle(lineup));
    host.append(cell);
    thumbWatcher.observe(img);
  }
  updatePicked();
}

function slotEl(className, text) {
  const node = document.createElement("span");
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

/** ชื่อเว็บต้นทางแบบสั้น — ในตารางมีที่แค่ช่องเดียว ชื่อเต็มยาวเกิน */
const sourceShort = (l) => (l.src === "vlp" ? "VLP" : l.src === "vc" ? "VC" : l.src || "");

function chipEl(className, text, title) {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = text;
  node.title = title;
  return node;
}

function updatePicked() {
  const n = SRC.picked.size;
  $("s-selcount").textContent = `เลือกไว้ ${n} ใบ`;
  $("s-bulktake").disabled = $("s-bulkskip").disabled = !n;
}

function openInSingle(lineup) {
  const index = SRC.shown.findIndex((l) => l.uid === lineup.uid);
  if (index < 0) return;
  SRC.cursor = index;
  setGridMode(false);
}

function setGridMode(grid) {
  SRC.grid = grid;
  $("s-gridpane").hidden = !grid;
  $("s-onepane").hidden = grid;
  $("s-mode").textContent = grid ? "▭ ดูทีละใบ" : "⊞ ตาราง";
  try { localStorage.setItem("lm-source-grid", grid ? "1" : "0"); } catch { /* ไม่ซีเรียส */ }
  if (grid) renderGrid(); else showCurrent();
}

/* ---------- เก็บหลายใบรวดเดียว (ต่อรูปอัตโนมัติ ไม่ต้องแต่ง) ----------
 *
 * ต่อรูปด้วย canvas ตัวเดียวกับโหมดทีละใบเป๊ะ — แผ่นที่ได้จึงหน้าตาเหมือนกันทุกประการ
 * ไม่ต้องมีตัวต่อรูปฝั่งเซิร์ฟเวอร์ให้เพี้ยนกันสองที่ และทำเรียงทีละใบ (ไม่ขนาน) เพื่อให้
 * จังหวะหน่วงระหว่างโหลดรูปของเว็บต้นทางยังทำงานตามเดิม
 */
async function bulkTake() {
  const picked = SRC.shown.filter((l) => SRC.picked.has(l.uid));
  if (!picked.length) return;
  const bad = picked.filter((l) => !STATE.maps.includes(l.m));
  if (bad.length) {
    toastSource(`มี ${bad.length} ใบที่แมพไม่มีในคลังเรา — เอาติ๊กออกก่อน`, "err");
    return;
  }
  if (!confirm(`เก็บ ${picked.length} ใบเข้าคลังเลยไหม (ต่อรูปให้อัตโนมัติ ไม่ได้แต่ง)`)) return;

  SRC.stopBulk = false;
  const bar = $("s-bulkbar");
  bar.hidden = false; bar.max = picked.length; bar.value = 0;
  $("s-bulkstop").hidden = false;
  $("s-bulktake").disabled = $("s-bulkskip").disabled = true;

  let done = 0, pinned = 0, failed = 0;
  for (const lineup of picked) {
    if (SRC.stopBulk) break;
    try {
      const data = await composeOne(lineup);
      if (!data) { failed += 1; continue; }
      const site = String(lineup.st || "").toLowerCase();
      const result = await api("source/take", {
        uid: lineup.uid, data,
        name: (lineup.t || `lineup-${lineup.i}`).replace(/[<>:"/\\|?*]/g, "_"),
        map: lineup.m, side: lineup.side,
        site: STATE.sites.includes(site) ? site : "a",
        agent: STATE.agents.some((a) => a.id === lineup.a) ? lineup.a : "sova",
      });
      SRC.decided.taken[lineup.uid] = result.rel;
      SRC.picked.delete(lineup.uid);
      done += 1;
      if (result.pin === "full") pinned += 1;
    } catch {
      failed += 1;
    }
    bar.value = done + failed;
  }

  bar.hidden = true;
  $("s-bulkstop").hidden = true;
  await load();                    // คลังของเรามีใบใหม่แล้ว โหลดแท็บนั้นใหม่ด้วย
  buildOwned();
  refilterSource();
  toastSource(`เก็บ ${done} ใบ   ปักหมุดให้ ${pinned}` +
              (failed ? `   ข้าม ${failed} (โหลดรูปไม่ขึ้น)` : "") +
              (SRC.stopBulk ? "   หยุดกลางคัน" : ""), done ? "ok" : "err");
}

/** ต่อรูปของใบนี้เป็นแผ่นเดียวแบบเงียบๆ — คืน data URL หรือ null ถ้าโหลดรูปไม่ขึ้นเลย */
async function composeOne(lineup) {
  await api(`source/prepare?uid=${encodeURIComponent(lineup.uid)}`);
  const count = lineup.n || 1;
  const loaded = await Promise.all(Array.from({ length: count }, (_, i) => new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = `/api/source/step?uid=${encodeURIComponent(lineup.uid)}&i=${i + 1}&t=${TOKEN}`;
  })));
  const images = loaded.filter(Boolean);
  if (!images.length) return null;

  // ยืมสถานะของโหมดทีละใบมาใช้ชั่วคราว แล้วคืนให้เหมือนเดิม — ใช้ตัวจัดหน้า/ตัววาดตัวเดียวกัน
  const keep = { steps: SRC.steps, marks: SRC.marks, layout: SRC.layout,
                 selected: SRC.selected, trash: SRC.trash, manual: SRC.manual };
  SRC.steps = images;
  SRC.marks = images.map(() => []);
  SRC.layout = [];
  SRC.selected = -1;
  SRC.trash = [];
  SRC.manual = false;
  try {
    autoLayout();
    drawSheet(false);            // ไม่มีจุดจับ/กรอบไข่ปลา ไม่ให้ติดไปในไฟล์จริง
    return $("sheet").toDataURL("image/png");
  } finally {
    Object.assign(SRC, keep);
  }
}

async function bulkSkip() {
  const picked = [...SRC.picked];
  if (!picked.length) return;
  for (const uid of picked) {
    try {
      await api("source/skip", { uid });
      SRC.decided.skipped.push(uid);
    } catch { /* ข้ามใบที่พลาดไป ไม่ให้ค้างทั้งชุด */ }
  }
  SRC.picked.clear();
  refilterSource();
  toastSource(`ไม่เอา ${picked.length} ใบ`, "ok");
}

/* ---------- แผนที่กรอง: จิ้มโซนแทนการเลือกจาก dropdown ---------- */
async function loadZoneMap() {
  if (!SRC.zmap) return;
  const map_ = $("s-map").value;
  $("s-zonebox").hidden = !map_ || !STATE.maps.includes(map_);
  if ($("s-zonebox").hidden) { SRC.zones = []; return; }
  SRC.zmap.setMap(map_, TOKEN);
  let extras = { labels: {}, callouts: [] };
  try {
    extras = await api(`map-extras?map=${encodeURIComponent(map_)}`);
  } catch { /* ไม่มีชื่อโซนก็ยังกรองจาก dropdown ได้ */ }
  SRC.zones = (extras.callouts || []).map((c) => ({ label: c.label, xy: c.xy, count: 0 }));
  SRC.zmap.setData({ labels: extras.labels || {}, callouts: [], pins: [] });
  drawZones();
}

/** นับจำนวนใบต่อโซนใหม่ทุกครั้งที่ตัวกรองเปลี่ยน
 *
 * **ยังไม่เลือกต้นทาง** → นับทุกใบที่แตะโซนนั้น (จะได้เห็นว่าที่ไหนมีของเยอะ)
 * **เลือกต้นทางแล้ว** → นับเฉพาะใบที่ออกจากต้นทางนั้น แล้วลงตรงไหนบ้าง — วงที่เหลือจึงเป็น
 * "ปลายทางที่ยิงถึงจริง" ให้กดต่อได้เลย ไม่ใช่ 0 ทั้งแมพ
 */
function drawZones() {
  if (!SRC.zmap || !SRC.zones.length) return;
  const from = $("s-from").value;
  const to = $("s-to").value;
  const tally = new Map();
  const bump = (name) => { if (name) tally.set(name, (tally.get(name) || 0) + 1); };
  for (const l of SRC.pool) {
    if (!from) { bump(l.from); bump(l.to); }
    else if (l.from === from) bump(l.to);
  }
  if (from) tally.set(from, SRC.pool.filter((l) => l.from === from).length);
  SRC.zmap.setData({
    zones: SRC.zones.map((z) => ({
      ...z,
      count: tally.get(z.label) || 0,
      role: z.label === from ? "from" : z.label === to ? "to" : "",
    })),
  });
  $("s-zonestate").textContent = from
    ? (to ? `${from} ▸ ${to}` : `${from} ▸ …`)
    : "ยังไม่ได้เลือก";
}

/** ชื่อโซนของเรากับของเว็บต้นทางเรียกไม่เหมือนกันเป๊ะ ("A Site" / "Site A") — จับคู่แบบ
 *  นับคำที่ตรงกัน เหมือนที่ฝั่ง Python ทำตอนปักหมุดอัตโนมัติ (ดู tools/route_pins.py)
 *  ที่นี่ใช้แค่กรองรายการ ไม่ได้เอาไปเขียนพิกัดลงไฟล์ จึงไม่ต้องเป๊ะเท่า
 */
const NOISE_WORDS = new Set(["plant", "the", "spot", "position", "area"]);
const ZONE_ALIAS = { attackers: "attacker spawn", defenders: "defender spawn" };
const wordsOf = (name) => {
  const flat = String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return new Set((ZONE_ALIAS[flat] || flat).split(" ").filter((w) => w && !NOISE_WORDS.has(w)));
};

function nearestName(label, names) {
  const want = wordsOf(label);
  if (!want.size) return "";
  let best = "", bestScore = 0;
  for (const name of names) {
    const have = wordsOf(name);
    if (!have.size) continue;
    const shared = [...want].filter((w) => have.has(w)).length;
    const union = new Set([...want, ...have]).size;
    // โบนัสส่วนย่อยให้เฉพาะตอนฝั่งสั้นมี 2 คำขึ้นไป — เหตุผลเดียวกับ tools/route_pins.py
    const subset = (shared === want.size || shared === have.size)
      && Math.min(want.size, have.size) >= 2;
    const score = shared === union ? 1 : (subset ? 0.8 : shared / union);
    if (score > bestScore) { bestScore = score; best = name; }
  }
  return bestScore >= 0.5 ? best : "";
}

/** คลิกบนแผนที่ → หาโซนที่ใกล้ที่สุด → ตั้งเป็นตัวกรองต้นทาง/ปลายทาง */
function onZonePick(point) {
  if (!SRC.zones.length) return;
  let best = null, bestDist = Infinity;
  for (const zone of SRC.zones) {
    const dist = Math.hypot(zone.xy[0] - point[0], zone.xy[1] - point[1]);
    if (dist < bestDist) { bestDist = dist; best = zone; }
  }
  // คลิกไกลจากทุกโซน = ตั้งใจล้างตัวกรอง (ไม่ใช่เล็งพลาด)
  if (!best || bestDist > 0.06) {
    $("s-from").value = ""; $("s-to").value = "";
    refilterSource();
    return;
  }
  const target = (!$("s-from").value || $("s-to").value) ? "s-from" : "s-to";
  if (target === "s-from") $("s-to").value = "";
  const names = [...$(target).options].map((o) => o.value).filter(Boolean);
  const matched = nearestName(best.label, names);
  if (!matched) {
    toastSource(`โซน "${best.label}" ไม่มีไลน์อัพในชุดที่กรองอยู่`, "warn");
    return;
  }
  $(target).value = matched;
  refilterSource();
}

/** หน่วงการเรียกไว้ — ช่องค้นหาพิมพ์รัวๆ จะได้ไม่กรองรายการ 11,000 ใบใหม่ทุกตัวอักษร */
function debounceSource(fn, ms) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

const toastSource = (message, kind) => say(message, kind);

/* ---------- ต่อสายเหตุการณ์ ---------- */
function wireSource() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", async () => {
      for (const other of document.querySelectorAll(".tab")) other.classList.toggle("on", other === button);
      const which = button.dataset.tab;
      $("tab-library").hidden = which !== "library";
      $("tab-source").hidden = which !== "source";
      $("tab-settings").hidden = which !== "settings";
      if (which === "source" && !SRC.loaded) {
        let remembered = "1";
        try { remembered = localStorage.getItem("lm-source-grid") ?? "1"; } catch { /* โหมดเริ่มต้น */ }
        setGridMode(remembered !== "0");
        try { await loadCatalog(); } catch (error) { toastSource(error.message, "err"); }
        loadZoneMap();
      }
    });
  }

  for (const id of ["s-side", "s-site", "s-ability", "s-from", "s-to",
                    "s-steps", "s-diff", "s-src", "s-owned"]) {
    $(id).addEventListener("change", refilterSource);
  }
  // เปลี่ยนตัวละคร = ช่องสกิลต้องเหลือแค่ของตัวนั้นก่อน แล้วค่อยกรอง (ไม่งั้นสกิลตัวเก่าค้างกรองอยู่)
  $("s-agent").addEventListener("change", () => { scopeSourceAbility(); refilterSource(); });
  $("s-q").addEventListener("input", debounceSource(refilterSource, 200));
  // เปลี่ยนแมพ = ชื่อโซนต้นทาง/ปลายทางเปลี่ยนตามทั้งชุด และแผนที่กรองต้องเปลี่ยนรูปด้วย
  $("s-map").addEventListener("change", () => {
    $("s-from").value = ""; $("s-to").value = "";
    buildRouteFilters();
    refilterSource();
    loadZoneMap();
  });
  $("s-mode").addEventListener("click", () => setGridMode(!SRC.grid));
  $("s-reload").addEventListener("click", () => loadCatalog(true).catch((e) => toastSource(e.message, "err")));

  // -- โหมดตาราง --
  $("s-prevpage").addEventListener("click", () => { SRC.page -= 1; renderGrid(); });
  $("s-nextpage").addEventListener("click", () => { SRC.page += 1; renderGrid(); });
  $("s-selpage").addEventListener("click", () => {
    for (const l of pageItems()) SRC.picked.add(l.uid);
    renderGrid();
  });
  $("s-selnone").addEventListener("click", () => { SRC.picked.clear(); renderGrid(); });
  $("s-bulktake").addEventListener("click", () => bulkTake().catch((e) => toastSource(e.message, "err")));
  $("s-bulkskip").addEventListener("click", () => bulkSkip().catch((e) => toastSource(e.message, "err")));
  $("s-bulkstop").addEventListener("click", () => { SRC.stopBulk = true; });

  // -- แผนที่กรอง --
  SRC.zmap = createMapView($("s-zonestage"), { onPick: onZonePick });
  wireMapBar($("s-zonebox").querySelector(".mapbar"), SRC.zmap);
  $("s-zoneclear").addEventListener("click", (event) => {
    event.preventDefault();
    $("s-from").value = ""; $("s-to").value = "";
    refilterSource();
  });
  // แผนที่ต้องวัดขนาดกรอบตอนวาด ถ้ากล่องยังพับอยู่จะได้ 0 — สั่งพอดีจอใหม่ตอนกางออก
  $("s-zonebox").addEventListener("toggle", () => {
    if ($("s-zonebox").open) { loadZoneMap(); setTimeout(() => SRC.zmap.fit(), 0); }
  });
  // คอลัมน์/ช่องไฟ = จัดตารางใหม่ทั้งแผ่น (ทิ้งที่ลากเองไว้) ส่วนความกว้าง/เลขกำกับแค่วาดใหม่
  for (const id of ["s-cols", "s-gap"]) {
    $(id).addEventListener("input", () => { autoLayout(); drawSheet(); });
  }
  for (const id of ["s-numbers", "s-size"]) {
    $(id).addEventListener("input", () => drawSheet());
  }
  $("s-relayout").addEventListener("click", () => {
    SRC.selected = -1;
    SRC.manual = false;
    autoLayout();
    drawSheet();
    syncPanelButtons();
    toastSource("จัดเรียงใหม่เป็นตารางแล้ว", "ok");
  });
  for (const id of ["s-name", "s-destmap", "s-destside", "s-destsite", "s-destagent"]) {
    $(id).addEventListener("input", updateSourceDest);
  }
  SRC.map = createMapView($("src-mapstage"), { onPick: onSourcePick });
  wireMapBar($("s-pinbox").querySelector(".mapbar"), SRC.map);
  $("s-pinundo").addEventListener("click", () => { SRC.pinPending = null; drawSourcePin(); });
  $("s-pinclear").addEventListener("click", () => {
    SRC.pin = null; SRC.pinPending = null; SRC.autoPinned = false; drawSourcePin();
  });
  // เปลี่ยนแมพ/ฝั่งปลายทาง = แผนที่ต้องตามไปด้วย (หมุดที่จิ้มไว้ล้างทิ้ง เพราะคนละแมพแล้ว)
  for (const id of ["s-destmap", "s-destside"]) {
    $(id).addEventListener("change", () => {
      SRC.pin = null; SRC.pinPending = null; SRC.autoPinned = false;
      const lineup = currentSource();
      if (lineup) loadSourceMap(lineup);
    });
  }
  $("s-skip").addEventListener("click", skipCurrent);
  $("s-take").addEventListener("click", takeCurrent);

  // -- เครื่องมือเขียน --
  for (const button of document.querySelectorAll(".tool")) {
    button.addEventListener("click", () => {
      SRC.tool = button.dataset.tool;
      for (const other of document.querySelectorAll(".tool")) other.classList.toggle("on", other === button);
      $("sheet").classList.toggle("drawing", SRC.tool !== "none");
      $("sheet").classList.toggle("picking", SRC.tool === "none");
      drawSheet();
    });
  }
  const swatches = $("swatches");
  for (const color of COLORS) {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "swatch" + (color === SRC.color ? " on" : "");
    dot.style.background = color;
    dot.addEventListener("click", () => {
      SRC.color = color;
      for (const other of swatches.children) other.classList.toggle("on", other === dot);
    });
    swatches.append(dot);
  }
  $("s-delpanel").addEventListener("click", () => removePanel());
  $("s-restore").addEventListener("click", restorePanel);
  $("s-undo").addEventListener("click", undoMark);
  $("s-clearmarks").addEventListener("click", () => {
    SRC.marks = SRC.marks.map(() => []);
    drawSheet();
  });

  const canvas = $("sheet");
  canvas.addEventListener("pointerdown", (event) => {
    if (SRC.tool === "none") {
      // โหมดเลือก: ลากกลางรูป = ย้าย · ลากมุม = ย่อขยาย
      const handle = hitHandle(event);
      const spot = hit(event);
      if (handle < 0 && !spot) { SRC.selected = -1; drawSheet(); syncPanelButtons(); return; }
      const index = handle >= 0 ? SRC.selected : spot.index;
      SRC.selected = index;
      canvas.setPointerCapture(event.pointerId);
      const start = toSheet(event);
      const W = sheetOptions().width;
      SRC.drag = {
        index, handle,
        from: { x: start.x / W, y: start.y / W },     // เก็บเป็นหน่วยความกว้างเหมือน layout
        box: { ...SRC.layout[index] },
      };
      drawSheet();
      syncPanelButtons();
      return;
    }
    const spot = hit(event);
    if (!spot) return;
    canvas.setPointerCapture(event.pointerId);
    const size = +$("s-width").value;
    if (SRC.tool === "text") {
      const text = prompt("พิมพ์ข้อความที่จะเขียนลงรูป");
      if (text) {
        SRC.marks[spot.index].push({ kind: "text", pts: [spot.point], text, color: SRC.color, size });
        drawSheet();
      }
      return;
    }
    SRC.drawing = { index: spot.index, mark: { kind: SRC.tool, pts: [spot.point], color: SRC.color, size } };
    SRC.marks[spot.index].push(SRC.drawing.mark);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (SRC.drag) {
      const W = sheetOptions().width;
      const now = toSheet(event);
      const dx = now.x / W - SRC.drag.from.x;
      const dy = now.y / W - SRC.drag.from.y;
      const box = SRC.drag.box;
      const MIN = 0.06;                     // เล็กกว่านี้จิ้มกลับยาก
      let next;
      if (SRC.drag.handle < 0) {
        next = { ...box, x: box.x + dx, y: box.y + dy };
      } else {
        // มุมซ้าย/บน ต้องขยับขอบด้วย ส่วนมุมขวา/ล่างแค่เปลี่ยนขนาด
        const left = SRC.drag.handle === 0 || SRC.drag.handle === 2;
        const top = SRC.drag.handle === 0 || SRC.drag.handle === 1;
        const w = Math.max(MIN, left ? box.w - dx : box.w + dx);
        const h = Math.max(MIN, top ? box.h - dy : box.h + dy);
        next = {
          x: left ? box.x + (box.w - w) : box.x,
          y: top ? box.y + (box.h - h) : box.y,
          w, h,
        };
      }
      SRC.layout[SRC.drag.index] = next;
      SRC.manual = true;        // จัดหน้าเองแล้ว ห้ามจัดตารางใหม่ทับตอนลบรูป
      drawSheet();
      return;
    }
    if (!SRC.drawing) return;
    const spot = hit(event);
    // ลากเลยออกนอกช่องได้ (สัดส่วนเกิน 0..1 ไปตามจริง) แต่ยังนับเป็นของช่องที่เริ่มลาก
    const cell = SRC.rects[SRC.drawing.index];
    const box = canvas.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width * canvas.width;
    const y = (event.clientY - box.top) / box.height * canvas.height;
    const point = spot && spot.index === SRC.drawing.index
      ? spot.point : [(x - cell.x) / cell.w, (y - cell.y) / cell.h];
    if (SRC.drawing.mark.kind === "arrow" || SRC.drawing.mark.kind === "line") {
      SRC.drawing.mark.pts[1] = point;          // สองจุด: ต้นทางคงที่ ปลายวิ่งตามเมาส์
    } else {
      SRC.drawing.mark.pts.push(point);         // ปากกา: เก็บทุกจุดที่ลากผ่าน
    }
    drawSheet();
  });
  const endDraw = () => {
    if (SRC.drag) { SRC.drag = null; drawSheet(); return; }
    if (!SRC.drawing) return;
    const mark = SRC.drawing.mark;
    // คลิกเฉยๆ ไม่ได้ลาก = ไม่มีอะไรให้วาด เอาออกไม่ให้ค้างเป็นจุดจิ๋ว
    if (mark.pts.length < 2) SRC.marks[SRC.drawing.index].pop();
    SRC.drawing = null;
    drawSheet();
  };
  canvas.addEventListener("pointerup", endDraw);
  canvas.addEventListener("pointercancel", endDraw);

  document.addEventListener("keydown", (event) => {
    if ($("tab-source").hidden) return;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName);
    if (event.key === "z" && (event.ctrlKey || event.metaKey)) { undoMark(); return; }
    if (typing) return;
    if ((event.key === "Delete" || event.key === "Backspace") && SRC.selected >= 0) {
      event.preventDefault();
      removePanel();
      return;
    }
    if (event.key === "ArrowRight") skipCurrent();
    if (event.key === "Enter") takeCurrent();
  });
}

/** ลบรูปขั้นที่เลือกออกจากแผ่น — เก็บไว้ในถังขยะให้กดคืนได้ ไม่ได้หายถาวร */
function removePanel(index = SRC.selected) {
  if (index < 0 || index >= SRC.steps.length) {
    toastSource("เลือกรูปที่จะลบก่อน (ใช้เครื่องมือ ย้าย/ย่อขยาย แล้วคลิกรูป)", "warn");
    return;
  }
  if (SRC.steps.length <= 1) {
    toastSource("เหลือรูปเดียวแล้ว ลบไม่ได้", "warn");
    return;
  }
  SRC.trash.push({
    index,
    img: SRC.steps[index],
    marks: SRC.marks[index],
    box: SRC.layout[index],
  });
  SRC.steps.splice(index, 1);
  SRC.marks.splice(index, 1);
  SRC.layout.splice(index, 1);
  SRC.selected = -1;
  // ยังไม่เคยลากจัดหน้าเอง = จัดตารางใหม่ให้เลย จะได้ไม่เหลือรูโหว่ · ถ้าจัดเองไว้แล้วไม่ไปยุ่ง
  if (!SRC.manual) autoLayout();
  drawSheet();
  syncPanelButtons();
  toastSource(`ลบรูปขั้นที่ ${index + 1} แล้ว · เหลือ ${SRC.steps.length} ขั้น (กดคืนได้)`, "ok");
}

/** คืนรูปที่เพิ่งลบกลับเข้าที่เดิม */
function restorePanel() {
  const item = SRC.trash.pop();
  if (!item) { toastSource("ไม่มีรูปที่ลบไว้ให้คืน", "warn"); return; }
  const at = Math.min(item.index, SRC.steps.length);
  SRC.steps.splice(at, 0, item.img);
  SRC.marks.splice(at, 0, item.marks);
  SRC.layout.splice(at, 0, item.box);
  SRC.selected = at;
  if (!SRC.manual) autoLayout();
  drawSheet();
  syncPanelButtons();
  toastSource(`คืนรูปกลับมาแล้ว · ตอนนี้ ${SRC.steps.length} ขั้น`, "ok");
}

function syncPanelButtons() {
  $("s-delpanel").disabled = SRC.selected < 0 || SRC.steps.length <= 1;
  const restore = $("s-restore");
  restore.disabled = SRC.trash.length === 0;
  // ปุ่มเป็นไอคอนล้วน **ห้ามเขียนทับ textContent** ไม่งั้นไอคอนหายกลายเป็นข้อความยาว
  // จำนวนที่ลบไว้ไปอยู่ใน tooltip แทน
  restore.title = SRC.trash.length
    ? `คืนรูปที่เพิ่งลบกลับมา (ลบไว้ ${SRC.trash.length} รูป)`
    : "คืนรูปที่เพิ่งลบกลับมา";
}

function undoMark() {
  for (let i = SRC.marks.length - 1; i >= 0; i--) {
    if (SRC.marks[i] && SRC.marks[i].length) { SRC.marks[i].pop(); drawSheet(); return; }
  }
}

wireSource();

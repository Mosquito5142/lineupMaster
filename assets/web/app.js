/* หน้าจัดการคลัง LineupMaster — ฝั่งเบราว์เซอร์
 *
 * ทั้งไฟล์นี้ทำแค่ 2 อย่าง: วาดสิ่งที่ได้จาก /api/state ออกมา และส่งคำสั่งแก้ไขกลับไป
 * **การแก้ไฟล์จริงเกิดที่ฝั่ง Python ทั้งหมด** (ผ่าน lineupmaster.library ตัวเดียวกับที่
 * หน้า Qt เดิมใช้) ฝั่งนี้จึงไม่ต้องรู้เรื่องโครงโฟลเดอร์/ของพ่วงเลย
 */

const TOKEN = new URLSearchParams(location.search).get("t") || "";
const $ = (id) => document.getElementById(id);

const SIDE_TH = { attack: "บุก", defense: "ตั้งรับ" };
const ALL = "— ทั้งหมด —";

let STATE = null;          // ข้อมูลดิบล่าสุดจากเซิร์ฟเวอร์
let shown = [];            // ใบที่ผ่านตัวกรองแล้ว (ตามลำดับที่โชว์)
let current = null;        // rel ของใบที่กำลังแก้
let picked = new Set();    // rel ที่ติ๊กไว้สำหรับสั่งเหมา
let pendingFrom = null;    // จุดยืนที่คลิกไว้ รอคลิกจุดที่ 2
let placingSite = null;    // กำลังรอคลิกวางป้ายจุด a/b/c
let mapExtras = { labels: {}, callouts: [] };

/* ---------- คุยกับเซิร์ฟเวอร์ ---------- */
async function api(path, body) {
  const url = `/api/${path}${path.includes("?") ? "&" : "?"}t=${encodeURIComponent(TOKEN)}`;
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({ error: "อ่านคำตอบจากเซิร์ฟเวอร์ไม่ได้" }));
  if (!response.ok) throw new Error(data.error || `ผิดพลาด ${response.status}`);
  return data;
}

let toastTimer = null;
function say(message, kind = "ok") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast ${kind}`;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 4200);
}

/* ---------- ตัวช่วยเติม <select> ---------- */
function fill(select, items, { blank = null, value = null } = {}) {
  select.innerHTML = "";
  if (blank !== null) select.append(new Option(blank, ""));
  for (const item of items) {
    const [id, label] = Array.isArray(item) ? item : [item, item];
    select.append(new Option(label, id));
  }
  if (value !== null) select.value = value;
}

function abilityOptions(agent) {
  const allowed = STATE.agentAbilities[agent];
  const list = allowed
    ? STATE.abilities.filter((a) => allowed.includes(a.id))
    : STATE.abilities;
  return list.map((a) => [a.id, a.th]);
}

/** ช่องสกิลของตัวกรองบนสุด + "ตั้งสกิลให้ทุกใบ" แคบตามตัวละครที่กรองอยู่ (เหมือน tools/manage.py)
 * ต้องเรียกใหม่ทุกครั้งที่เปลี่ยน f-agent · ตั้งสกิลทุกใบรีเซ็ตเป็นว่างเสมอ เพราะเป็นปุ่มสั่งงาน
 */
function scopeLibraryAbility() {
  const choices = abilityOptions($("f-agent").value);
  fill($("f-ability"), choices, { blank: ALL, value: keptValue(choices, $("f-ability").value) });
  fill($("bulk-ability"), choices, { blank: "— เลือกสกิล —", value: "" });
}

/* ---------- โหลด + วาด ---------- */
async function load(keepRel = null) {
  STATE = await api("state");
  const keep = keepRel || current;
  buildFilterOptions();
  render();
  if (keep && STATE.lineups.some((lu) => lu.rel === keep)) select(keep);
  else if (!STATE.lineups.some((lu) => lu.rel === current)) { current = null; showEditor(); }
  $("subtitle").textContent = `คลัง ${STATE.lineups.length} ใบ`;
  $("btn-unpinned").textContent = `ยังไม่จิ้มหมุด ${STATE.unpinned}`;
}

let filtersBuilt = false;
function buildFilterOptions() {
  const maps = STATE.maps.map((m) => [m, m]);
  const sides = STATE.sides.map((s) => [s.id, s.th]);
  const sites = STATE.sites.map((s) => [s, s.toUpperCase()]);
  const agents = STATE.agents.map((a) => [a.id, a.th]);

  if (!filtersBuilt) {
    fill($("f-map"), maps, { blank: ALL });
    fill($("f-side"), sides, { blank: ALL });
    fill($("f-site"), sites, { blank: ALL });
    fill($("f-agent"), agents, { blank: ALL });
    scopeLibraryAbility();
    for (const select of ["e-map", "a-map"]) fill($(select), maps);
    for (const select of ["e-side", "a-side"]) fill($(select), sides);
    for (const select of ["e-site", "a-site"]) fill($(select), sites);
    for (const select of ["e-agent", "a-agent"]) fill($(select), agents);
    filtersBuilt = true;
  }
  // แท็กเปลี่ยนได้เรื่อยๆ ตามที่ผู้ใช้พิมพ์ จึงเติมใหม่ทุกรอบ (คงค่าที่เลือกไว้)
  const tagValue = $("f-tag").value;
  fill($("f-tag"), STATE.tags, { blank: ALL, value: "" });
  if (STATE.tags.includes(tagValue)) $("f-tag").value = tagValue;
}

function matches(lu) {
  const text = $("search").value.trim().toLowerCase();
  if (text && !(`${lu.stem} ${lu.note} ${lu.rel}`.toLowerCase().includes(text))) return false;
  if ($("f-map").value && lu.map !== $("f-map").value) return false;
  if ($("f-side").value && lu.side !== $("f-side").value) return false;
  if ($("f-site").value && lu.site !== $("f-site").value) return false;
  if ($("f-agent").value && lu.agent !== $("f-agent").value) return false;
  if ($("f-ability").value && lu.ability !== $("f-ability").value) return false;
  if ($("f-tag").value && !lu.tags.includes($("f-tag").value)) return false;
  if ($("f-fav").classList.contains("on") && !lu.fav) return false;
  if ($("btn-unpinned").classList.contains("on") && lu.pin) return false;
  return true;
}

function render() {
  shown = STATE.lineups.filter(matches);
  const grid = $("grid");
  grid.innerHTML = "";
  for (const lu of shown) {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.rel = lu.rel;
    if (lu.rel === current) card.classList.add("active");
    if (picked.has(lu.rel)) card.classList.add("picked");

    // ยังไม่จิ้มหมุด = ขีดเหลืองที่ขอบซ้ายของแถบคำอธิบาย หาเจอทั้งตารางโดยไม่ต้องอ่านตัวหนังสือ
    if (!lu.pin) card.classList.add("nopin");
    const ability = STATE.abilities.find((a) => a.id === lu.ability);
    // ชื่อไฟล์ส่วนใหญ่ *คือ* เส้นทางอยู่แล้ว ("A Lobby to A Site (attack) #2") — ถ้าโชว์ทั้งชื่อ
    // และเส้นทางที่แกะจากชื่อ มันคือข้อมูลเดียวกันสองบรรทัด เปลืองที่เปล่าๆ เลยโชว์บรรทัดเดียว
    const route = routeOf(lu.stem);
    const dup = (lu.stem.match(/#(\d+)\s*$/) || [])[1];   // #2 #3 = ท่าเดียวกันหลายแบบ ต้องแยกออก
    const title = lu.note
      ? escapeHtml(lu.note)
      : route
        ? `${escapeHtml(route[0])} <i>▸</i> ${escapeHtml(route[1])}` +
          (dup ? ` <u>#${escapeHtml(dup)}</u>` : "")
        : escapeHtml(lu.stem);
    card.innerHTML = `
      <img loading="lazy" src="/api/thumb?rel=${encodeURIComponent(lu.rel)}&t=${TOKEN}" alt="">
      <div class="meta">
        <div class="name">${title}</div>
        <div class="slots">
          <span class="site">${escapeHtml((lu.site || "").toUpperCase())}</span>
          <span>${escapeHtml(SIDE_TH[lu.side] || lu.side || "")}</span>
          <span class="abil">${ability ? escapeHtml(ability.th) : ""}</span>
          <span class="fav">${lu.fav ? "★" : ""}${lu.gif ? " gif" : ""}</span>
        </div>
      </div>`;
    card.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey) togglePick(lu.rel);
      else select(lu.rel);
    });
    grid.append(card);
  }
  $("empty").hidden = shown.length > 0;
  $("empty").textContent = STATE.lineups.length
    ? "ไม่มีใบไหนตรงกับตัวกรองนี้ — ลองล้างตัวกรองดู"
    : "ยังไม่มีรูปในคลัง — กด “เพิ่มรูปเข้าคลัง” หรือลากไฟล์มาวาง";
  $("count").textContent = `แสดง ${shown.length} จาก ${STATE.lineups.length} ใบ`;
}

/** แยก "A Lobby to A Site (attack) #2" เป็น [ต้นทาง, ปลายทาง] — ชื่อที่ไม่ได้อยู่ในรูปนี้คืน null
 *
 *  เส้นทางคือตัวตนจริงของไลน์อัพ (ยืนตรงไหน ยิงไปตรงไหน) ชื่อไฟล์ส่วนใหญ่ในคลังเก็บไว้แบบนี้อยู่แล้ว
 */
function routeOf(stem) {
  const clean = String(stem || "")
    .replace(/\s*#\d+\s*$/, "")
    .replace(/\s*\((attack|defense|defence)\)\s*/gi, " ");
  const parts = clean.split(/\s+to\s+|→|->|▸/i).map((x) => x.trim());
  return parts.length === 2 && parts[0] && parts[1] ? parts : null;
}

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- เลือก/แก้ไขใบเดียว ---------- */
function lineup(rel) { return STATE.lineups.find((lu) => lu.rel === rel) || null; }

async function select(rel) {
  current = rel;
  pendingFrom = null;
  placingSite = null;
  for (const card of document.querySelectorAll(".card")) {
    card.classList.toggle("active", card.dataset.rel === rel);
  }
  showEditor();
  await loadMap();
}

function showEditor() {
  const lu = current ? lineup(current) : null;
  $("editor").hidden = !lu;
  $("placeholder").hidden = !!lu;
  if (!lu) return;

  $("preview-img").src = `/api/image?rel=${encodeURIComponent(lu.rel)}&t=${TOKEN}`;
  $("preview-path").textContent = lu.rel;
  showRoute(lu);
  $("e-name").value = lu.stem;
  $("e-map").value = lu.map || STATE.maps[0];
  $("e-side").value = lu.side || "attack";
  $("e-site").value = lu.site || "a";
  $("e-agent").value = lu.agent || "sova";
  syncAbility(lu.ability);
  $("e-fav").checked = lu.fav;
  $("e-tags").value = lu.tags.join(" ");
  $("e-note").value = lu.note;
  updateDest();
}

function syncAbility(keep) {
  const options = abilityOptions($("e-agent").value);
  // สกิลเดิมที่ไม่ได้อยู่ในลิสต์ของตัวละครนี้ต้องคงไว้ ไม่งั้นกดบันทึกแล้วแท็กเดิมหายเงียบๆ
  if (keep && !options.some(([id]) => id === keep)) {
    const known = STATE.abilities.find((a) => a.id === keep);
    options.push([keep, known ? known.th : keep]);
  }
  fill($("e-ability"), options, { blank: "— ไม่ระบุ —", value: keep || "" });
}

/** ชื่อไลน์อัพเขียนเป็นเส้นวิถี ต้นทาง ▸ ปลายทาง — ชื่อที่ไม่ได้อยู่ในรูปเส้นทางก็โชว์ชื่อเฉยๆ */
function showRoute(lu) {
  const box = $("route-line");
  const route = routeOf(lu.stem);
  box.classList.toggle("plain", !route);
  box.querySelector(".a").textContent = route ? route[0] : (lu.note || lu.stem);
  box.querySelector(".b").textContent = route ? route[1] : "";
  box.title = lu.stem;
}

/* พาธของไฟล์โชว์อยู่ในตัวฟอร์มเองแล้ว (ดู .pathbar) จึงไม่ต้องมีบรรทัดเฉลยซ้ำอีก */
function updateDest() {}

/* ---------- แผนที่ + จิ้มหมุด ---------- */
/* ---------- ขนาดช่องดู: ลากปรับได้ + จอใหญ่ ----------
 *
 * รูปไลน์อัพมี**มินิแมพเล็กๆ ของเกมติดอยู่ในภาพ** ซึ่งบอกว่าคนยิงยืนตรงไหน — ต้องดูให้ออก
 * ถึงจะจิ้มหมุดบนแผนที่เราตามได้ถูก ค่าที่ลากไว้เก็บลง localStorage เปิดใหม่ได้ขนาดเดิม
 */
let previewView = null;

function rememberSize(key, value) {
  try { localStorage.setItem(key, value); } catch { /* เปิดแบบไม่เก็บอะไรก็ยังใช้ได้ */ }
}

function recallSize(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function refit() {
  if (mapView) mapView.fit();
  if (previewView) previewView.fit();
}

/** ต่อสายตัวคั่นลากได้หนึ่งอัน — ใช้ได้ทั้งแนวตั้ง (คอลัมน์) และแนวนอน (แถว)
 *
 * เก็บค่าเป็น ``fr`` ไม่ใช่พิกเซล — ย่อ/ขยายหน้าต่างทีหลังสัดส่วนที่ตั้งไว้จึงยังอยู่เท่าเดิม
 */
function wireSplitter(handle, container, varName, storeKey,
                      { min = 180, restMin = 320, axis = "x" } = {}) {
  const saved = recallSize(storeKey);
  if (saved) container.style.setProperty(varName, saved);
  const vertical = axis === "y";
  const bodyClass = vertical ? "splitting-y" : "splitting";

  let drag = null;
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const before = handle.previousElementSibling.getBoundingClientRect();
    const box = container.getBoundingClientRect();
    try { handle.setPointerCapture(event.pointerId); } catch { /* ลากต่อได้ตามปกติ */ }
    drag = {
      at: vertical ? event.clientY : event.clientX,
      size: vertical ? before.height : before.width,
      total: vertical ? box.height : box.width,
    };
    handle.classList.add("dragging");
    document.body.classList.add(bodyClass);
  });
  handle.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const now = vertical ? event.clientY : event.clientX;
    const want = drag.size + (now - drag.at);
    const capped = Math.max(min, Math.min(want, drag.total - restMin));
    const value = `${(capped / Math.max(1, drag.total - capped)).toFixed(3)}fr`;
    container.style.setProperty(varName, value);
    rememberSize(storeKey, value);
    refit();
  });
  const stop = () => {
    drag = null;
    handle.classList.remove("dragging");
    document.body.classList.remove(bodyClass);
  };
  handle.addEventListener("pointerup", stop);
  handle.addEventListener("pointercancel", stop);
  handle.addEventListener("dblclick", () => {
    container.style.setProperty(varName, "1fr");
    rememberSize(storeKey, "1fr");
    refit();
  });
}

function setWide(on) {
  $("lib-body").classList.toggle("wide", on);
  $("btn-wide").classList.toggle("on", on);
  $("btn-wide").textContent = on ? "⛶ ออกจากจอใหญ่" : "⛶ จอใหญ่";
  rememberSize("lm-lib-wide", on ? "1" : "0");
  // กรอบเพิ่งเปลี่ยนขนาด ต้องรอให้เบราว์เซอร์จัดหน้าเสร็จก่อนค่อยสั่งพอดีจอ
  requestAnimationFrame(refit);
}

/** เลื่อนไปใบก่อนหน้า/ถัดไปในรายการที่กรองอยู่
 *
 * จำเป็นตอนเปิด "จอใหญ่" เพราะรายการรูปทางซ้ายถูกซ่อนไปแล้ว ถ้าไม่มีปุ่มนี้จะติดอยู่ใบเดียว
 * ออกไปไหนไม่ได้ (และตอนไล่จิ้มหมุดทีละใบก็สะดวกกว่ามาไล่คลิกในรายการ)
 */
function step(delta) {
  if (!shown.length) return;
  const at = shown.findIndex((lu) => lu.rel === current);
  const next = shown[Math.max(0, Math.min((at < 0 ? 0 : at + delta), shown.length - 1))];
  if (next && next.rel !== current) select(next.rel);
}

function wirePanes() {
  previewView = createZoomPane($("preview-stage"), $("preview-img"));
  const bar = $("preview-stage").parentElement.querySelector(".mapbar");
  const zoomText = bar.querySelector(".pv-zoom");
  previewView.onView((state) => {
    if (zoomText) zoomText.textContent = `${Math.round(state.scale * 100)}%`;
  });
  for (const button of bar.querySelectorAll("[data-pv]")) {
    button.addEventListener("click", () => {
      const act = button.dataset.pv;
      if (act === "in") previewView.zoomBy(1.25);
      else if (act === "out") previewView.zoomBy(1 / 1.25);
      else previewView.fit();
    });
  }

  wireSplitter($("lib-split"), $("lib-body"), "--lib-w", "lm-lib-split",
               { min: 180, restMin: 420 });
  wireSplitter($("pane-split"), $("lib-panes"), "--pv-w", "lm-pane-split",
               { min: 160, restMin: 160 });
  wireSplitter($("form-split"), $("editor"), "--panes-h", "lm-form-split",
               { min: 160, restMin: 90, axis: "y" });

  $("btn-prev").addEventListener("click", () => step(-1));
  $("btn-next").addEventListener("click", () => step(1));
  $("btn-wide").addEventListener("click", () => setWide(!$("lib-body").classList.contains("wide")));
  setWide(recallSize("lm-lib-wide") === "1");

  // ย่อ/ขยายหน้าต่างแล้วต้องจัดให้พอดีกรอบใหม่ ไม่งั้นรูปค้างอยู่มุมเดิม
  window.addEventListener("resize", refit);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("lib-body").classList.contains("wide")) setWide(false);
    // ต้องกด Alt ด้วย ไม่งั้นลูกศรจะไปแย่งการเลื่อนเคอร์เซอร์ในช่องกรอกชื่อ/โน้ต
    if (event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      step(event.key === "ArrowRight" ? 1 : -1);
    }
  });
}

let mapView = null;          // ตัวแผนที่ที่ซูม/หมุนได้ (ดู mapview.js) สร้างครั้งเดียวตอนต่อสาย

async function loadMap() {
  const lu = current ? lineup(current) : null;
  if (!lu || !lu.map || !mapView) return;
  mapView.setMap(lu.map, TOKEN);
  try {
    mapExtras = await api(`map-extras?map=${encodeURIComponent(lu.map)}&side=${lu.side || ""}`);
  } catch { mapExtras = { labels: {}, callouts: [] }; }
  drawMap();
}

function drawMap() {
  const lu = current ? lineup(current) : null;
  if (!mapView) return;
  if (!lu) { mapView.setData({ pins: [], labels: {}, callouts: [], current: null, pending: null }); return; }

  // หมุดของใบอื่นในแมพ/ฝั่งเดียวกัน — ไว้ดูว่าจะจิ้มให้ตรงกับของเดิมตรงไหน
  const others = STATE.lineups
    .filter((o) => o.rel !== lu.rel && o.map === lu.map && o.side === lu.side && o.pin && o.pin.from)
    .map((o) => o.pin.from);
  mapView.setData({
    pins: others,
    labels: mapExtras.labels || {},
    callouts: mapExtras.callouts || [],
    current: lu.pin || null,
    pending: pendingFrom,
  });

  $("pin-status").textContent = placingSite
    ? `คลิกบนแผนที่เพื่อวางป้ายจุด ${placingSite.toUpperCase()} · Esc ยกเลิก`
    : pendingFrom
      ? "รับจุดยืนแล้ว · คลิกที่ 2 เพื่อบอกจุดที่ลูกไปตก"
      : (lu.pin ? "จิ้มหมุดแล้ว · คลิกใหม่เพื่อจิ้มทับ" : "คลิก 2 ครั้ง: จุดยืน → จุดที่ลูกไปตก");
}

async function onMapPick(point) {
  const lu = current ? lineup(current) : null;
  if (!lu) return;
  try {
    if (placingSite) {
      const site = placingSite;
      placingSite = null;
      for (const other of document.querySelectorAll("[data-site]")) other.classList.remove("on");
      await api("site-label", { map: lu.map, site, point });
      await load(lu.rel);
      await loadMap();
      say(`วางป้ายจุด ${site.toUpperCase()} ของแมพ ${lu.map} แล้ว`);
      return;
    }
    if (!pendingFrom) {
      pendingFrom = point;
      drawMap();
      return;
    }
    const from = pendingFrom;
    pendingFrom = null;
    await api("pin", { rel: lu.rel, from, to: point });
    await load(lu.rel);
    await loadMap();
    say(`จิ้มหมุด ${lu.stem} ครบแล้ว · เหลือที่ยังไม่จิ้ม ${STATE.unpinned} ใบ`);
  } catch (error) {
    say(error.message, "err");
  }
}

/** ต่อปุ่มซูม/หมุนของแถบแผนที่เข้ากับตัวแผนที่ — ใช้ได้ทั้งสองแท็บเพราะปุ่มหน้าตาเหมือนกัน */
function wireMapBar(bar, view) {
  const slider = bar.querySelector(".mv-rot");
  const deg = bar.querySelector(".mv-deg");
  const zoom = bar.querySelector(".mv-zoom");
  const sync = () => {
    if (deg) deg.textContent = `${Math.round(view.getRotation())}°`;
    if (slider) slider.value = Math.round(view.getRotation());
  };
  view.onView((state) => {
    if (zoom) zoom.textContent = `${Math.round(state.scale * 100)}%`;
  });
  for (const button of bar.querySelectorAll("[data-mv]")) {
    button.addEventListener("click", () => {
      const act = button.dataset.mv;
      if (act === "in") view.zoomBy(1.25);
      else if (act === "out") view.zoomBy(1 / 1.25);
      else if (act === "fit") view.fit();
      else if (act === "cw") { view.setRotation(view.getRotation() + 15); sync(); }
      else if (act === "ccw") { view.setRotation(view.getRotation() - 15); sync(); }
      else if (act === "rot0") { view.setRotation(0); sync(); }
    });
  }
  if (slider) slider.addEventListener("input", () => { view.setRotation(+slider.value); sync(); });
  sync();
}

/* ---------- สั่งเหมาหลายใบ ---------- */
function togglePick(rel) {
  picked.has(rel) ? picked.delete(rel) : picked.add(rel);
  render();
  syncBulk();
}

function syncBulk() {
  $("bulkbar").hidden = picked.size === 0;
  $("bulk-count").textContent = `เลือกไว้ ${picked.size} ใบ`;
}

async function runBulk(payload) {
  try {
    const result = await api("bulk", { rels: [...picked], ...payload });
    picked.clear();
    syncBulk();
    await load();
    say(`สั่งเหมาเสร็จ ${result.done} ใบ`);
  } catch (error) { say(error.message, "err"); }
}

/* ---------- เพิ่มรูป ---------- */
let addQueue = [];

function openAdd(files) {
  addQueue = files;
  if (!addQueue.length) return;
  const lu = current ? lineup(current) : null;
  const file = addQueue[0];
  $("add-info").textContent = addQueue.length > 1
    ? `${addQueue.length} ไฟล์ — จะถามทีละไฟล์`
    : file.name || "รูปจากคลิปบอร์ด";
  $("a-name").value = (file.name || "").replace(/\.[^.]+$/, "") || "ไลน์อัพใหม่";
  $("a-map").value = (lu && lu.map) || $("f-map").value || STATE.maps[0];
  $("a-side").value = (lu && lu.side) || $("f-side").value || "attack";
  $("a-site").value = (lu && lu.site) || $("f-site").value || "a";
  $("a-agent").value = (lu && lu.agent) || $("f-agent").value || "sova";
  const reader = new FileReader();
  reader.onload = () => { $("add-preview").src = reader.result; };
  reader.readAsDataURL(file);
  updateAddDest();
  $("add-dialog").showModal();
}

function updateAddDest() {
  const name = $("a-name").value.trim() || "ชื่อ";
  $("a-dest").textContent =
    `lineups/${$("a-map").value}/${$("a-side").value}/${$("a-agent").value}/` +
    `${$("a-site").value.toUpperCase()}/${name}.png`;
}

async function submitAdd() {
  const file = addQueue.shift();
  if (!file) return;
  const data = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
  const suffix = (file.name && file.name.includes(".")) ? file.name.slice(file.name.lastIndexOf(".")) : ".png";
  try {
    const result = await api("add", {
      data, suffix,
      name: $("a-name").value.trim(),
      map: $("a-map").value, side: $("a-side").value,
      site: $("a-site").value, agent: $("a-agent").value,
    });
    await load(result.rel);
    say(result.message);
  } catch (error) { say(error.message, "err"); }
  if (addQueue.length) openAdd(addQueue);
}

const imageFiles = (list) => [...list].filter((f) => f.type.startsWith("image/"));

/* ---------- ต่อสายเหตุการณ์ ---------- */
function wire() {
  for (const id of ["f-map", "f-side", "f-site", "f-ability", "f-tag"]) {
    $(id).addEventListener("change", render);
  }
  $("f-agent").addEventListener("change", () => { scopeLibraryAbility(); render(); });
  $("search").addEventListener("input", render);
  for (const id of ["f-fav", "btn-unpinned"]) {
    $(id).addEventListener("click", () => { $(id).classList.toggle("on"); render(); });
  }
  $("f-reset").addEventListener("click", () => {
    for (const id of ["f-map", "f-side", "f-site", "f-agent", "f-ability", "f-tag"]) $(id).value = "";
    $("search").value = "";
    $("f-fav").classList.remove("on");
    $("btn-unpinned").classList.remove("on");
    scopeLibraryAbility();   // ตัวละครกลับเป็นทั้งหมด ช่องสกิลต้องกลับมาครบด้วย
    render();
  });

  for (const id of ["e-name", "e-map", "e-side", "e-site", "e-agent"]) {
    $(id).addEventListener("input", updateDest);
  }
  $("e-agent").addEventListener("change", () => syncAbility($("e-ability").value));

  $("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const lu = lineup(current);
    if (!lu) return;
    try {
      const result = await api("save", {
        rel: lu.rel,
        name: $("e-name").value.trim(),
        map: $("e-map").value, side: $("e-side").value,
        site: $("e-site").value, agent: $("e-agent").value,
        ability: $("e-ability").value || null,
        fav: $("e-fav").checked,
        tags: $("e-tags").value.split(/\s+/).filter(Boolean),
        note: $("e-note").value,
      });
      await load(result.rel);
      await loadMap();
      say("บันทึกแล้ว — " + result.changes.join(", "));
    } catch (error) { say(error.message, "err"); }
  });

  $("btn-delete").addEventListener("click", async () => {
    const lu = lineup(current);
    if (!lu) return;
    if (!confirm(`ลบ "${lu.stem}" ?\n\nไฟล์จะถูกย้ายไปที่ .trash/ (ไม่ได้ลบถาวร ลากกลับมาเองได้)\nหมุดและแท็กของใบนี้จะถูกล้างไปด้วย`)) return;
    try {
      const result = await api("delete", { rel: lu.rel });
      current = null;
      await load();
      say(result.message);
    } catch (error) { say(error.message, "err"); }
  });

  mapView = createMapView($("lib-mapstage"), { onPick: onMapPick });
  wireMapBar($("lib-mapbar"), mapView);
  wirePanes();
  $("pin-undo").addEventListener("click", () => { pendingFrom = null; drawMap(); });
  $("pin-clear").addEventListener("click", async () => {
    const lu = lineup(current);
    if (!lu) return;
    try {
      await api("pin/clear", { rel: lu.rel });
      await load(lu.rel);
      await loadMap();
      say("ลบหมุดของใบนี้แล้ว");
    } catch (error) { say(error.message, "err"); }
  });
  for (const button of document.querySelectorAll("[data-site]")) {
    button.addEventListener("click", () => {
      placingSite = placingSite === button.dataset.site ? null : button.dataset.site;
      for (const other of document.querySelectorAll("[data-site]")) {
        other.classList.toggle("on", other.dataset.site === placingSite);
      }
      drawMap();
    });
  }

  $("bulk-ability").addEventListener("change", (event) => {
    if (event.target.value) runBulk({ ability: event.target.value });
    event.target.value = "";
  });
  $("bulk-fav").addEventListener("click", () => runBulk({ fav: true }));
  $("bulk-unfav").addEventListener("click", () => runBulk({ fav: false }));
  $("bulk-clear").addEventListener("click", () => { picked.clear(); render(); syncBulk(); });

  $("btn-add").addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.multiple = true;
    input.onchange = () => openAdd([...input.files]);
    input.click();
  });
  for (const id of ["a-name", "a-map", "a-side", "a-site", "a-agent"]) {
    $(id).addEventListener("input", updateAddDest);
  }
  $("add-form").addEventListener("submit", (event) => {
    if (event.submitter && event.submitter.value === "ok") submitAdd();
    else addQueue = [];
  });

  document.addEventListener("dragover", (event) => {
    event.preventDefault();
    document.body.classList.add("dragging");
  });
  document.addEventListener("dragleave", (event) => {
    if (event.relatedTarget === null) document.body.classList.remove("dragging");
  });
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    document.body.classList.remove("dragging");
    const files = imageFiles(event.dataTransfer.files);
    if (files.length) openAdd(files);
  });
  document.addEventListener("paste", (event) => {
    const files = imageFiles([...event.clipboardData.files]);
    if (files.length) openAdd(files);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && placingSite) {
      placingSite = null;
      for (const other of document.querySelectorAll("[data-site]")) other.classList.remove("on");
      drawMap();
    }
    if (event.key === "Backspace" && pendingFrom && event.target === document.body) {
      pendingFrom = null;
      drawMap();
    }
  });
}

wire();
load().catch((error) => say("โหลดข้อมูลไม่ได้: " + error.message, "err"));

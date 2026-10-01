/* ไลน์อัพที่ยังขาด — ดูคลังของเราเองบนแผนที่เต็มจอ ว่ายังขาดตรงไหน (ไม่เกี่ยวกับของจากเว็บ)
 *
 * เลือก แมพ / ฝั่ง / ตัวละคร / สกิล แล้วเห็นสองอย่าง:
 *   1. ตาราง "ยังขาดอะไร" — ไซต์ × สถานการณ์ (บุก: เปิดทาง / หลังวางบอมบ์ · รับ: เฝ้า / กู้ไซต์)
 *      ใช้กติกาเดียวกับโหมด F10 (src/lineupmaster/intent.py::purpose) ดูจากหมุดจุดยืน/จุดตก
 *      ช่อง 0 = ยังไม่มี · คลิกช่อง = แผนที่ไฮไลต์เฉพาะใบในช่องนั้น + รายชื่อทางขวา
 *   2. แผนที่ — ทุกโซนมีวงบอกจำนวนใบ (แดง = ยังไม่มี) · นับจาก "ยืนที่โซน" หรือ "ยิงไปตกโซน"
 *      คลิกวง = รายชื่อใบในโซนนั้น · คลิกชื่อใบ = ไปเปิดใบนั้นในหน้าคลัง
 */

/* ---------- สูตรล้วน (เหมือน intent.py) — ทดสอบด้วย node ได้ ---------- */
const COVER_SITES = ["a", "b", "c"];
const SITE_R = 0.11;
const cdist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

function nameRegion(label) {
  const words = String(label).toLowerCase().replace(/-/g, " ").split(/\s+/).filter(Boolean);
  const letter = words.find((w) => COVER_SITES.includes(w));
  if (letter) return letter;
  if (words.includes("spawn")) {
    if (words.includes("attacker") || words.includes("attackers")) return "atk";
    if (words.includes("defender") || words.includes("defenders")) return "def";
  }
  if (words.includes("mid") || words.includes("middle")) return "mid";
  return null;
}

/** โลกของแมพหนึ่ง: จุดกลางไซต์ + ฟังก์ชันหาไซต์ของจุด — callouts = [{label, xy}] */
function coverWorld(callouts) {
  const groups = {}, sites = {};
  for (const { label, xy } of callouts) {
    const region = nameRegion(label);
    if (!COVER_SITES.includes(region)) continue;
    (groups[region] = groups[region] || []).push(xy);
    const low = label.toLowerCase().trim();
    if (low === `${region} site` || low === `site ${region}`) sites[region] = xy;
  }
  for (const [site, points] of Object.entries(groups)) {
    if (!sites[site]) sites[site] = [points.reduce((s, p) => s + p[0], 0) / points.length,
                                     points.reduce((s, p) => s + p[1], 0) / points.length];
  }
  const nearestSite = (p) => {
    const keys = Object.keys(sites);
    return keys.length ? keys.reduce((b, k) => (cdist(sites[k], p) < cdist(sites[b], p) ? k : b)) : null;
  };
  const siteAt = (p) => {
    if (!p || !callouts.length) return null;
    const near = callouts.reduce((b, c) => (cdist(c.xy, p) < cdist(b.xy, p) ? c : b));
    const region = nameRegion(near.label) || nearestSite(near.xy);
    return COVER_SITES.includes(region) ? region : null;
  };
  const inSite = (site, p) => !!(site && p && sites[site] && cdist(sites[site], p) <= SITE_R);
  return { sites, siteAt, inSite };
}

/** ใบนี้ใช้ตอนไหน + ยิงไปไซต์ไหน — {purpose, site} (กติกาเดียวกับ intent.purpose) */
function lineupPurpose(world, side, stand, target) {
  if (!stand || !target) return { purpose: null, site: null };
  const goal = world.siteAt(target);
  if (side === "attack") {
    if (!goal) return { purpose: "info", site: null };
    return { purpose: world.inSite(goal, stand) ? "post" : "entry", site: goal };
  }
  if (!goal || world.siteAt(stand) === goal) return { purpose: "hold", site: goal || world.siteAt(stand) };
  return { purpose: "retake", site: goal };
}

if (typeof module !== "undefined") {
  module.exports = { nameRegion, coverWorld, lineupPurpose };
} else {
  /* ============================ ในเบราว์เซอร์ ============================ */
  const COLUMNS = {
    attack: [["entry", "เปิดทาง"], ["post", "หลังวางบอมบ์"]],
    defense: [["hold", "เฝ้าไซต์"], ["retake", "กู้ไซต์"]],
  };
  const COV = { view: null, extras: null, key: null, zone: null, cell: null, ours: new Map(), cells: new Map() };
  const agentTh = (id) => (STATE.agents.find((a) => a.id === id) || {}).th || id;
  const abilityTh = (id) => (STATE.abilities.find((a) => a.id === id) || {}).th || id;

  function fillFilters() {
    const keep = (id) => $(id).value;
    const map = keep("cv-map"), agent = keep("cv-agent");
    fill($("cv-map"), STATE.maps.map((m) => [m, m.toUpperCase()]), { value: map || STATE.maps[0] });
    fill($("cv-side"), [["", "ทั้งสองฝั่ง"], ...STATE.sides.map((s) => [s.id, s.th])], { value: keep("cv-side") });
    const agents = [...new Set(STATE.lineups.map((lu) => lu.agent))].sort();
    fill($("cv-agent"), agents.map((a) => [a, agentTh(a)]),
         { blank: "ทุกตัวละคร", value: agents.includes(agent) ? agent : "" });
    fillAbility();
  }

  function fillAbility() {
    const agent = $("cv-agent").value;
    const options = agent ? abilityOptions(agent) : STATE.abilities.map((a) => [a.id, a.th]);
    const current = $("cv-ability").value;
    fill($("cv-ability"), options, { blank: "ทุกสกิล", value: options.some(([id]) => id === current) ? current : "" });
  }

  function chosen() {
    const map = $("cv-map").value, side = $("cv-side").value;
    const agent = $("cv-agent").value, ability = $("cv-ability").value;
    return STATE.lineups.filter((lu) => lu.map === map && (!side || lu.side === side) &&
      (!agent || lu.agent === agent) && (!ability || lu.ability === ability));
  }

  const nearestZone = (zones, point) =>
    zones.reduce((best, z) => (cdist(z.xy, point) < cdist(best.xy, point) ? z : best)).label;

  async function refresh() {
    if (!STATE || $("tab-coverage").hidden) return;
    const map = $("cv-map").value, side = $("cv-side").value;
    if (!map) return;
    if (COV.key !== `${map}|${side}`) {
      COV.key = `${map}|${side}`;
      COV.zone = null;
      COV.cell = null;
      try { COV.extras = await api(`map-extras?map=${encodeURIComponent(map)}&side=${side}`); }
      catch { COV.extras = { labels: {}, callouts: [], spawns: {} }; }
      COV.view.setMap(map, TOKEN);
      faceSide(COV.view, map, side || "attack", COV.extras);
    }
    const zones = COV.extras.callouts || [];
    const world = coverWorld(zones);
    const byTarget = $("cv-count").value === "to";
    const items = chosen();

    // ตาราง ไซต์ × สถานการณ์
    COV.cells = new Map();
    for (const lu of items) {
      const pin = lu.pin || {};
      const { purpose, site } = lineupPurpose(world, lu.side, pin.from, pin.to);
      if (!purpose || !site) continue;
      const key = `${lu.side}|${site}|${purpose}`;
      if (!COV.cells.has(key)) COV.cells.set(key, []);
      COV.cells.get(key).push(lu);
    }
    drawTable(Object.keys(world.sites).sort(), side);

    // แผนที่: ใบนับเข้าโซนที่ใกล้จุดยืน/จุดตกที่สุด
    COV.ours = new Map(zones.map((z) => [z.label, []]));
    let unpinned = 0;
    for (const lu of items) {
      const point = lu.pin && (byTarget ? lu.pin.to : lu.pin.from);
      if (!point || !zones.length) { unpinned += 1; continue; }
      COV.ours.get(nearestZone(zones, point)).push(lu);
    }
    const focus = COV.cell ? COV.cells.get(COV.cell) || [] : null;   // คลิกช่องในตาราง = เฉพาะใบในช่องนั้น
    const shown = focus || items;
    const most = Math.max(1, ...[...COV.ours.values()].map((list) => list.length));
    const tone = (n) => (n === 0 ? "#ff5a5a" : n >= most * 0.6 ? "#4ade80" : "#7dd3fc");
    COV.view.setData({
      labels: COV.extras.labels || {},
      callouts: [],
      zones: focus ? [] : zones.map((z) => {
        const n = COV.ours.get(z.label).length;
        return { label: z.label, xy: z.xy, count: n, tone: tone(n), role: z.label === COV.zone ? "from" : "" };
      }),
      pins: focus ? [] : shown.filter((lu) => lu.pin && lu.pin.from).map((lu) => lu.pin.from),
      strong: !!focus,
      lines: shown.filter((lu) => lu.pin && lu.pin.from && lu.pin.to).map((lu) => [lu.pin.from, lu.pin.to]),
    });

    const empty = zones.map((z) => z.label).filter((label) => !COV.ours.get(label).length);
    $("cv-summary").textContent = `${items.length} ใบ · มีใน ${zones.length - empty.length}/${zones.length} โซน` +
      (unpinned ? ` · ยังไม่ปักหมุด ${unpinned} ใบ (ไม่ได้นับ)` : "");
    const gaps = $("cv-empty");
    gaps.replaceChildren();
    if (!empty.length) gaps.textContent = "ครบทุกโซนแล้ว";
    for (const label of empty) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "cv-gap";
      chip.textContent = label;
      chip.addEventListener("click", () => { COV.cell = null; COV.zone = label; refresh(); });
      gaps.append(chip);
    }
    showList();
  }

  function drawTable(sites, side) {
    const table = $("cv-table");
    table.replaceChildren();
    const sides = side ? [side] : ["attack", "defense"];
    const head = document.createElement("tr");
    head.innerHTML = "<th></th>";
    for (const s of sides) {
      for (const [, name] of COLUMNS[s]) {
        const th = document.createElement("th");
        th.textContent = sides.length > 1 ? `${s === "attack" ? "บุก" : "รับ"} · ${name}` : name;
        head.append(th);
      }
    }
    table.append(head);
    for (const site of sites) {
      const row = document.createElement("tr");
      const label = document.createElement("th");
      label.textContent = `ไซต์ ${site.toUpperCase()}`;
      row.append(label);
      for (const s of sides) {
        for (const [purpose] of COLUMNS[s]) {
          const key = `${s}|${site}|${purpose}`;
          const n = (COV.cells.get(key) || []).length;
          const td = document.createElement("td");
          const button = document.createElement("button");
          button.type = "button";
          button.className = "cv-cell" + (n ? "" : " zero") + (COV.cell === key ? " on" : "");
          button.textContent = n ? String(n) : "0 ⚠";
          button.title = n ? "คลิกดูใบในช่องนี้บนแผนที่" : "ยังไม่มีเลย";
          button.addEventListener("click", () => {
            COV.cell = COV.cell === key ? null : key;
            COV.zone = null;
            refresh();
          });
          td.append(button);
          row.append(td);
        }
      }
      table.append(row);
    }
  }

  function showList() {
    const list = $("cv-list");
    list.replaceChildren();
    let items = null, title = "";
    if (COV.cell) {
      const [s, site, purpose] = COV.cell.split("|");
      const name = (COLUMNS[s].find(([p]) => p === purpose) || [])[1];
      items = COV.cells.get(COV.cell) || [];
      title = `${s === "attack" ? "บุก" : "ตั้งรับ"} · ไซต์ ${site.toUpperCase()} · ${name}`;
    } else if (COV.zone) {
      items = COV.ours.get(COV.zone) || [];
      title = `${$("cv-count").value === "to" ? "ยิงไปตก" : "ยืนที่"} ${COV.zone}`;
    }
    $("cv-zonebox").hidden = !items;
    if (!items) return;
    $("cv-zone").textContent = `${title} — ${items.length ? `${items.length} ใบ` : "ยังไม่มี"}`;
    for (const lu of items) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "cv-item";
      row.innerHTML = `<img loading="lazy" alt="" src="/api/thumb?rel=${encodeURIComponent(lu.rel)}&v=${lu.v}&t=${TOKEN}">` +
        "<span><b></b><small></small></span>";
      row.querySelector("b").textContent = lu.stem;
      row.querySelector("small").textContent =
        `${lu.side === "attack" ? "บุก" : "ตั้งรับ"} · ${agentTh(lu.agent)} · ${lu.ability ? abilityTh(lu.ability) : "ยังไม่ตั้งสกิล"}`;
      row.addEventListener("click", () => {        // ไปเปิดใบนี้ในหน้าคลัง
        document.querySelector('.tab[data-tab="library"]').click();
        setTimeout(() => select(lu.rel), 0);
      });
      list.append(row);
    }
  }

  function onPick(point) {
    const zones = (COV.extras && COV.extras.callouts) || [];
    if (!zones.length) return;
    const label = nearestZone(zones, point);
    const near = zones.find((z) => z.label === label);
    COV.cell = null;
    COV.zone = cdist(near.xy, point) < 0.08 ? label : null;   // คลิกที่ว่างไกลจากโซน = ยกเลิกเลือก
    refresh();
  }

  function wire() {
    COV.view = createMapView($("cv-stage"), { onPick });
    wireMapBar($("tab-coverage").querySelector(".mapbar"), COV.view);
    for (const id of ["cv-map", "cv-side", "cv-ability", "cv-count"]) $(id).addEventListener("change", () => {
      COV.cell = null;
      refresh();
    });
    $("cv-agent").addEventListener("change", () => { fillAbility(); COV.cell = null; refresh(); });
    document.querySelector('.tab[data-tab="coverage"]').addEventListener("click", () => {
      setTimeout(async () => {
        if (!STATE) return;
        fillFilters();
        COV.key = null;          // เพิ่งโชว์แท็บ — กรอบแผนที่เพิ่งมีขนาด ต้องพอดีจอใหม่
        await refresh();
        COV.view.fit();
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
  window.refreshCoverage = refresh;
}

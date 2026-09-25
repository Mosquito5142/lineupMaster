/* คัดใบซ้ำ — ไลน์อัพที่โหลดจากเว็บมาทั้งกอง ให้เหลือไม่กี่ใบที่ดีต่อเป้าหมาย (lineupmaster/curate.py)
 *
 * สามขั้นในกล่องเดียว: เลือกตัวละคร → คัดทีละกลุ่ม (แมพ × ฝั่ง × สกิล × โซนปลายทาง) → สรุปแล้วทิ้งเข้า .trash
 * ใบที่โปรแกรมเสนอติดกรอบ "เก็บ" ไว้ก่อน · คีย์บอร์ด: 1-9 สลับเก็บ/ทิ้ง · Enter ยืนยันไปกลุ่มถัดไป
 * · Backspace กลับ · 0 ทิ้งทั้งกลุ่ม · S ข้าม · ตัดสินแต่ละกลุ่มถูกจำไว้ที่เซิร์ฟเวอร์ ปิดกลางทางมาต่อได้
 */

const CUR = { agent: "", groups: [], decisions: {}, abilities: {}, index: 0, keep: new Set() };
const CUR_SIDE = { attack: "บุก", defense: "ตั้งรับ" };

function curStage(name) {
  for (const stage of ["pick", "review", "done"]) $(`cur-${stage}`).hidden = stage !== name;
}

async function openCurate() {
  curStage("pick");
  $("curate-dialog").showModal();
  $("cur-agent").innerHTML = "<option>กำลังโหลด…</option>";
  try {
    const { agents } = await api("curate/agents");
    fill($("cur-agent"), agents.map((a) => [a.agent, `${a.th} (${a.count} ใบจากเว็บ)`]));
    $("cur-start").disabled = !agents.length;
    if (!agents.length) $("cur-agent").innerHTML = "<option>ยังไม่มีไลน์อัพที่โหลดมาจากหน้าหาไลน์อัพ</option>";
  } catch (error) {
    say(error.message, "err");
  }
}

async function startCurate() {
  CUR.agent = $("cur-agent").value;
  const keep = $("cur-keep").value;
  const singles = $("cur-singles").checked ? "1" : "0";
  try {
    const data = await api(`curate?agent=${encodeURIComponent(CUR.agent)}&keep=${keep}&singles=${singles}`);
    CUR.groups = data.groups;
    CUR.decisions = data.decisions;
    CUR.abilities = data.abilities;
  } catch (error) {
    say(error.message, "err");
    return;
  }
  if (!CUR.groups.length) {
    say("ไม่มีกลุ่มที่มีหลายใบให้เลือก — ติ๊ก \"ดูกลุ่มเดี่ยวด้วย\" ถ้าอยากไล่ทิ้งใบเดี่ยว", "warn");
    return;
  }
  const first = CUR.groups.findIndex((g) => !(g.key in CUR.decisions));
  showGroup(first < 0 ? 0 : first);
  curStage("review");
}

function showGroup(index) {
  CUR.index = Math.max(0, Math.min(index, CUR.groups.length - 1));
  const group = CUR.groups[CUR.index];
  CUR.keep = new Set(CUR.decisions[group.key] ?? group.suggest);
  const ability = CUR.abilities[group.ability] || group.ability;
  const done = CUR.groups.filter((g) => g.key in CUR.decisions).length;
  $("cur-head").innerHTML =
    `<b>${escapeHtml(group.map)} · ${CUR_SIDE[group.side] || group.side} · ${escapeHtml(ability)} → ${escapeHtml(group.to)}</b>` +
    `<span>กลุ่ม ${CUR.index + 1}/${CUR.groups.length} · ตัดสินแล้ว ${done}` +
    `${group.key in CUR.decisions ? " · (กลุ่มนี้ตัดสินไว้แล้ว)" : ""}</span>`;
  const row = $("cur-items");
  row.replaceChildren(...group.items.map((item, i) => {
    const card = document.createElement("figure");
    card.className = "cur-card";
    card.dataset.rel = item.rel;
    const rel = encodeURIComponent(item.rel);
    card.innerHTML =
      `<img loading="lazy" src="/api/thumb?rel=${rel}&t=${TOKEN}" alt="" data-full="/api/image?rel=${rel}&t=${TOKEN}">` +
      `<figcaption><kbd>${i + 1}</kbd> <b>${escapeHtml(item.title)}</b><br>` +
      `ยืนจาก ${escapeHtml(item.from)} · ${item.steps} ขั้น` +
      `${item.fav ? " · ★" : ""}${item.uses ? ` · ใช้ ${item.uses} ครั้ง` : ""}` +
      `${item.has_pin ? "" : " · ยังไม่มีหมุด"}</figcaption>`;
    card.addEventListener("click", (event) => {
      if (event.target.tagName === "IMG") window.open(event.target.dataset.full, "_blank");
      else toggleKeep(i);
    });
    return card;
  }));
  paintKeep();
}

function paintKeep() {
  for (const card of document.querySelectorAll("#cur-items .cur-card")) {
    card.classList.toggle("keep", CUR.keep.has(card.dataset.rel));
  }
  const group = CUR.groups[CUR.index];
  $("cur-count").textContent = `เก็บ ${CUR.keep.size} · ทิ้ง ${group.items.length - CUR.keep.size}`;
}

function toggleKeep(i) {
  const item = CUR.groups[CUR.index].items[i];
  if (!item) return;
  if (CUR.keep.has(item.rel)) CUR.keep.delete(item.rel); else CUR.keep.add(item.rel);
  paintKeep();
}

async function decide(keep) {
  const group = CUR.groups[CUR.index];
  try {
    const { decisions } = await api("curate/decide", { agent: CUR.agent, key: group.key, keep });
    CUR.decisions = decisions;
  } catch (error) {
    say(error.message, "err");
    return;
  }
  nextGroup();
}

function nextGroup() {
  const after = CUR.groups.findIndex((g, i) => i > CUR.index && !(g.key in CUR.decisions));
  if (after >= 0) showGroup(after);
  else if (CUR.index < CUR.groups.length - 1) showGroup(CUR.index + 1);
  else showSummary();
}

function showSummary() {
  let keep = 0, drop = 0, open = 0;
  for (const group of CUR.groups) {
    const kept = CUR.decisions[group.key];
    if (!kept) { open += 1; continue; }
    keep += kept.length;
    drop += group.items.length - kept.length;
  }
  $("cur-summary").innerHTML =
    `<li>ตัดสินแล้ว ${CUR.groups.length - open}/${CUR.groups.length} กลุ่ม</li>` +
    `<li>เก็บ <b>${keep}</b> ใบ · ทิ้ง <b>${drop}</b> ใบ</li>` +
    (open ? `<li>ยังไม่ตัดสิน ${open} กลุ่ม — ไม่ถูกแตะ (เก็บไว้ทุกใบ)</li>` : "") +
    "<li class=\"hint\">ใบที่ทิ้งย้ายเข้า .trash (กู้คืนได้) หมุด/แท็กของมันถูกล้างออก และจดไว้ให้ตอนรวมคลังไม่ฟื้นกลับมา · " +
    "ใบที่เหลือได้แท็กสกิลจากเว็บให้อัตโนมัติ</li>";
  $("cur-apply").disabled = false;
  curStage("done");
}

async function applyCurate() {
  $("cur-apply").disabled = true;
  try {
    const result = await api("curate/apply", { agent: CUR.agent });
    say(`ย้ายเข้า .trash ${result.removed} ใบ · เติมแท็กสกิล ${result.tagged} ใบ` +
        (result.errors.length ? ` · ทำไม่สำเร็จ ${result.errors.length}` : ""),
        result.errors.length ? "warn" : "ok");
    $("curate-dialog").close();
    await load();
  } catch (error) {
    say(error.message, "err");
    $("cur-apply").disabled = false;
  }
}

document.addEventListener("keydown", (event) => {
  if (!$("curate-dialog").open || $("cur-review").hidden) return;
  if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") return;
  const digit = /^[1-9]$/.test(event.key) ? Number(event.key) : null;
  if (digit) { toggleKeep(digit - 1); event.preventDefault(); return; }
  if (event.key === "Enter") { decide([...CUR.keep]); event.preventDefault(); }
  else if (event.key === "0") { decide([]); event.preventDefault(); }
  else if (event.key === "Backspace") { showGroup(CUR.index - 1); event.preventDefault(); }
  else if (event.key.toLowerCase() === "s") { nextGroup(); event.preventDefault(); }
});

$("btn-curate").addEventListener("click", openCurate);
$("cur-start").addEventListener("click", startCurate);
$("cur-ok").addEventListener("click", () => decide([...CUR.keep]));
$("cur-drop-all").addEventListener("click", () => decide([]));
$("cur-back").addEventListener("click", () => showGroup(CUR.index - 1));
$("cur-skip").addEventListener("click", nextGroup);
$("cur-finish").addEventListener("click", showSummary);
$("cur-review-again").addEventListener("click", () => { showGroup(0); curStage("review"); });
$("cur-apply").addEventListener("click", applyCurate);
for (const button of document.querySelectorAll("[data-cur-close]")) {
  button.addEventListener("click", () => $("curate-dialog").close());
}

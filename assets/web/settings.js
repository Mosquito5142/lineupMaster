/* แท็บ "ตั้งค่า" — ปรับค่าของโปรแกรมหลักแล้วมีผลทันที (ส่วนใหญ่ไม่ต้องเปิดโปรแกรมใหม่)
 *
 * ฟอร์มวาดจาก schema ที่เซิร์ฟเวอร์ส่งมา (lineupmaster/settings.py เป็นที่เดียวที่นิยามว่าปรับอะไรได้)
 * ค่าเก็บใน settings.json ทับ config.yaml — ↺ = ลบค่าที่ปรับ กลับไปใช้ของ config.yaml
 * ด้านบนมีแถบ "ดูสด" ว่าโหมดตามตัว (F9) รอบล่าสุดอ่านจอได้อะไร และทำไมแผนที่ขยับ/ไม่ขยับ
 */

const SET = { state: null, timers: {}, poll: null };

const SET_GROUPS = [
  ["auto", "โหมดตามตัว (F9 / F10)"],
  ["match", "เทียบชื่อโซนที่อ่านได้"],
  ["map", "หน้าแผนที่"],
  ["voice", "เสียงพูด"],
  ["window", "หน้าต่างโปรแกรม"],
];

const LIVE_RESULT = {
  moved: ["ขยับแผนที่แล้ว", "ok"],
  waiting: ["รอยืนยัน (อ่านได้ชื่อเดิมยังไม่ครบ)", "warn"],
  same: ["โซนเดิม ไม่ต้องขยับ", "ok"],
  busy: ["ไม่ขยับ — กำลังเลือกหมุด/ซูมรูปอยู่", "warn"],
  "no-match": ["อ่านได้แต่เทียบชื่อโซนไม่ผ่าน", "err"],
  "no-text": ["อ่านจอไม่เจอตัวหนังสือ", "err"],
  blank: ["แคปจอได้ภาพว่าง (เกมเต็มจอแบบผูกขาด?)", "err"],
};

function settingInput(field, value) {
  if (field.type === "bool") {
    return `<input type="checkbox" data-key="${field.key}"${value ? " checked" : ""}>`;
  }
  return `<input type="number" data-key="${field.key}" value="${value}" min="${field.min}" ` +
    `max="${field.max}" step="${field.step}">`;
}

/** ค่าแบบอ่านรู้เรื่อง — เปิด/ปิดเป็นคำไทย ตัวเลขโชว์ตรงๆ */
const settingText = (value) => (value === true ? "เปิด" : value === false ? "ปิด" : String(value));

function renderSettings() {
  const { schema, values, defaults, overrides } = SET.state;
  const box = $("settings-form");
  box.replaceChildren();
  for (const [group, title] of SET_GROUPS) {
    const fields = schema.filter((field) => field.group === group);
    if (!fields.length) continue;
    const section = document.createElement("section");
    section.className = "set-group";
    section.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
    for (const field of fields) {
      const changed = field.key in overrides;
      const row = document.createElement("div");
      row.className = `set-row${changed ? " changed" : ""}`;
      row.innerHTML =
        `<label class="set-label">${settingInput(field, values[field.key])}` +
        `<span><b>${escapeHtml(field.label)}</b>` +
        (field.help ? `<small>${escapeHtml(field.help)}</small>` : "") + `</span></label>` +
        `<span class="set-tag ${field.live ? "live" : "restart"}">` +
        `${field.live ? "มีผลทันที" : "เปิดโปรแกรมใหม่"}</span>` +
        (changed
          ? `<button type="button" class="chip small" data-reset="${field.key}" ` +
            `title="กลับไปใช้ค่าเริ่มต้น">↺ ${escapeHtml(settingText(defaults[field.key]))}</button>`
          : "");
      section.append(row);
    }
    box.append(section);
  }
}

async function loadSettings() {
  try {
    SET.state = await api("settings");
    renderSettings();
  } catch (error) {
    say(error.message, "err");
  }
}

async function saveSetting(key, value) {
  try {
    SET.state = await api("settings/set", { key, value });
    renderSettings();
    if (key === "voice.rate" || key === "voice.notes") loadVoice();   // ความเร็ว/โน้ตเปลี่ยน = ประโยคชุดใหม่
    say("บันทึกแล้ว — โปรแกรมหลักใช้ค่าใหม่รอบถัดไป", "ok");
  } catch (error) {
    say(error.message, "err");
    loadSettings();
  }
}

function renderLive(data) {
  const box = $("settings-live");
  const live = data.live;
  if (!live || data.age > 5) {
    box.className = "set-live idle";
    box.innerHTML = "<b>ดูสด:</b> โหมดตามตัวไม่ได้เปิดอยู่ — กด F9 ในเกมแล้วเดินไปมา ตรงนี้จะบอกว่าอ่านจอได้อะไร";
    return;
  }
  const [text, kind] = LIVE_RESULT[live.result] || [live.result, "warn"];
  const parts = [`<b>ดูสด</b> <span class="set-result ${kind}">${escapeHtml(text)}</span>`];
  if (live.lines && live.lines.length) {
    parts.push(`อ่านได้: ${live.lines.map((line) => `“${escapeHtml(line)}”`).join(" · ")}`);
  }
  if (live.zone) {
    parts.push(`จับคู่: <b>${escapeHtml(live.zone)}</b> · นับ ${live.count}/${live.confirm}`);
  }
  if (live.near) {
    parts.push(`เฉียดที่สุด: <b>${escapeHtml(live.near.label)}</b> คะแนน ${live.near.score} ` +
      `(ต้องได้ ≥ ${SET.state ? SET.state.values["match.cutoff"] : "?"})`);
  }
  if (live.map) parts.push(`แมพ ${escapeHtml(live.map)}`);
  box.className = "set-live";
  box.innerHTML = parts.join("<br>");
}

async function pollLive() {
  if ($("tab-settings").hidden) { clearInterval(SET.poll); SET.poll = null; return; }
  try { renderLive(await api("settings/live")); } catch { /* เซิร์ฟเวอร์ปิด — รอบหน้าลองใหม่ */ }
}

/* ---------- ย่อขนาดรูปทั้งคลัง ----------
 * PNG → WebP คุณภาพสูง ขนาดภาพเท่าเดิม (ดู lineupmaster/shrink.py) ส่งทีละใบให้เห็นความคืบหน้า
 * และกดหยุดกลางทางได้ — ใบที่ทำไปแล้วเสร็จสมบูรณ์ทีละใบ หยุดตรงไหนคลังก็ไม่พัง */
const SHRINK = { rels: [], bytes: 0, running: false, stop: false };
const mb = (bytes) => `${(bytes / 1e6).toFixed(bytes >= 1e8 ? 0 : 1)} MB`;

async function loadShrink() {
  if (SHRINK.running) return;
  try {
    const data = await api("shrink/candidates");
    SHRINK.rels = data.rels;
    SHRINK.bytes = data.bytes;
    $("shrink-info").textContent = data.rels.length
      ? `รูป PNG ${data.rels.length} ใบ รวม ${mb(data.bytes)} → แปลงเป็น WebP ความละเอียดเท่าเดิม ` +
        `ไฟล์เล็กลงราว 90% · รูปเดิมย้ายเข้า .trash (กู้คืนได้)`
      : "รูปทั้งคลังย่อแล้ว ไม่มีอะไรต้องทำ";
    $("shrink-go").disabled = !data.rels.length;
  } catch (error) {
    $("shrink-info").textContent = error.message;
  }
}

async function runShrink() {
  const rels = SHRINK.rels.slice();
  if (!rels.length) return;
  if (!(await uiConfirm(`แปลง ${rels.length} ใบเป็น WebP (ใช้เวลาราว ${Math.max(1, Math.round(rels.length * 0.4 / 60))} นาที)\n` +
      "หมุด แท็ก และสถิติตามไปครบ · รูป PNG เดิมย้ายเข้า .trash ไม่ได้ลบถาวร\n" +
      "ถ้าเปิดโปรแกรมหลักค้างอยู่ ให้ปิดก่อน แล้วเปิดใหม่หลังทำเสร็จ",
      { title: "ย่อขนาดรูปทั้งคลัง?", ok: "เริ่มย่อ" }))) return;

  SHRINK.running = true; SHRINK.stop = false;
  const bar = $("shrink-bar");
  bar.hidden = false; bar.max = rels.length; bar.value = 0;
  $("shrink-go").disabled = true;
  $("shrink-stop").hidden = false;
  let done = 0, skipped = 0, failed = 0, saved = 0;
  for (const rel of rels) {
    if (SHRINK.stop) break;
    try {
      const result = await api("shrink", { rel });
      if (result.skipped) skipped += 1;
      else { done += 1; saved += result.oldBytes - result.newBytes; }
    } catch {
      failed += 1;
    }
    bar.value = done + skipped + failed;
    $("shrink-info").textContent = `ย่อแล้ว ${done}/${rels.length} ใบ · ลดไปแล้ว ${mb(saved)}`;
  }
  SHRINK.running = false;
  bar.hidden = true;
  $("shrink-stop").hidden = true;
  const parts = [`ย่อ ${done} ใบ ลดไป ${mb(saved)}`];
  if (skipped) parts.push(`ข้าม ${skipped} ใบ (ไฟล์เดิมเล็กกว่าอยู่แล้ว)`);
  if (failed) parts.push(`พลาด ${failed} ใบ`);
  if (SHRINK.stop) parts.push("หยุดกลางทาง — กดอีกทีทำต่อจากที่ค้าง");
  say(parts.join(" · ") + " · รูปเดิมอยู่ใน .trash ถ้าดูแล้วชัดเหมือนเดิมค่อยล้างถังเพื่อเอาพื้นที่คืน",
      failed ? "err" : "ok");
  await load();            // rel เปลี่ยนเป็น .webp แล้ว — คลังในหน้าเว็บต้องอ่านใหม่
  await loadShrink();
}

$("shrink-go").addEventListener("click", () => runShrink().catch((error) => say(error.message, "err")));
$("shrink-stop").addEventListener("click", () => { SHRINK.stop = true; });

/* ---------- ไฟล์เสียงพูด ----------
 * สร้าง mp3 ของทุกใบไว้ก่อนเล่น (ดู lineupmaster/voice.py) — ยิงพร้อมกันทีละ 8 ประโยค
 * (แต่ละประโยครอบริการเสียงราว 1 วินาที ทีละอันจะนานเกิน) · กดหยุดได้ ที่ทำแล้วไม่หาย */
const VOICE = { missing: [], running: false, stop: false };

async function loadVoice() {
  if (VOICE.running) return;
  try {
    const data = await api("voice/candidates");
    VOICE.missing = data.missing;
    $("voice-info").textContent = data.missing.length
      ? `ยังไม่มีเสียง ${data.missing.length} จาก ${data.total} ประโยค · สร้างครั้งเดียว ` +
        `(ต้องต่อเน็ต) แล้วตอนเล่นเสียงขึ้นทันทีไม่ต้องใช้เน็ต`
      : `มีเสียงครบทั้ง ${data.total} ประโยคแล้ว · ใบใหม่ที่เพิ่มทีหลังโปรแกรมสร้างให้เองตอนกดครั้งแรก`;
    if (data.pruned) {
      $("voice-info").textContent += ` · ลบเสียงเก่าที่ไม่ใช้แล้ว ${data.pruned} ไฟล์ (${mb(data.freed)})`;
    }
    $("voice-go").disabled = !data.missing.length;
  } catch (error) {
    $("voice-info").textContent = error.message;
  }
}

async function runVoice() {
  const todo = VOICE.missing.slice();
  if (!todo.length) return;
  VOICE.running = true; VOICE.stop = false;
  const bar = $("voice-bar");
  bar.hidden = false; bar.max = todo.length; bar.value = 0;
  $("voice-go").disabled = true;
  $("voice-stop").hidden = false;
  let done = 0, failed = 0;
  const worker = async () => {
    while (todo.length && !VOICE.stop) {
      const text = todo.shift();
      try { await api("voice/make", { text }); done += 1; } catch { failed += 1; }
      bar.value = done + failed;
      $("voice-info").textContent = `สร้างแล้ว ${done}/${bar.max} ประโยค` + (failed ? ` · พลาด ${failed}` : "");
    }
  };
  // บริการเสียงตอบพลาดบ่อย (รอราว 2.6 วิกว่าจะรู้ว่าพลาด) — ยิงพร้อมกันหลายอันให้เวลารอซ้อนกัน
  await Promise.all(Array.from({ length: 8 }, worker));
  VOICE.running = false;
  bar.hidden = true;
  $("voice-stop").hidden = true;
  say(`สร้างเสียง ${done} ประโยค` + (failed ? ` · พลาด ${failed} (กดอีกทีทำเฉพาะที่ขาด)` : "") +
      (VOICE.stop ? " · หยุดกลางทาง" : ""), failed ? "err" : "ok");
  await loadVoice();
}

$("voice-go").addEventListener("click", () => runVoice().catch((error) => say(error.message, "err")));
$("voice-stop").addEventListener("click", () => { VOICE.stop = true; });
$("voice-sample").addEventListener("click", async () => {
  const button = $("voice-sample");
  button.disabled = true;
  try {
    // ต่อท้ายเวลาไว้ — ปรับความเร็วแล้วกดฟังใหม่ต้องได้ไฟล์ใหม่ ไม่ใช่ของที่เบราว์เซอร์แคชไว้
    const audio = new Audio(`/api/voice/sample?t=${encodeURIComponent(TOKEN)}&n=${Date.now()}`);
    audio.addEventListener("ended", () => { button.disabled = false; });
    audio.addEventListener("error", () => { button.disabled = false; say("ทดลองฟังไม่ได้ — เช็คว่าต่อเน็ตอยู่", "err"); });
    await audio.play();
  } catch (error) {
    button.disabled = false;
    say(error.message, "err");
  }
});

/* ---------- tracker.gg: bookmarklet + สถานะรายการที่เคยส่งเข้ามา ---------- */
const TRACKER = { href: "" };

async function loadTracker() {
  try {
    const data = await api("tracker/status");
    TRACKER.href = data.bookmarklet;
    $("tracker-link").href = data.bookmarklet;
    $("tracker-info").textContent = data.agents.length
      ? "ส่งเข้ามาแล้ว: " + data.agents.map((a) =>
        `${agentTh(a.agent)} ${a.count.toLocaleString()} ใบ (${new Date(a.saved * 1000).toLocaleString("th-TH")})`).join(" · ")
      : "ยังไม่เคยส่งรายการเข้ามา";
  } catch (error) {
    $("tracker-info").textContent = error.message;
  }
}

// ห้ามให้คลิกเฉยๆ รัน javascript: บนหน้านี้ — ลิงก์นั้นมีไว้ลากไปเป็นบุ๊กมาร์กเท่านั้น
$("tracker-link").addEventListener("click", (event) => {
  event.preventDefault();
  say("ลากปุ่มนี้ไปวางบนแถบบุ๊กมาร์กของเบราว์เซอร์ (ไม่ใช่คลิก) แล้วไปกดบนหน้า tracker.gg", "warn");
});
$("tracker-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(TRACKER.href);
    say("คัดลอกโค้ดแล้ว — สร้างบุ๊กมาร์กใหม่ แล้ววางโค้ดในช่อง URL", "ok");
  } catch {
    say("คัดลอกไม่ได้ — ลากปุ่มไปวางบนแถบบุ๊กมาร์กแทน", "err");
  }
});

function openSettingsTab() {
  loadTracker();
  loadSettings();
  loadShrink();
  loadVoice();
  pollLive();
  if (!SET.poll) SET.poll = setInterval(pollLive, 1000);
}

$("settings-form").addEventListener("change", (event) => {
  const input = event.target.closest("[data-key]");
  if (!input) return;
  const key = input.dataset.key;
  const value = input.type === "checkbox" ? input.checked : Number(input.value);
  clearTimeout(SET.timers[key]);
  SET.timers[key] = setTimeout(() => saveSetting(key, value), 300);
});
$("settings-form").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-reset]");
  if (!button) return;
  try {
    SET.state = await api("settings/reset", { key: button.dataset.reset });
    renderSettings();
    say("คืนค่าเริ่มต้นแล้ว", "ok");
  } catch (error) {
    say(error.message, "err");
  }
});
document.querySelector('.tab[data-tab="settings"]').addEventListener("click", openSettingsTab);

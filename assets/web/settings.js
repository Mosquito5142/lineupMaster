/* แท็บ "ตั้งค่า" — ปรับค่าของโปรแกรมหลักแล้วมีผลทันที (ส่วนใหญ่ไม่ต้องเปิดโปรแกรมใหม่)
 *
 * ฟอร์มวาดจาก schema ที่เซิร์ฟเวอร์ส่งมา (lineupmaster/settings.py เป็นที่เดียวที่นิยามว่าปรับอะไรได้)
 * ค่าเก็บใน settings.json ทับ config.yaml — ↺ = ลบค่าที่ปรับ กลับไปใช้ของ config.yaml
 * ด้านบนมีแถบ "ดูสด" ว่าโหมดตามตัว (F9) รอบล่าสุดอ่านจอได้อะไร และทำไมแผนที่ขยับ/ไม่ขยับ
 */

const SET = { state: null, timers: {}, poll: null };

const SET_GROUPS = [
  ["auto", "โหมดตามตัว (F9)"],
  ["match", "เทียบชื่อโซนที่อ่านได้"],
  ["map", "หน้าแผนที่"],
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

function openSettingsTab() {
  loadSettings();
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

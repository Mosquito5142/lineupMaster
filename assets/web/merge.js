/* รวมคลังจากโฟลเดอร์อื่น — หน้าตาของ lineupmaster/merge.py
 *
 * สามขั้นในกล่องเดียว: เลือกโฟลเดอร์ → ดูสรุป/ติ๊ก → ผลลัพธ์ · แผนตัวจริงเซิร์ฟเวอร์จำไว้เอง
 * หน้านี้ส่งกลับไปแค่สิ่งที่ผู้ใช้ติ๊ก (id ของรายการ) ไม่ได้ส่งแผนกลับไปทั้งก้อน
 * สเปก: docs/superpowers/specs/2026-09-25-library-merge-design.md
 */

const MERGE_KIND = {
  image: "รูป", pin: "หมุด", ability: "สกิล", callout: "ป้ายชื่อโซน", note: "โน้ต", gif: "คลิป gif",
};

function mergeStage(name) {
  for (const stage of ["pick", "preview", "done"]) $(`merge-${stage}`).hidden = stage !== name;
}

/** ข้อความผิดพลาดในกล่อง (toast อยู่ใต้ฉากมืดของ dialog มองไม่เห็น) — ว่าง = ซ่อน
 *  โชว์ที่บรรทัดของขั้นที่เปิดอยู่: ขั้นดูสรุปใช้ #merge-error ขั้นเลือกโฟลเดอร์ใช้ #merge-pick-error */
function mergeError(message) {
  for (const id of ["merge-error", "merge-pick-error"]) {
    $(id).textContent = message || "";
    $(id).hidden = true;
  }
  if (!message || !$("merge-dialog").open) return;
  const line = $("merge-preview").hidden ? $("merge-pick-error") : $("merge-error");
  line.hidden = false;
}

function mergeLine(html) {
  const li = document.createElement("li");
  li.innerHTML = html;
  return li;
}

async function openMerge() {
  mergeStage("pick");
  mergeError("");
  $("merge-path").value = "";
  const found = $("merge-found");
  found.replaceChildren(mergeLine('<span class="hint">กำลังหาโฟลเดอร์คลังอื่นในเครื่อง…</span>'));
  $("merge-dialog").showModal();
  try {
    const { folders } = await api("merge/candidates");
    found.replaceChildren();
    if (!folders.length) {
      found.append(mergeLine('<span class="hint">ไม่เจอโฟลเดอร์คลังอื่นแถว Desktop / Downloads — วาง path เองด้านล่าง</span>'));
    }
    for (const folder of folders) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "merge-folder";
      const seen = folder.machine ? ` · เปิดล่าสุดที่ ${escapeHtml(folder.machine)}` : "";
      button.innerHTML = `<b>${escapeHtml(folder.path)}</b>` +
        `<span>${folder.images} ใบ · แก้ล่าสุด ${escapeHtml(folder.modified.replace("T", " "))}${seen}</span>`;
      button.addEventListener("click", () => { $("merge-path").value = folder.path; previewMerge(); });
      const li = document.createElement("li");
      li.append(button);
      found.append(li);
    }
  } catch (error) {
    found.replaceChildren(mergeLine(`<span class="hint">${escapeHtml(error.message)}</span>`));
  }
}

/** ดูสรุป — ``keepError`` = เรียกซ้ำเองหลังรวมไม่สำเร็จ ให้ข้อความเดิมค้างไว้ให้อ่านบนสรุปใหม่ */
async function previewMerge({ keepError = false } = {}) {
  const path = $("merge-path").value.trim();
  if (!path) {
    say("เลือกโฟลเดอร์หรือวาง path ก่อน", "warn");
    mergeError("เลือกโฟลเดอร์หรือวาง path ก่อน");
    return;
  }
  if (!keepError) mergeError("");
  $("merge-go").disabled = true;
  try {
    renderMergePlan(await api("merge/preview", { path }));
    mergeStage("preview");
  } catch (error) {
    say(error.message, "err");
    mergeError(error.message);
  } finally {
    $("merge-go").disabled = false;
  }
}

/** ขนาดไฟล์อ่านง่าย — โน้ตมักไม่ถึง 1 KB */
function mergeSize(bytes) {
  return bytes < 1024 ? `${bytes} ไบต์` : `${Math.round(bytes / 1024)} KB`;
}

/** ค่าของที่ขัดกันแบบอ่านรู้เรื่อง — รูป/gif บอกขนาด/เวลา โน้ตบอกข้อความต้นๆ หมุด/ป้ายบอกพิกัด */
function mergeValue(kind, value) {
  if (value == null) return "—";
  const at = (point) => (point ? point.map((n) => Number(n).toFixed(3)).join(", ") : "—");
  const file = (info) => `${mergeSize(info.size)} · ${info.mtime.replace("T", " ")}`;
  if (kind === "image" || kind === "gif") return file(value);
  if (kind === "note") {
    const text = (value.text || "").replace(/\s+/g, " ").trim();
    return `${text ? `"${text.length > 80 ? `${text.slice(0, 80)}…` : text}" · ` : ""}${file(value)}`;
  }
  if (kind === "pin") return `ยืน ${at(value.from)} → ${at(value.to)}`;
  if (kind === "callout") return `${value.label || ""}${value.xy ? ` (${at(value.xy)})` : ""}`;
  return String(value);
}

/** รูปย่อสองฝั่งของรูปที่ขัดกัน — เซิร์ฟเวอร์หารูปจากสรุปที่จำไว้เอง ส่งไปแค่ id กับฝั่ง */
function mergeThumbs(item) {
  const one = (side, label) =>
    `<figure><img loading="lazy" alt="" src="/api/merge/image?side=${side}&id=${item.id}&t=${TOKEN}">` +
    `<figcaption>${label}</figcaption></figure>`;
  return `<span class="merge-thumbs">${one("here", "ที่นี่")}${one("there", "โฟลเดอร์นั้น")}</span>`;
}

function renderMergePlan(plan) {
  const c = plan.counts;
  $("merge-from").textContent = `จาก ${plan.there}`;

  const rows = [
    [c.copy, "รูปใหม่ที่จะก๊อปมา"],
    [c.rename, "ใบที่อีกเครื่องเปลี่ยนชื่อ/ย้าย — ทำตาม"],
    [c.remove, "ใบที่อีกเครื่องลบไปแล้ว — ย้ายเข้า .trash ตาม"],
    [c.sidecars, "โน้ต/คลิป gif ที่อีกเครื่องเพิ่มให้ไลน์อัพที่มีอยู่แล้ว"],
    [c.positions, "หมุดบนแผนที่ที่จะเพิ่ม"],
    [c.meta, "ใบที่ได้สกิล/แท็ก/ไม้ตายเพิ่ม"],
    [c.callouts, "ป้ายชื่อโซนที่จะเพิ่ม"],
    [c.taken, "รายการ \"เอามาแล้ว\" จากหน้าหาไลน์อัพ"],
  ].filter(([n]) => n > 0);
  const summary = $("merge-summary");
  summary.replaceChildren(...rows.map(([n, label]) => mergeLine(`${escapeHtml(label)} <b>${n}</b>`)));
  if (!rows.length && !plan.ask.length && !plan.conflicts.length) {
    summary.append(mergeLine("สองโฟลเดอร์มีของเหมือนกันแล้ว ไม่มีรูปหรือหมุดให้รวม"));
  }

  const ask = $("merge-ask");
  ask.replaceChildren(...plan.ask.map((item) => mergeLine(
    `<label><input type="checkbox" value="${item.id}"${item.default ? " checked" : ""}>` +
    `<span><code>${escapeHtml(item.rel)}</code><br><small>${escapeHtml(item.detail)}</small></span></label>`)));
  $("merge-ask-box").hidden = !plan.ask.length;

  // รูปชื่อซ้ำแต่เนื้อต่าง ผู้ใช้เลือกแล้วว่าตั้งต้นที่ "เอาอันที่แก้ล่าสุด" (เซิร์ฟเวอร์ตั้ง item.default
  // ตามเวลาแก้ไฟล์) แต่ยังเลือกเก็บทั้งคู่รายใบได้ · ที่ขัดกันอย่างอื่นเป็นแค่ค่าเดียว ใช้ติ๊กถูกพอ
  // (โน้ต/gif ติ๊กไว้ให้ถ้าของโฟลเดอร์นั้นใหม่กว่า — กติกาเดียวกับรูป)
  const conflicts = $("merge-conflicts");
  conflicts.replaceChildren(...plan.conflicts.map((item) => {
    const what = `${escapeHtml(MERGE_KIND[item.kind] || item.kind)} · <code>${escapeHtml(item.key)}</code><br>` +
      `<small>ที่นี่: ${escapeHtml(mergeValue(item.kind, item.here))} · ` +
      `โฟลเดอร์นั้น: ${escapeHtml(mergeValue(item.kind, item.there))}</small>`;
    if (item.kind !== "image") {
      const on = item.default === "there" ? " checked" : "";
      return mergeLine(`<label><input type="checkbox" value="${item.id}"${on}><span>${what}</span></label>`);
    }
    const pick = (value, label) =>
      `<option value="${value}"${(item.default || "here") === value ? " selected" : ""}>${label}</option>`;
    const newer = (side) => (item.newer === side ? " — ใหม่กว่า" : "");
    return mergeLine(`<span>${what}</span>${mergeThumbs(item)}<select data-conflict="${item.id}">` +
      pick("here", `เก็บของที่นี่${newer("here")}`) +
      pick("there", `ใช้ของโฟลเดอร์นั้น (ของที่นี่เข้า .trash)${newer("there")}`) +
      pick("both", "เก็บทั้งคู่ (ของโฟลเดอร์นั้นได้ชื่อใหม่)") + "</select>");
  }));
  $("merge-conflicts-box").hidden = !plan.conflicts.length;
  const clock = plan.clock || { here: true, there: true };
  $("merge-clock").hidden = clock.here && clock.there;

  const m = plan.machine;
  const who = (name) => (name ? ` (เปิดล่าสุดที่ ${name})` : "");
  fill($("merge-machine"), [
    ["there", `ใช้ของโฟลเดอร์นั้น${who(m.there)}`],
    ["here", `ใช้ของที่นี่${who(m.here)}`],
  ], { value: m.default });

  // config ตามค่าเฉพาะเครื่องไปจนกว่าผู้ใช้จะกดช่องนี้เอง (ดู listener ท้ายไฟล์)
  $("merge-config").dataset.touched = "";
  $("merge-config").checked = m.default === "there";
  $("merge-config-names").textContent = plan.config_differs.join(", ");
  $("merge-config-row").hidden = !plan.config_differs.length;

  const detail = [
    ...plan.rename_here.map((item) =>
      `เปลี่ยนชื่อ <code>${escapeHtml(item.old)}</code> → <code>${escapeHtml(item.new)}</code>`),
    ...plan.remove_here.map((item) => `ลบ (เข้า .trash) <code>${escapeHtml(item.rel)}</code>`),
    ...plan.skipped.map((item) => `ข้าม <code>${escapeHtml(item.rel)}</code> — ${escapeHtml(item.why)}`),
  ];
  $("merge-detail").replaceChildren(...detail.map(mergeLine));
  $("merge-more").hidden = !detail.length;
}

async function applyMerge() {
  const ticked = (id) => [...document.querySelectorAll(`#${id} input:checked`)].map((box) => Number(box.value));
  const images = (value) => [...document.querySelectorAll("#merge-conflicts select[data-conflict]")]
    .filter((select) => select.value === value).map((select) => Number(select.dataset.conflict));
  const choices = {
    ask: ticked("merge-ask"),
    take_there: [...ticked("merge-conflicts"), ...images("there")],
    keep_both: images("both"),
    machine: $("merge-machine").value,
    config: $("merge-config").checked,
  };
  $("merge-apply").disabled = true;
  mergeError("");
  try {
    const { report } = await api("merge/apply", { choices });
    const rows = [
      [report.copied, "ก๊อปรูปใหม่มา"], [report.renamed, "เปลี่ยนชื่อ/ย้ายตามอีกเครื่อง"],
      [report.removed, "ย้ายเข้า .trash"], [report.replaced, "แทนรูปด้วยของโฟลเดอร์นั้น"],
      [report.kept_both, "เก็บทั้งคู่ (ของโฟลเดอร์นั้นได้ชื่อใหม่)"],
      [report.sidecars, "โน้ต/คลิป gif ที่ได้มาเพิ่ม"],
      [report.sidecars_replaced, "แทนโน้ต/คลิป gif ด้วยของโฟลเดอร์นั้น"],
      [report.positions, "หมุดใหม่"], [report.meta, "ใบที่ได้สกิล/แท็ก/ไม้ตายเพิ่ม"],
      [report.callouts, "ป้ายชื่อโซนใหม่"], [report.taken, "รายการ \"เอามาแล้ว\" จากหน้าหาไลน์อัพ"],
    ].filter(([n]) => n > 0);
    const errors = report.errors || [];
    $("merge-report").replaceChildren(
      mergeLine(errors.length ? "<b>รวมเสร็จ แต่มีบางรายการทำไม่สำเร็จ</b>" : "<b>รวมเสร็จแล้ว</b>"),
      ...rows.map(([n, label]) => mergeLine(`${escapeHtml(label)} <b>${n}</b>`)),
      // ที่พังจะไม่ถูกจดว่าทำแล้ว — แก้สาเหตุ (เช่นปิดโปรแกรมที่เปิดไฟล์ค้าง) แล้วกดรวมใหม่ได้เลย
      ...errors.map((line) => mergeLine(`<small class="merge-error">ทำไม่สำเร็จ: ${escapeHtml(line)}</small>`)),
      mergeLine(`<small>ของเดิมที่ถูกแทน/ลบ และ json ก่อนรวม เก็บไว้ที่ <code>${escapeHtml(report.trash)}</code></small>`),
    );
    mergeStage("done");
    await load();
  } catch (error) {
    // แผนที่เซิร์ฟเวอร์จำไว้ถูกล้างแล้ว (ใช้ได้ครั้งเดียว) — บอกในกล่องแล้วดูสรุปใหม่ให้เลย
    // กดรวมซ้ำจะได้ใช้แผนล่าสุด ไม่ใช่แผนเก่าที่เซิร์ฟเวอร์ไม่มีแล้ว
    say(error.message, "err");
    mergeError(`รวมไม่สำเร็จ: ${error.message} — ดูสรุปใหม่ให้แล้ว ตรวจแล้วกดรวมอีกครั้ง`);
    await previewMerge({ keepError: true });
  } finally {
    $("merge-apply").disabled = false;
  }
}

$("btn-merge").addEventListener("click", openMerge);
$("merge-go").addEventListener("click", () => previewMerge());
$("merge-path").addEventListener("keydown", (event) => { if (event.key === "Enter") previewMerge(); });
$("merge-back").addEventListener("click", () => { mergeError(""); mergeStage("pick"); });
$("merge-apply").addEventListener("click", applyMerge);
$("merge-machine").addEventListener("change", () => {
  const box = $("merge-config");
  if (!box.dataset.touched) box.checked = $("merge-machine").value === "there";
});
$("merge-config").addEventListener("change", () => { $("merge-config").dataset.touched = "1"; });
for (const button of document.querySelectorAll("[data-merge-close]")) {
  button.addEventListener("click", () => $("merge-dialog").close());
}

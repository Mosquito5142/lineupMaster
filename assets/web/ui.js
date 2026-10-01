/* กล่องยืนยัน / แจ้ง / ถามข้อความ ของเราเอง — แทน confirm/alert/prompt ของเบราว์เซอร์ที่หลุดธีม
 *
 *   if (!(await uiConfirm("ลบใบนี้?", { title: "ลบไลน์อัพ", ok: "ลบ", danger: true }))) return;
 *   await uiAlert("ข้าม 3 ใบ: …", { title: "แชร์บางใบไม่ได้" });
 *   const text = await uiPrompt("พิมพ์ข้อความ", { title: "ตัวหนังสือบนรูป" });   // null = ยกเลิก
 */

function uiBox({ title = "", message = "", ok = "ตกลง", cancel = "ยกเลิก", danger = false, input = null }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "ui-box";
    const esc = (t) => String(t).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    dlg.innerHTML = `
      ${title ? `<h2>${esc(title)}</h2>` : ""}
      <div class="ui-msg">${esc(message)}</div>
      ${input !== null ? `<input type="text" value="${esc(input)}">` : ""}
      <menu>
        ${cancel ? `<button type="button" data-v="no">${esc(cancel)}</button>` : ""}
        <button type="button" class="primary${danger ? " danger" : ""}" data-v="yes">${esc(ok)}</button>
      </menu>`;
    const field = dlg.querySelector("input");
    const done = (yes) => {
      dlg.close();
      dlg.remove();
      resolve(input !== null ? (yes ? field.value : null) : yes);
    };
    dlg.querySelector('[data-v="yes"]').addEventListener("click", () => done(true));
    dlg.querySelector('[data-v="no"]')?.addEventListener("click", () => done(false));
    dlg.addEventListener("cancel", (event) => { event.preventDefault(); done(false); });
    if (field) field.addEventListener("keydown", (event) => { if (event.key === "Enter") done(true); });
    document.body.append(dlg);
    dlg.showModal();
    (field || dlg.querySelector('[data-v="yes"]')).focus();
  });
}

const uiConfirm = (message, opts = {}) => uiBox({ title: "ยืนยัน", ...opts, message });
const uiAlert = (message, opts = {}) => uiBox({ title: "", cancel: null, ...opts, message });
const uiPrompt = (message, opts = {}) => uiBox({ title: "", ...opts, message, input: opts.value || "" });

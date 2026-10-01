/* นำเข้าไลน์อัพจากคลิป YouTube — ส่วนเสริมของแท็บ "หาไลน์อัพจากเว็บ" (source.js)
 *
 * วางลิงก์ที่ติดเวลา (ปุ่มแชร์ใน ValoPlant) → เซิร์ฟเวอร์ถอดเฟรมเฉพาะ chapter ของท่านั้น (clipgrab.py)
 * → ได้ "ใบเสมือน" uid yt:… ที่ยังไม่มีขั้น แทรกไว้หน้าสุดของรายการแล้วเปิดดูทีละใบ
 * → คลิกเฟรมจากแถบเฟรมเข้าไปเป็นช่องในแผ่น (คลิกซ้ำ = เอาออก) → ที่เหลือใช้ของเดิมทั้งหมด:
 *   จัดหน้า เขียนทับ ปักหมุด และปุ่ม "เก็บเข้าคลัง" (source/take รู้จักใบคลิปแล้ว)
 */

const CLIP = {
  data: {},            // uid → {times, subs, gif: {start, end} | null} ของคลิปที่ดึงมาแล้ว
  picking: null,       // ตั้งช่วง GIF อยู่: null = ไม่ได้ตั้ง · [] = รอเฟรมเริ่ม · [i] = รอเฟรมจบ
};
const GIF_MAX = 10;    // ตรงกับ clipgrab.GIF_MAX

const clipTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const clipFrameUrl = (uid, i, small) =>
  `/api/clip/frame?uid=${encodeURIComponent(uid)}&i=${i}${small ? "&s=1" : ""}&t=${TOKEN}`;

async function loadClip() {
  const link = $("s-cliplink").value.trim();
  if (!link) { $("s-cliplink").focus(); return; }
  const button = $("s-clipgo");
  button.disabled = true;
  $("s-clipstate").textContent = "กำลังดึงคลิป… (ท่าละ ~20 วินาที ครั้งแรก)";
  try {
    const result = await api("clip/load", { link });
    const entry = result.entry;
    CLIP.data[entry.uid] = { times: result.times, subs: result.subs, gif: null };
    // แทรกไว้หน้าสุดของรายการ (ถ้าเคยดึงแล้วก็ย้ายขึ้นมา) แล้วเปิดใบนั้นทีละใบ
    SRC.shown = [entry, ...SRC.shown.filter((l) => l.uid !== entry.uid)];
    SRC.cursor = 0;
    $("s-clipstate").textContent = `ได้ ${result.times.length} เฟรม — คลิกเลือกเฟรมด้านล่างแผ่น`;
    if (SRC.grid) setGridMode(false); else showCurrent();
  } catch (error) {
    $("s-clipstate").textContent = "";
    toastSource(error.message, "err");
  } finally {
    button.disabled = false;
  }
}

/** เรียกจาก showCurrent — ใบคลิปคืน true (ไม่ต้องโหลดขั้นจากเว็บ) ใบอื่นซ่อนแถบเฟรมแล้วคืน false */
function showClipFrames(lineup) {
  const data = lineup && lineup.src === "yt" ? CLIP.data[lineup.uid] : null;
  $("s-clippane").hidden = !data;
  if (!data) return false;
  SRC.steps = [];
  SRC.marks = [];
  const strip = $("s-frames");
  strip.replaceChildren();
  data.times.forEach((time, i) => {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "frame";
    cell.dataset.i = i;
    cell.title = `${clipTime(time)} — คลิกเพื่อใส่เป็นช่องถัดไป`;
    cell.innerHTML = `<img loading="lazy" src="${clipFrameUrl(lineup.uid, i, true)}" alt=""><span>${clipTime(time)}</span>`;
    cell.addEventListener("click", () => (CLIP.picking ? pickGifFrame(lineup, i) : toggleClipFrame(lineup, i)));
    strip.append(cell);
  });
  $("s-subs").textContent = data.subs.length ? `ซับในช่วงนี้: “${data.subs.join(" ")}”` : "";
  CLIP.picking = null;
  $("s-gifprev").hidden = true;
  $("s-animonly").checked = false;
  refreshClipStrip();
  return true;
}

function toggleClipFrame(lineup, i) {
  const at = SRC.steps.findIndex((img) => img.dataset && img.dataset.frame === String(i));
  if (at >= 0) {                                  // คลิกซ้ำ = เอาเฟรมนั้นออกจากแผ่น
    SRC.steps.splice(at, 1);
    SRC.marks.splice(at, 1);
    SRC.selected = -1;
    autoLayout();
    drawSheet();
    syncPanelButtons();
    return;
  }
  const img = new Image();
  img.dataset.frame = String(i);
  img.onload = () => {
    if (currentSource() !== lineup) return;       // ผู้ใช้เปลี่ยนใบไประหว่างโหลด
    SRC.steps.push(img);
    SRC.marks.push([]);
    SRC.manual = false;
    autoLayout();
    drawSheet();
    syncPanelButtons();
  };
  img.onerror = () => toastSource("โหลดเฟรมไม่ขึ้น — ลองดึงคลิปใหม่", "err");
  img.src = clipFrameUrl(lineup.uid, i, false);
}

/** ไฮไลต์เฟรมที่อยู่ในแผ่นแล้ว พร้อมเลขลำดับช่อง — เรียกทุกครั้งที่แผ่นเปลี่ยน (รวมลบด้วยปุ่ม 🗑) */
function refreshClipStrip() {
  if ($("s-clippane").hidden) return;
  const lineup = currentSource();
  const data = lineup && CLIP.data[lineup.uid];
  const order = SRC.steps.map((img) => img.dataset && img.dataset.frame);
  for (const cell of $("s-frames").children) {
    const at = order.indexOf(cell.dataset.i);
    cell.classList.toggle("on", at >= 0);
    cell.dataset.n = at >= 0 ? String(at + 1) : "";
    const t = data ? data.times[Number(cell.dataset.i)] : 0;
    cell.classList.toggle("gif", !!(data && data.gif && t >= data.gif.start && t <= data.gif.end));
  }
  refreshGifBar(data);
}

/* ---------- GIF ช่วงยิง ----------
 * กด "ตั้งช่วง GIF" → คลิกเฟรมเริ่ม → คลิกเฟรมจบ (สลับลำดับให้เองถ้าคลิกกลับด้าน) · ยาวเกิน 6 วิตัดท้าย
 * ทำ GIF จริงตอนกด "ดูตัวอย่าง" หรือตอนเก็บเข้าคลัง (เซิร์ฟเวอร์ถอดช่วงนั้นใหม่ที่ 12 ภาพ/วิ) */
const STEP_AFTER = 0.5;          // เฟรมจบรวมไปอีกครึ่งวิ (ระยะห่างของเฟรมในแถบ) ไม่ให้ขาดจังหวะท้าย

function refreshGifBar(data) {
  const gif = data && data.gif;
  $("s-gifmode").classList.toggle("on", !!CLIP.picking);
  $("s-gifmode").textContent = CLIP.picking
    ? (CLIP.picking.length ? "คลิกเฟรมจบ…" : "คลิกเฟรมเริ่ม…") : "🎞 ตั้งช่วง GIF เอง";
  $("s-gifrange").textContent = gif
    ? `GIF ช่วงยิง ${clipTime(gif.start)}–${clipTime(gif.end)} (${(gif.end - gif.start).toFixed(1)} วิ) — เก็บเข้าคลังพร้อมรูป`
    : "GIF ช่วงยิง: ยังไม่ได้ตั้ง — ในเกมกด numpad * ดูได้";
  $("s-gifplay").hidden = !gif;
  $("s-gifclear").hidden = !gif;
}

function pickGifFrame(lineup, i) {
  const data = CLIP.data[lineup.uid];
  CLIP.picking.push(i);
  if (CLIP.picking.length === 2) {
    let [a, b] = CLIP.picking.map((k) => data.times[k]).sort((x, y) => x - y);
    b += STEP_AFTER;
    if (b - a > GIF_MAX) {
      b = a + GIF_MAX;
      toastSource(`GIF ยาวได้ไม่เกิน ${GIF_MAX} วิ — ตัดท้ายให้แล้ว`, "warn");
    }
    data.gif = { start: a, end: b };
    CLIP.picking = null;
    $("s-gifprev").hidden = true;
  }
  refreshClipStrip();
}

/** ติ๊ก "เก็บแค่ภาพเคลื่อนไหว" ไว้ไหม (ใบจากคลิปเท่านั้น) */
function clipAnimOnly(lineup) {
  return !!(lineup && lineup.src === "yt" && $("s-animonly").checked);
}

/** ช่วง GIF ของใบนี้ (ส่งไปกับ source/take) — ใบที่ไม่ได้มาจากคลิปหรือไม่ได้ตั้งช่วง = null */
function clipGifFor(lineup) {
  const data = lineup && lineup.src === "yt" ? CLIP.data[lineup.uid] : null;
  return data && data.gif ? data.gif : null;
}

async function previewGif() {
  const lineup = currentSource();
  const gif = clipGifFor(lineup);
  if (!gif) return;
  const button = $("s-gifplay");
  button.disabled = true;
  button.textContent = "กำลังทำ GIF…";
  try {
    const result = await api("clip/gif", { uid: lineup.uid, ...gif });
    const img = $("s-gifprev");
    img.src = `/api/clip/file?uid=${encodeURIComponent(lineup.uid)}&name=${encodeURIComponent(result.name)}&t=${TOKEN}`;
    img.hidden = false;
    $("s-gifrange").textContent += ` · ${(result.kb / 1024).toFixed(1)} MB`;
  } catch (error) {
    toastSource(error.message, "err");
  } finally {
    button.disabled = false;
    button.textContent = "▶ ดูตัวอย่าง";
  }
}

(() => {
  const original = syncPanelButtons;            // ลบ/คืนช่องด้วยปุ่มเดิม แถบเฟรมต้องตามด้วย
  window.syncPanelButtons = function () { original(); refreshClipStrip(); };
  // ปุ่ม "เปิดคลิป" ย้ายไปเปิดหน้าทำวิดีโอแล้ว (video.js) — แถบเฟรมข้างล่างนี้เหลือไว้จนกว่าจะเลิกใช้จริง
  $("s-gifmode").addEventListener("click", () => {
    CLIP.picking = CLIP.picking ? null : [];
    refreshClipStrip();
  });
  $("s-gifplay").addEventListener("click", previewGif);
  $("s-gifauto").addEventListener("click", async () => {
    const lineup = currentSource();
    const data = lineup && CLIP.data[lineup.uid];
    if (!data) return;
    try {
      const guess = await api(`clip/suggest?uid=${encodeURIComponent(lineup.uid)}`);
      if (guess.start == null) {
        toastSource("เดาช่วงยิงไม่ได้ (คลิปไม่มีช่วงเล็งนิ่ง) — กด ตั้งช่วง GIF เอง", "warn");
        return;
      }
      data.gif = { start: guess.start, end: guess.end };
      CLIP.picking = null;
      refreshClipStrip();
      previewGif();                      // ทำตัวอย่างให้ดูเลยว่าเดาตรงไหม
    } catch (error) { toastSource(error.message, "err"); }
  });
  $("s-gifclear").addEventListener("click", () => {
    const lineup = currentSource();
    if (lineup && CLIP.data[lineup.uid]) CLIP.data[lineup.uid].gif = null;
    $("s-gifprev").hidden = true;
    refreshClipStrip();
  });
})();

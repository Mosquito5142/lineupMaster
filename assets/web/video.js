/* หน้าทำวิดีโอ — ใบจากคลิป YouTube / ValoPlant (ส่วนเสริมของแท็บ "หาไลน์อัพจากเว็บ" source.js)
 *
 * วางลิงก์ที่ติดเวลา → เซิร์ฟเวอร์ตัดคลิปช่วงของท่านั้นมาไว้ในเครื่อง (proxy.mp4 · clipgrab.open_video)
 * → ฝั่งซ้ายเปลี่ยนจากแผ่นจัดรูปเป็นตัวเล่นคลิป + แถบเวลา: ตั้งจุดเริ่ม/จบ · เร่ง ×2 ×4 · ตัดข้าม
 * → กด "เก็บเข้าคลัง" (ปุ่มเดิมทางขวา) = ส่ง "แผน" ไปให้เซิร์ฟเวอร์ทำ WebP เคลื่อนไหวแล้วเก็บเป็นใบ
 *   ภาพเคลื่อนไหวล้วน (source/take) · ฟิลด์ แมพ/ฝั่ง/จุด/หมุด ทางขวาใช้ของเดิมทั้งหมด
 *
 * แผน = {start, end, parts: [{from, to, speed}]} วินาทีในคลิปจริง · speed 0 = ตัดข้าม
 * สูตร cleanPlan / planLength ต้องตรงกับ clipgrab.clean_plan / plan_length (มีเทสต์ทั้งสองฝั่ง)
 */

const PLAN_SPEEDS = [0, 1, 2, 4];
const r3 = (value) => Math.round(Number(value) * 1000) / 1000;

/** แผนมาตรฐาน: หนีบเข้าช่วง · ทับกันอันหลังชนะ · ×1 = ล้าง · ต่อช่วงที่ติดกัน (เหมือน clipgrab.clean_plan) */
function cleanPlan(plan) {
  const [start, end] = [r3(plan.start), r3(plan.end)].sort((a, b) => a - b);
  if (end - start < 0.05) throw new Error("ช่วงที่เก็บสั้นเกินไป");
  let spans = [];
  for (const part of plan.parts || []) {
    const speed = Number(part.speed);
    if (!PLAN_SPEEDS.includes(speed)) throw new Error(`ความเร็ว ${part.speed} ใช้ไม่ได้`);
    let [a, b] = [r3(part.from), r3(part.to)].sort((x, y) => x - y);
    a = Math.max(a, start);
    b = Math.min(b, end);
    if (b - a < 0.05) continue;
    const kept = [];
    for (const [x, y, s] of spans) {
      if (y <= a || x >= b) { kept.push([x, y, s]); continue; }
      if (x < a) kept.push([x, a, s]);
      if (y > b) kept.push([b, y, s]);
    }
    kept.push([a, b, speed]);
    spans = kept.sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  }
  const merged = [];
  for (const [x, y, s] of spans) {
    if (s === 1 || y - x < 0.05) continue;
    const last = merged[merged.length - 1];
    if (last && last[2] === s && Math.abs(last[1] - x) < 1e-6) last[1] = y;
    else merged.push([x, y, s]);
  }
  return { start, end, parts: merged.map(([x, y, s]) => ({ from: r3(x), to: r3(y), speed: s })) };
}

/** ความยาวภาพเคลื่อนไหวที่จะได้ (วินาที) หลังเร่ง/ตัด */
function planLength(plan) {
  const clean = cleanPlan(plan);
  let total = clean.end - clean.start;
  for (const part of clean.parts) {
    const span = part.to - part.from;
    total += (part.speed ? span / part.speed : 0) - span;
  }
  return Math.round(total * 1000) / 1000;
}

if (typeof module !== "undefined") {
  module.exports = { cleanPlan, planLength };
} else {
  /* ============================ ในเบราว์เซอร์ ============================ */
  const VID = {
    data: {},          // uid → คำตอบของ video/open (start, end, offset, fps, motion, suggest, subs)
    plan: {},          // uid → แผนที่กำลังแต่ง
    uid: null,         // ใบที่เปิดอยู่
    sel: null,         // ช่วงที่ลากเลือก {a, b}
    drag: null,        // "start" | "end" | {anchor, moved}
    preview: false,
    raf: 0,
  };
  const player = () => $("v-player");
  const current = () => VID.data[VID.uid];
  const plan = () => VID.plan[VID.uid];
  const fmt = (t) => {
    if (Math.abs(t) < 0.05) t = 0;          // ทศนิยมคลาดนิดเดียว ไม่ต้องโชว์ "-0:00.0"
    const sign = t < 0 ? "-" : "";
    t = Math.abs(t);
    return `${sign}${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;
  };

  /* ---------- เวลา: คลิปจริง ↔ ไฟล์ในเครื่อง ---------- */
  function clipNow() {
    const data = current();
    return data ? player().currentTime + data.offset : 0;
  }
  function seekClip(t) {
    const data = current();
    if (!data) return;
    t = Math.max(data.start, Math.min(data.end, t));
    player().currentTime = Math.max(0, t - data.offset);
    drawTimeline();
  }

  /* ---------- เปิดลิงก์ ---------- */
  async function openVideo() {
    const link = $("s-cliplink").value.trim();
    if (!link) { $("s-cliplink").focus(); return; }
    const button = $("s-clipgo");
    button.disabled = true;
    $("s-clipstate").textContent = "กำลังโหลดคลิปของท่านี้… (ครั้งแรก ~10 วินาที)";
    try {
      const result = await api("video/open", { link });
      const entry = result.entry;
      VID.data[entry.uid] = result;
      VID.plan[entry.uid] = cleanPlan(result.plan);
      SRC.shown = [entry, ...SRC.shown.filter((l) => l.uid !== entry.uid)];
      SRC.cursor = 0;
      $("s-clipstate").textContent = `เปิดแล้ว: ${entry.t}`;
      if (SRC.grid) setGridMode(false); else showCurrent();
    } catch (error) {
      $("s-clipstate").textContent = "เปิดคลิปไม่สำเร็จ — กดเปิดคลิปอีกครั้งเพื่อลองใหม่";
      toastSource(error.message, "err");
    } finally {
      button.disabled = false;
    }
  }

  const hasVideo = (lineup) => !!VID.data[lineup.uid];
  const opening = new Set();

  /** ใบจาก tracker.gg (มีแต่สตรีมวิดีโอ ไม่มีรูปทีละขั้น) → ให้เซิร์ฟเวอร์โหลดคลิปมาไว้ในเครื่อง แล้ววาดใบนี้ใหม่
   *  แมพ/ฝั่ง/สกิล/ชื่อ เติมจากใบอยู่แล้วใน showCurrent · พิกัดบนแผนที่ของ tracker.gg ไม่แปลง (จิ้มหมุดเอง) */
  async function openEntryVideo(lineup) {
    if (opening.has(lineup.uid)) return;
    opening.add(lineup.uid);
    stopPreview();
    $("s-videopane").hidden = true;
    $("s-sheetpane").hidden = false;
    $("s-loading").hidden = false;
    toastSource("กำลังโหลดวิดีโอจาก tracker.gg… (ครั้งแรกไม่กี่วินาที)", "info");
    try {
      const result = await api("video/open", { uid: lineup.uid });
      VID.data[lineup.uid] = result;
      VID.plan[lineup.uid] = cleanPlan(result.plan);
    } catch (error) {
      toastSource("เปิดวิดีโอไม่สำเร็จ: " + error.message, "err");
    } finally {
      opening.delete(lineup.uid);
      $("s-loading").hidden = true;
    }
    if (VID.data[lineup.uid] && currentSource() === lineup) showCurrent();
  }

  /** เรียกจาก showCurrent — ใบวิดีโอสลับฝั่งซ้ายเป็นหน้าทำวิดีโอแล้วคืน true · ใบอื่นสลับกลับแล้วคืน false */
  function showVideo(lineup) {
    const data = lineup ? VID.data[lineup.uid] : null;     // มีข้อมูลวิดีโอ = เปิดเป็นใบวิดีโอ (yt หรือ tg)
    $("s-videopane").hidden = !data;
    $("s-sheetpane").hidden = !!data;
    $("s-howtobox").hidden = !data;
    stopPreview();
    if (!data) {
      if (VID.uid) { player().pause(); player().removeAttribute("src"); player().load(); }
      VID.uid = null;
      return false;
    }
    if (VID.uid !== lineup.uid) {
      VID.uid = lineup.uid;
      VID.sel = null;
      $("v-loading").hidden = false;
      player().src = `/api/video/file?uid=${encodeURIComponent(lineup.uid)}&t=${TOKEN}`;
      $("s-howto").value = data.howto || "";               // ใบจาก tracker.gg: คำอธิบายของเว็บ แก้ต่อได้
      $("s-vsubs").textContent = data.subs && data.subs.length ? `ซับในช่วงนี้: “${data.subs.join(" ")}”` : "";
    }
    requestAnimationFrame(() => { drawTimeline(); refreshLength(); });
    return true;
  }

  /** แผนของใบนี้สำหรับส่งไปเก็บ — ใบอื่นคืน null · แผนใช้ไม่ได้ (ยาวเกิน/สั้นไป) เตือนแล้วคืน false */
  function videoPlanFor(lineup) {
    if (!lineup || !VID.data[lineup.uid]) return null;
    const data = VID.data[lineup.uid];
    const clean = cleanPlan(VID.plan[lineup.uid]);
    const length = planLength(clean);
    if (length > data.max + 1e-6) {
      toastSource(`ภาพเคลื่อนไหวยาว ${length.toFixed(1)} วิ เกิน ${data.max} วิ — เร่งหรือตัดเพิ่มอีก ${(length - data.max).toFixed(1)} วิ`, "warn");
      return false;
    }
    if (length < 0.3) { toastSource("ภาพเคลื่อนไหวสั้นเกินไป — ขยายช่วงหรือลดส่วนที่ตัด", "warn"); return false; }
    stopPreview();
    return clean;
  }

  /* ---------- แก้แผน ---------- */
  function setPlan(next) {
    try {
      VID.plan[VID.uid] = cleanPlan(next);
    } catch (error) {
      toastSource(error.message, "warn");
      return;
    }
    drawTimeline();
    refreshLength();
  }

  function applySpeed(speed) {
    if (!current()) return;
    if (!VID.sel) { toastSource("ลากเลือกช่วงบนแถบเวลาก่อน แล้วค่อยกดปุ่มนี้", "warn"); return; }
    const now = plan();
    setPlan({ ...now, parts: [...now.parts, { from: VID.sel.a, to: VID.sel.b, speed }] });
  }

  function setEdge(which, t) {
    const now = plan();
    if (which === "start") setPlan({ ...now, start: Math.min(t, now.end - 0.3) });
    else setPlan({ ...now, end: Math.max(t, now.start + 0.3) });
  }

  function refreshLength() {
    const data = current();
    if (!data) return;
    const now = plan();
    const length = planLength(now);
    const bad = length > data.max + 1e-6 || length < 0.3;
    $("v-len").textContent = `ภาพเคลื่อนไหว ${length.toFixed(1)} วิ` +
      (bad && length > data.max ? ` — เกิน ${data.max} วิ อยู่ ${(length - data.max).toFixed(1)} วิ` : "") +
      `  ·  ช่วงในคลิป ${(now.end - now.start).toFixed(1)} วิ`;
    $("v-len").classList.toggle("bad", bad);
    $("s-take").classList.toggle("over", bad);
  }

  /* ---------- แถบเวลา ---------- */
  const PAD = 8;               // ขอบซ้ายขวา (px จอ)
  const LABEL_H = 18;          // แถบป้าย ×2/×4/ตัด ด้านบน

  function timeline() {
    const canvas = $("v-timeline");
    const data = current();
    const width = canvas.clientWidth;
    return {
      canvas, data, width,
      x: (t) => PAD + (t - data.start) / (data.end - data.start) * (width - 2 * PAD),
      t: (x) => data.start + (x - PAD) / (width - 2 * PAD) * (data.end - data.start),
    };
  }

  function drawTimeline() {
    const data = current();
    const canvas = $("v-timeline");
    if (!data || $("s-videopane").hidden || !canvas.clientWidth) return;
    const ratio = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (canvas.width !== Math.round(W * ratio)) canvas.width = Math.round(W * ratio);
    if (canvas.height !== Math.round(H * ratio)) canvas.height = Math.round(H * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const { x } = timeline();
    const now = plan();
    const top = LABEL_H, bottom = H - 14;

    // กราฟการขยับ — แท่งสูง = ภาพเปลี่ยนมาก (ช่วงเล็งนิ่งจะแบนราบ)
    const values = data.motion.values;
    const sorted = [...values].sort((a, b) => a - b);
    const cap = Math.max(1, sorted[Math.floor(sorted.length * 0.95)] || 1);
    ctx.fillStyle = "rgba(139,151,159,.55)";
    data.motion.times.forEach((t, i) => {
      const h = Math.min(1, values[i] / cap) * (bottom - top);
      const x0 = x(t);
      ctx.fillRect(x0 - 1, bottom - h, 2, h);
    });

    // นอกช่วงที่เก็บ = มืด
    ctx.fillStyle = "rgba(0,0,0,.55)";
    ctx.fillRect(0, 0, x(now.start), H);
    ctx.fillRect(x(now.end), 0, W - x(now.end), H);

    // ช่วงเร่ง/ตัด
    ctx.font = "600 11px Kanit, sans-serif";
    ctx.textBaseline = "middle";
    for (const part of now.parts) {
      const a = x(part.from), b = x(part.to);
      const cut = part.speed === 0;
      ctx.fillStyle = cut ? "rgba(255,90,90,.28)" : part.speed === 4 ? "rgba(125,211,252,.30)" : "rgba(125,211,252,.16)";
      ctx.fillRect(a, top, b - a, bottom - top);
      ctx.fillStyle = cut ? "#FF5A5A" : "#7DD3FC";
      ctx.fillRect(a, 2, b - a, LABEL_H - 4);
      if (b - a > 26) {
        ctx.fillStyle = "#0F1923";
        ctx.fillText(cut ? "ตัด" : `×${part.speed}`, a + 4, LABEL_H / 2);
      }
    }

    // ช่วงที่ลากเลือก
    if (VID.sel) {
      ctx.fillStyle = "rgba(236,232,225,.16)";
      ctx.fillRect(x(VID.sel.a), top, x(VID.sel.b) - x(VID.sel.a), bottom - top);
      ctx.strokeStyle = "rgba(236,232,225,.7)";
      ctx.strokeRect(x(VID.sel.a) + .5, top + .5, x(VID.sel.b) - x(VID.sel.a) - 1, bottom - top - 1);
    }

    // จุดเริ่ม/จบ
    ctx.fillStyle = "#FF4655";
    for (const t of [now.start, now.end]) {
      ctx.fillRect(x(t) - 2, 0, 4, H);
      ctx.fillRect(x(t) - 6, bottom, 12, 6);
    }

    // ตัวเลขเวลาใต้แถบ (ทุก 5 วิ นับจากต้นท่า)
    ctx.fillStyle = "#56626B";
    ctx.font = "10px Kanit, sans-serif";
    for (let s = 0; s <= data.end - data.start; s += 5) ctx.fillText(`${s}s`, x(data.start + s) + 2, H - 5);

    // หัวเล่น
    const head = x(clipNow());
    ctx.fillStyle = "#FFD479";
    ctx.fillRect(head - 1, 0, 2, H);

    $("v-time").textContent = `${fmt(clipNow() - data.start)} / ${fmt(data.end - data.start)}`;
  }

  function onPointerDown(event) {
    if (!current()) return;
    const { canvas, x, t } = timeline();
    const px = event.offsetX;
    const now = plan();
    canvas.setPointerCapture(event.pointerId);
    stopPreview();
    player().pause();
    if (Math.abs(px - x(now.start)) <= 7) VID.drag = "start";
    else if (Math.abs(px - x(now.end)) <= 7) VID.drag = "end";
    else {
      VID.drag = { anchor: t(px), moved: false };
      seekClip(t(px));
    }
  }

  function onPointerMove(event) {
    if (!current()) return;
    const { canvas, x, t } = timeline();
    const px = event.offsetX;
    if (!VID.drag) {
      const now = plan();
      const edge = Math.abs(px - x(now.start)) <= 7 || Math.abs(px - x(now.end)) <= 7;
      canvas.style.cursor = edge ? "ew-resize" : "crosshair";
      return;
    }
    const at = t(px);
    if (VID.drag === "start" || VID.drag === "end") {
      setEdge(VID.drag, at);
      seekClip(VID.drag === "start" ? plan().start : plan().end);
      return;
    }
    if (Math.abs(x(at) - x(VID.drag.anchor)) > 4) VID.drag.moved = true;
    if (VID.drag.moved) VID.sel = { a: Math.min(at, VID.drag.anchor), b: Math.max(at, VID.drag.anchor) };
    seekClip(at);
  }

  function onPointerUp(event) {
    if (!current() || !VID.drag) return;
    const drag = VID.drag;
    VID.drag = null;
    if (typeof drag === "object" && !drag.moved) {
      // คลิกเฉยๆ บนช่วงที่เร่ง/ตัดไว้ = เลือกช่วงนั้น (กด ×1 เพื่อล้าง) · คลิกที่ว่าง = ล้างที่เลือก
      const hitPart = plan().parts.find((p) => p.from <= drag.anchor && drag.anchor < p.to);
      VID.sel = hitPart ? { a: hitPart.from, b: hitPart.to } : null;
    }
    drawTimeline();
  }

  /* ---------- เล่น / ดูตัวอย่าง ---------- */
  function loop() {
    cancelAnimationFrame(VID.raf);
    const step = () => {
      const data = current();
      if (!data) return;
      if (VID.preview) {
        const now = plan();
        const t = clipNow();
        if (t >= now.end - 0.01) { stopPreview(); drawTimeline(); return; }
        const part = now.parts.find((p) => p.from <= t + 1e-3 && t < p.to);
        if (part && part.speed === 0) seekClip(part.to);
        else {
          const rate = part ? part.speed : 1;
          if (player().playbackRate !== rate) player().playbackRate = rate;
        }
      } else if (clipNow() >= data.end) {
        player().pause();
      }
      drawTimeline();
      if (!player().paused) VID.raf = requestAnimationFrame(step);
    };
    VID.raf = requestAnimationFrame(step);
  }

  function togglePlay() {
    if (!current()) return;
    stopPreview();
    if (player().paused) {
      if (clipNow() >= current().end - 0.05) seekClip(current().start);
      player().play();
    } else player().pause();
  }

  function startPreview() {
    if (!current()) return;
    VID.preview = true;
    $("v-preview").textContent = "■ หยุดตัวอย่าง";
    seekClip(plan().start);
    player().play();
  }

  function stopPreview() {
    if (!VID.preview) return;
    VID.preview = false;
    player().pause();
    player().playbackRate = 1;
    $("v-preview").textContent = "👁 ดูตัวอย่าง";
  }

  function stepFrames(direction, seconds) {
    if (!current()) return;
    stopPreview();
    player().pause();
    seekClip(clipNow() + direction * (seconds || 1 / (current().fps || 30)));
  }

  function onKey(event) {
    if ($("tab-source").hidden || $("s-videopane").hidden || !current()) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
    const key = event.key.toLowerCase();
    if (key === " ") togglePlay();
    else if (key === "arrowleft") stepFrames(-1, event.shiftKey ? 1 : 0);
    else if (key === "arrowright") stepFrames(1, event.shiftKey ? 1 : 0);   // ในหน้านี้ → ไม่ใช่ "ไม่เอา"
    else if (key === "i") setEdge("start", clipNow());
    else if (key === "o") setEdge("end", clipNow());
    else if (key === "escape") { VID.sel = null; drawTimeline(); }
    else return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function wireVideo() {
    const video = player();
    video.addEventListener("loadeddata", () => {
      $("v-loading").hidden = true;
      const data = current();
      if (data) seekClip(plan().start);
    });
    video.addEventListener("error", () => {
      if (!VID.uid) return;
      $("v-loading").hidden = false;
      $("v-loading").textContent = "เล่นคลิปไม่ได้ — วางลิงก์แล้วกดเปิดคลิปใหม่อีกครั้ง";
    });
    video.addEventListener("play", loop);
    video.addEventListener("pause", () => { $("v-play").textContent = "▶"; drawTimeline(); });
    video.addEventListener("playing", () => { $("v-play").textContent = "⏸"; });
    video.addEventListener("seeked", drawTimeline);

    const canvas = $("v-timeline");
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    window.addEventListener("resize", drawTimeline);

    $("s-clipgo").addEventListener("click", openVideo);
    $("s-cliplink").addEventListener("keydown", (event) => { if (event.key === "Enter") openVideo(); });
    $("v-play").addEventListener("click", togglePlay);
    $("v-prev").addEventListener("click", (event) => stepFrames(-1, event.shiftKey ? 1 : 0));
    $("v-next").addEventListener("click", (event) => stepFrames(1, event.shiftKey ? 1 : 0));
    $("v-in").addEventListener("click", () => setEdge("start", clipNow()));
    $("v-out").addEventListener("click", () => setEdge("end", clipNow()));
    $("v-x2").addEventListener("click", () => applySpeed(2));
    $("v-x4").addEventListener("click", () => applySpeed(4));
    $("v-cut").addEventListener("click", () => applySpeed(0));
    $("v-x1").addEventListener("click", () => applySpeed(1));
    $("v-reset").addEventListener("click", () => { VID.sel = null; setPlan({ ...plan(), parts: [] }); });
    $("v-auto").addEventListener("click", () => {
      if (!current()) return;
      VID.sel = null;
      setPlan(current().suggest);
      startPreview();                       // เล่นให้ดูเลยว่าเดาตรงไหม
    });
    $("v-preview").addEventListener("click", () => (VID.preview ? stopPreview() : startPreview()));
    document.addEventListener("keydown", onKey, true);   // ก่อนตัวของ source.js (→ = ไม่เอา)
  }

  window.showVideo = showVideo;
  window.hasVideo = hasVideo;
  window.openEntryVideo = openEntryVideo;
  window.videoPlanFor = videoPlanFor;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wireVideo);
  else wireVideo();
}

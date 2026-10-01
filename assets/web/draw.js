/* วาด/เขียนทับรูปไลน์อัพ — ปากกา · ลูกศร · วงกลม · กรอบ · ตัวหนังสือ
 *
 * แทนการเปิดแอพแต่งรูปแยก: วาดบน <canvas> ขนาดเท่ารูปจริง (พิกัดเป็นพิกเซลของรูป ไม่ใช่ของจอ)
 * เก็บทุกเส้นเป็นรายการ ย้อนได้ทีละเส้นจนกว่าจะบันทึก · บันทึก = รวมรูป+เส้นเป็น PNG แล้วส่งให้
 * เซิร์ฟเวอร์เขียนทับไฟล์จริง (ต้นฉบับสำรองไว้ที่ .originals/ ฝั่ง Python — ดู Store.save_drawing)
 *
 * ส่วนบนเป็นฟังก์ชันล้วน ไม่แตะ DOM (ทดสอบด้วย node: tests/web/draw.test.js)
 */

const DRAW_COLORS = ["#ff3b30", "#ffd400", "#34c759", "#ffffff"];

/** ความหนาเส้น 3 ระดับ ตามขนาดรูป — รูปรวม 4 ขั้นกว้าง 2560px เส้น 3px มองไม่เห็นเลย */
function drawWidths(imageWidth) {
  const base = Math.max(2, Math.round(imageWidth / 450));
  return [base, base * 2, Math.round(base * 3.5)];
}

/** จุดบนจอ (clientX/Y) → พิกเซลของรูป — canvas ถูกย่อด้วย CSS ให้พอดีกล่อง */
function toImagePoint(clientX, clientY, rect, width, height) {
  const x = ((clientX - rect.left) / rect.width) * width;
  const y = ((clientY - rect.top) / rect.height) * height;
  return [Math.max(0, Math.min(width, x)), Math.max(0, Math.min(height, y))];
}

/** สองขาของหัวลูกศรที่ปลาย b (ชี้จาก a ไป b) */
function arrowHead(a, b, size) {
  const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const wing = Math.PI / 7;
  return [
    [b[0] - size * Math.cos(angle - wing), b[1] - size * Math.sin(angle - wing)],
    [b[0] - size * Math.cos(angle + wing), b[1] - size * Math.sin(angle + wing)],
  ];
}

/** วาดเส้นเดียวลง context (ใช้ทั้งตอนโชว์และตอนรวมเป็นไฟล์ — ภาพเดียวกันเป๊ะ) */
function paintShape(ctx, shape) {
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle = shape.color;
  ctx.lineWidth = shape.width;
  ctx.lineCap = ctx.lineJoin = "round";
  // ขอบดำบางๆ รอบทุกอย่าง — สีสดบนฉากเกมที่สีจัดจะจมหายถ้าไม่มีขอบ
  ctx.shadowColor = "rgba(0,0,0,.85)";
  ctx.shadowBlur = Math.max(2, shape.width * 0.8);
  const [a, b] = [shape.a, shape.b];
  if (shape.tool === "pen") {
    ctx.beginPath();
    shape.points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.stroke();
  } else if (shape.tool === "arrow") {
    const head = arrowHead(a, b, shape.width * 4.5);
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
    ctx.moveTo(head[0][0], head[0][1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(head[1][0], head[1][1]);
    ctx.stroke();
  } else if (shape.tool === "circle") {
    ctx.beginPath();
    ctx.ellipse((a[0] + b[0]) / 2, (a[1] + b[1]) / 2,
      Math.abs(b[0] - a[0]) / 2, Math.abs(b[1] - a[1]) / 2, 0, 0, Math.PI * 2);
    ctx.stroke();
  } else if (shape.tool === "rect") {
    ctx.strokeRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]),
      Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
  } else if (shape.tool === "text") {
    ctx.font = `bold ${shape.width * 9}px "Bai Jamjuree", "Leelawadee UI", sans-serif`;
    ctx.textBaseline = "top";
    ctx.lineWidth = Math.max(2, shape.width * 1.2);
    ctx.strokeStyle = "rgba(0,0,0,.9)";
    ctx.shadowBlur = 0;
    ctx.strokeText(shape.text, a[0], a[1]);
    ctx.fillText(shape.text, a[0], a[1]);
  }
  ctx.restore();
}

if (typeof module !== "undefined") {
  module.exports = { drawWidths, toImagePoint, arrowHead, DRAW_COLORS };
}

/* ---------- ส่วนเบราว์เซอร์ ---------- */
if (typeof document !== "undefined") {
  (() => {
    const dlg = () => document.getElementById("draw-dialog");
    const canvas = () => document.getElementById("draw-canvas");
    let image = null;          // รูปจริงที่โหลดมา
    let shapes = [];           // เส้นที่วาดแล้ว
    let live = null;           // เส้นที่กำลังลากอยู่
    let tool = "arrow";
    let color = DRAW_COLORS[0];
    let widthLevel = 1;
    let onSave = null;

    function redraw() {
      const c = canvas();
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.drawImage(image, 0, 0);
      for (const shape of shapes) paintShape(ctx, shape);
      if (live) paintShape(ctx, live);
      document.getElementById("draw-undo").disabled = !shapes.length;
      document.getElementById("draw-save").disabled = !shapes.length;
    }

    function point(event) {
      const c = canvas();
      return toImagePoint(event.clientX, event.clientY, c.getBoundingClientRect(), c.width, c.height);
    }

    function currentWidth() { return drawWidths(image.naturalWidth)[widthLevel]; }

    function onDown(event) {
      if (event.button !== 0) return;
      const at = point(event);
      if (tool === "text") {
        uiPrompt("พิมพ์ข้อความที่จะเขียนลงรูป", { title: "ตัวหนังสือบนรูป", ok: "ใส่" }).then((raw) => {
          const text = (raw || "").trim();
          if (text) { shapes.push({ tool, color, width: currentWidth(), a: at, text }); redraw(); }
        });
        return;
      }
      canvas().setPointerCapture(event.pointerId);
      live = tool === "pen"
        ? { tool, color, width: currentWidth(), points: [at] }
        : { tool, color, width: currentWidth(), a: at, b: at };
      redraw();
    }

    function onMove(event) {
      if (!live) return;
      const at = point(event);
      if (live.tool === "pen") live.points.push(at);
      else live.b = at;
      redraw();
    }

    function onUp() {
      if (!live) return;
      const moved = live.tool === "pen"
        ? live.points.length > 1
        : Math.hypot(live.b[0] - live.a[0], live.b[1] - live.a[1]) > 3;
      if (moved) shapes.push(live);     // คลิกเฉยๆ ไม่ลาก = ไม่นับเป็นเส้น
      live = null;
      redraw();
    }

    function pick(group, value) {
      for (const button of document.querySelectorAll(`#draw-dialog [data-${group}]`)) {
        button.classList.toggle("on", button.dataset[group] === String(value));
      }
    }

    async function close(force = false) {
      if (!force && shapes.length &&
          !(await uiConfirm("เส้นที่วาดไว้จะหายทั้งหมด", { title: "ทิ้งที่วาด?", ok: "ทิ้ง", danger: true }))) {
        return false;
      }
      shapes = [];
      live = null;
      dlg().close();
      return true;
    }

    /** เปิดตัววาดกับรูปนี้ — save(dataUrl) คืน Promise<boolean> (true = เซฟสำเร็จ ปิดตัววาดเลย) */
    window.openDrawer = (src, title, save) => {
      onSave = save;
      shapes = [];
      live = null;
      document.getElementById("draw-title").textContent = title;
      image = new Image();
      image.onload = () => {
        const c = canvas();
        c.width = image.naturalWidth;
        c.height = image.naturalHeight;
        redraw();
      };
      image.src = src;
      dlg().showModal();
    };

    function wire() {
      const c = canvas();
      c.addEventListener("pointerdown", onDown);
      c.addEventListener("pointermove", onMove);
      c.addEventListener("pointerup", onUp);
      c.addEventListener("pointercancel", onUp);

      const swatches = document.getElementById("draw-colors");
      DRAW_COLORS.forEach((value) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "swatch";
        button.style.background = value;
        button.dataset.color = value;
        button.title = "สี";
        swatches.append(button);
      });
      for (const button of document.querySelectorAll("#draw-dialog [data-tool]")) {
        button.addEventListener("click", () => { tool = button.dataset.tool; pick("tool", tool); });
      }
      for (const button of document.querySelectorAll("#draw-dialog [data-color]")) {
        button.addEventListener("click", () => { color = button.dataset.color; pick("color", color); });
      }
      for (const button of document.querySelectorAll("#draw-dialog [data-width]")) {
        button.addEventListener("click", () => {
          widthLevel = Number(button.dataset.width);
          pick("width", widthLevel);
        });
      }
      pick("tool", tool);
      pick("color", color);
      pick("width", widthLevel);

      document.getElementById("draw-undo").addEventListener("click", () => { shapes.pop(); redraw(); });
      document.getElementById("draw-clear").addEventListener("click", () => {
        if (!shapes.length) return;
        uiConfirm("เส้นที่วาดไว้จะหายทั้งหมด", { title: "ล้างที่วาด?", ok: "ล้าง", danger: true })
          .then((yes) => { if (yes) { shapes = []; redraw(); } });
      });
      document.getElementById("draw-cancel").addEventListener("click", () => close());
      dlg().addEventListener("cancel", (event) => { event.preventDefault(); close(); });   // Esc
      dlg().addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
          event.preventDefault();
          shapes.pop();
          redraw();
        }
      });
      document.getElementById("draw-save").addEventListener("click", async () => {
        const button = document.getElementById("draw-save");
        button.disabled = true;
        live = null;
        redraw();
        if (await onSave(canvas().toDataURL("image/png"))) close(true);
        else button.disabled = false;
      });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
    else wire();
  })();
}

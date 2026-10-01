/* แผนที่สำหรับจิ้มหมุด — ซูมได้ เลื่อนได้ หมุนได้ ใช้ร่วมกันทั้งแท็บ "คลังของเรา" และ "หาไลน์อัพจากเว็บ"
 *
 * **พิกัดที่คืนออกไปเป็นพิกัดของรูปแผนที่ต้นฉบับเสมอ (สัดส่วน 0..1) ไม่ใช่พิกัดบนจอ** —
 * ต่อให้ซูมเข้าไป 8 เท่าแล้วหมุน 137° อยู่ จิ้มตรงไหนก็ได้พิกัดเดิมที่ถูกต้อง เพราะปล่อยให้
 * เบราว์เซอร์คิดเมทริกซ์ผกผันให้ผ่าน ``getScreenCTM().inverse()`` ไม่ได้เขียนสูตรหมุนเอง
 * (เขียนเองพลาดง่ายมากตอนมุมไม่ใช่ 90 เท่า — บทเรียนจากฝั่ง Qt ที่เคยทำมาแล้ว)
 *
 * หมุนแค่ "ภาพที่เห็น" เท่านั้น ไม่ได้แตะพิกัดที่เก็บลงไฟล์เลยสักนิด
 */

function createMapView(stage, { onPick } = {}) {
  const NS = "http://www.w3.org/2000/svg";
  const el = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
  };

  const svg = el("svg", { class: "mv-svg" });
  const layer = el("g");
  const image = el("image", { x: 0, y: 0 });
  layer.append(image);
  svg.append(layer);
  stage.append(svg);

  const view = { scale: 1, tx: 0, ty: 0, rot: 0 };
  let size = { w: 1000, h: 1000 };       // ขนาดจริงของรูปแผนที่ (พิกเซล)
  let data = { pins: [], labels: {}, callouts: [], current: null, pending: null, zones: [] };
  let mapName = null;
  let facing = null;            // { key, own, enemy } จุดเกิดฝั่งเรา/อีกฝั่ง — ดู faceSpawn()
  let animateNext = false;      // เส้นวิถีเพิ่งเปลี่ยน → รอบวาดถัดไปให้ลากเส้นแบบมีแอนิเมชัน
  let lastTraj = "";
  const listeners = [];

  /* ---------- แปลงพิกัด ---------- */
  function toLocal(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = layer.getScreenCTM();
    if (!matrix) return null;
    return point.matrixTransform(matrix.inverse());   // ได้พิกเซลบนรูปต้นฉบับเลย
  }

  function normalized(event) {
    const local = toLocal(event);
    if (!local) return null;
    return [local.x / size.w, local.y / size.h];
  }

  /* ---------- มุมมอง ---------- */
  function apply() {
    layer.setAttribute("transform",
      `translate(${view.tx} ${view.ty}) scale(${view.scale}) rotate(${view.rot} ${size.w / 2} ${size.h / 2})`);
    for (const fn of listeners) fn(view);
    draw();
  }

  /** ขนาดกรอบหลังหมุน — ใช้คำนวณ "พอดีจอ" ให้เห็นแมพครบทุกมุมแม้หมุนเอียงอยู่ */
  function rotatedBox() {
    const rad = view.rot * Math.PI / 180;
    const c = Math.abs(Math.cos(rad));
    const s = Math.abs(Math.sin(rad));
    return { w: size.w * c + size.h * s, h: size.w * s + size.h * c };
  }

  /** หันแมพให้จุดเกิดฝั่งเราอยู่ล่าง จุดเกิดอีกฝั่งอยู่บน — เหมือนตั้งมินิแมพในเกมให้หมุนตามฝั่ง
   * ปัดเป็นทีละ 90° ให้แมพตั้งตรง ไม่เอียงตามแนวจุดเกิดที่ไม่ได้ตรงเป๊ะ
   * คิดจากพิกเซลจริง (ไม่ใช่สัดส่วน 0..1) เผื่อรูปแมพไม่จัตุรัส */
  function faceSpawn() {
    if (!facing || !facing.own || !facing.enemy) { view.rot = 0; return; }
    const dx = (facing.enemy[0] - facing.own[0]) * size.w;
    const dy = (facing.enemy[1] - facing.own[1]) * size.h;
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;       // ทิศจากฝั่งเราไปฝั่งเขาบนรูปตอนนี้
    const turn = Math.round((-90 - angle) / 90) * 90;          // -90° = ชี้ขึ้นบนจอ
    view.rot = ((turn % 360) + 360) % 360;
  }

  function fit() {
    const box = stage.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const rotated = rotatedBox();
    view.scale = Math.min(box.width / rotated.w, box.height / rotated.h) * 0.98;
    // จัดกึ่งกลาง — ยึดจุดกึ่งกลางรูป (ซึ่งเป็นจุดหมุนด้วย) ให้อยู่กลางกรอบพอดี
    view.tx = box.width / 2 - view.scale * size.w / 2;
    view.ty = box.height / 2 - view.scale * size.h / 2;
    apply();
  }

  /** ซูมโดยยึดจุดที่เมาส์ชี้ไว้กับที่ — ไม่งั้นสิ่งที่อยากดูจะเลื่อนหลุดกรอบทุกครั้งที่ซูม */
  function zoomAt(factor, stageX, stageY) {
    const next = Math.min(Math.max(view.scale * factor, 0.05), 40);
    if (next === view.scale) return;
    // จุดเดิมต้องอยู่ที่เดิม: t' = q - (s'/s)(q - t)  — ไม่ต้องยุ่งกับมุมหมุนเลย
    const ratio = next / view.scale;
    view.tx = stageX - ratio * (stageX - view.tx);
    view.ty = stageY - ratio * (stageY - view.ty);
    view.scale = next;
    apply();
  }

  /* ---------- วาดหมุด/ป้าย ---------- */
  function draw() {
    for (const node of [...layer.children]) {
      if (node !== image) node.remove();
    }
    if (!mapName) return;

    const unit = Math.max(size.w, size.h) / 1000;
    const at = (xy) => [xy[0] * size.w, xy[1] * size.h];
    // ตัวอักษรต้องหมุนกลับทางเสมอ ไม่งั้นพอหมุนแมพแล้วอ่านไม่ออก (กลับหัวตอน 180°)
    const upright = (x, y) => `rotate(${-view.rot} ${x} ${y})`;

    for (const callout of data.callouts) {
      const [x, y] = at(callout.xy);
      layer.append(el("circle", { cx: x, cy: y, r: 3 * unit, fill: "#7a8496", opacity: .55 }));
      const text = el("text", {
        x: x + 7 * unit, y: y + 4 * unit, "font-size": 11 * unit,
        fill: "#7a8496", opacity: .8, transform: upright(x, y),
      });
      text.textContent = callout.label;
      layer.append(text);
    }

    for (const [site, info] of Object.entries(data.labels)) {
      const [x, y] = at(info.xy);
      layer.append(el("circle", {
        cx: x, cy: y, r: 15 * unit, fill: "#0b0e14", opacity: info.manual ? .75 : .4,
        stroke: "#7dd3fc", "stroke-width": 2 * unit,
        ...(info.manual ? {} : { "stroke-dasharray": `${4 * unit} ${3 * unit}` }),
      }));
      const text = el("text", {
        x, y: y + 6 * unit, "font-size": 17 * unit, "font-weight": 700,
        fill: "#7dd3fc", "text-anchor": "middle", transform: upright(x, y),
      });
      text.textContent = site.toUpperCase();
      layer.append(text);
    }

    // โซนที่คลิกเลือกเป็นตัวกรองได้ — ตัวเลขในวงคือจำนวนไลน์อัพที่เกี่ยวข้องกับโซนนั้น
    // (วงใหญ่/สว่างกว่า = มีของให้เลือกเยอะกว่า มองออกตั้งแต่ยังไม่คลิก)
    //
    // **ขนาดวง/ตัวหนังสือหารด้วยระดับซูมไว้** ให้ใหญ่เท่าเดิมบนจอเสมอ — ไม่งั้นตอนพอดีจอ
    // (ย่อเหลือ ~35%) วงจะเล็กจนกดไม่โดนและอ่านเลขไม่ออก ส่วนตอนซูมเข้าจะบังแมพจนหมด
    const zoneUnit = Math.min(Math.max(unit / view.scale, unit * 0.4), unit * 8);
    for (const zone of data.zones) {
      const [x, y] = at(zone.xy);
      const role = zone.role || "";
      // zone.tone = สีที่ผู้เรียกกำหนดเอง (หน้า "แผนที่รวม": แดง = โซนที่ยังไม่มีไลน์อัพ) — มีสีเองไม่ทำจาง
      const tone = zone.tone || (role === "from" ? "#4ade80" : role === "to" ? "#ffd479" : "#7dd3fc");
      const weight = Math.min(1, (zone.count || 0) / 40);
      layer.append(el("circle", {
        cx: x, cy: y, r: (9 + 5 * weight) * zoneUnit,
        fill: "#0b0e14", "fill-opacity": role ? .95 : .72,
        stroke: role && zone.tone ? "#ffffff" : tone, "stroke-width": (role ? 3 : 1.6) * zoneUnit,
        opacity: zone.count || zone.tone ? 1 : .3,
      }));
      const count = el("text", {
        x, y: y + 4 * zoneUnit, "font-size": 10 * zoneUnit, "font-weight": 700,
        fill: tone, "text-anchor": "middle", transform: upright(x, y + 4 * zoneUnit),
      });
      count.textContent = String(zone.count || 0);
      layer.append(count);
      const name = el("text", {
        x, y: y + 22 * zoneUnit, "font-size": 9 * zoneUnit,
        fill: role ? tone : "#8b9aa3", "text-anchor": "middle",
        transform: upright(x, y + 22 * zoneUnit),
      });
      name.textContent = zone.label;
      layer.append(name);
      // ป้ายเล็กมุมขวาบนของวง — หน้า "หาไลน์อัพเพิ่ม": เว็บมีให้เก็บกี่ใบในโซนนี้
      if (zone.extra) {
        const bx = x + 13 * zoneUnit, by = y - 12 * zoneUnit;
        layer.append(el("rect", {
          x: bx - 2 * zoneUnit, y: by - 8 * zoneUnit, rx: 4 * zoneUnit,
          width: (String(zone.extra).length * 6 + 10) * zoneUnit, height: 11 * zoneUnit,
          fill: "#c084fc", transform: upright(x, y),
        }));
        const badge = el("text", {
          x: bx, y: by, "font-size": 8.5 * zoneUnit, "font-weight": 700, fill: "#0b0e14",
          transform: upright(x, y),
        });
        badge.textContent = `+${zone.extra}`;
        layer.append(badge);
      }
    }

    // เส้นจางจากจุดยืนไปจุดตกของทุกใบ (หน้า "แผนที่รวม") — วาดก่อนหมุด จะได้อยู่ใต้
    // data.strong = กำลังดูเฉพาะกลุ่มเล็กๆ (เลือกช่องในตาราง) — เส้น/จุดเข้มให้เห็นชัด
    for (const [from, to] of data.lines || []) {
      const [x1, y1] = at(from);
      const [x2, y2] = at(to);
      layer.append(el("line", { x1, y1, x2, y2, stroke: "#ffd479",
                                "stroke-width": (data.strong ? 2.6 : 1.2) * unit, opacity: data.strong ? .95 : .28 }));
      if (data.strong) {
        layer.append(el("circle", { cx: x2, cy: y2, r: 6 * unit, fill: "#ffd479" }));
        layer.append(el("circle", { cx: x1, cy: y1, r: 7 * unit, fill: "#4ade80", stroke: "#0b0e14",
                                    "stroke-width": 1.5 * unit }));
      }
    }

    for (const other of data.pins) {
      const [x, y] = at(other);
      layer.append(el("circle", {
        cx: x, cy: y, r: 7 * unit, fill: "#5b7a9a", opacity: .38,
        stroke: "#5b7a9a", "stroke-width": 2 * unit,
      }));
    }

    const current = data.current || {};
    if (current.from && current.to) {
      const [x1, y1] = at(current.from);
      const [x2, y2] = at(current.to);
      const line = el("line", { x1, y1, x2, y2, stroke: "#ffd479", "stroke-width": 3 * unit });
      // ให้เส้นวิถีค่อยๆ ลากตัวเองออกมา **เฉพาะตอนเปลี่ยนไลน์อัพ** — ไม่ใช่ทุกครั้งที่ซูม/เลื่อน
      // (draw() ถูกเรียกทุกเฟรมตอนลาก ถ้าไม่กันไว้เส้นจะกระพริบรัวทั้งเวลา)
      if (animateNext) {
        line.classList.add("traj");
        line.style.setProperty("--len", Math.hypot(x2 - x1, y2 - y1));
        animateNext = false;
      }
      layer.append(line);
      layer.append(el("circle", { cx: x2, cy: y2, r: 9 * unit, fill: "#ffd479" }));
    }
    const start = data.pending || current.from;
    if (start) {
      const [x, y] = at(start);
      layer.append(el("circle", {
        cx: x, cy: y, r: 11 * unit, fill: "#4ade80", stroke: "#0b0e14", "stroke-width": 2 * unit,
      }));
    }
  }

  /* ---------- เมาส์ ---------- */
  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    // ห้ามให้ setPointerCapture ล้มแล้วทำให้ทั้ง handler หลุด — บาง pointer จับไม่ได้
    // (เช่นปากกา/ทัชที่หลุดไปแล้ว) ถ้าไม่ดักไว้จะกลายเป็นคลิกไม่ติดทั้งอัน
    try { stage.setPointerCapture(event.pointerId); } catch { /* จับไม่ได้ก็ลากได้ตามปกติ */ }
    drag = { x: event.clientX, y: event.clientY, tx: view.tx, ty: view.ty, moved: false };
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;   // ขยับไม่ถึง 5px ยังนับเป็นคลิก ไม่ใช่ลาก
    drag.moved = true;
    view.tx = drag.tx + dx;
    view.ty = drag.ty + dy;
    apply();
  });
  const endDrag = (event) => {
    if (!drag) return;
    const wasDrag = drag.moved;
    drag = null;
    // ลาก = เลื่อนแผนที่ · คลิกเฉยๆ = จิ้มหมุด (แยกด้วยระยะที่เมาส์ขยับ ไม่ต้องมีปุ่มโหมด)
    if (!wasDrag && onPick) {
      const point = normalized(event);
      if (point && point[0] >= 0 && point[0] <= 1 && point[1] >= 0 && point[1] <= 1) {
        onPick(point.map((v) => +v.toFixed(4)));
      }
    }
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", () => { drag = null; });

  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    const box = stage.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.18 : 1 / 1.18, event.clientX - box.left, event.clientY - box.top);
  }, { passive: false });

  stage.addEventListener("dblclick", fit);

  return {
    setMap(name, token) {
      if (name === mapName) return;
      mapName = name;
      if (!name) { image.removeAttribute("href"); return; }
      const probe = new Image();
      probe.onload = () => {
        size = { w: probe.naturalWidth, h: probe.naturalHeight };
        image.setAttribute("width", size.w);
        image.setAttribute("height", size.h);
        image.setAttribute("href", probe.src);
        faceSpawn();     // ขนาดรูปเพิ่งรู้ — คิดมุมใหม่ด้วยขนาดจริง
        fit();
      };
      probe.src = `/api/map?name=${encodeURIComponent(name)}&t=${token}`;
    },
    setData(next) {
      data = { ...data, ...next };
      const traj = JSON.stringify((data.current || {}).from) + JSON.stringify((data.current || {}).to);
      if (traj !== lastTraj) { lastTraj = traj; animateNext = true; }
      draw();
    },
    setRotation(deg) { view.rot = ((+deg % 360) + 360) % 360; fit(); },
    /** หันแมพตามฝั่ง (own/enemy = จุดเกิด [x,y] สัดส่วน 0..1 · ไม่รู้ก็ส่ง null = 0°)
     * หมุนใหม่เฉพาะตอน key (แมพ+ฝั่ง) เปลี่ยน — วาดซ้ำแมพเดิมจะไม่ทับมุมที่ผู้ใช้หมุนเองไว้ */
    faceSide(key, own, enemy) {
      if (facing && facing.key === key) return;
      facing = { key, own, enemy };
      faceSpawn();
      fit();
    },
    resetFacing() { faceSpawn(); fit(); },
    getRotation: () => view.rot,
    zoomBy: (factor) => {
      const box = stage.getBoundingClientRect();
      zoomAt(factor, box.width / 2, box.height / 2);
    },
    zoomPercent: () => view.scale,
    fit,
    onView(fn) { listeners.push(fn); },
  };
}


/* ซูม/เลื่อนรูปธรรมดา (ไม่ใช่แผนที่ ไม่มีหมุด) — ใช้กับรูปไลน์อัพในหน้าจัดการคลัง
 *
 * ทำไมต้องซูมรูปไลน์อัพ: ในสกรีนช็อตมี**มินิแมพเล็กๆ ของเกมติดอยู่มุมจอ** ซึ่งบอกว่าคนยิง
 * ยืนตรงไหน — ต้องขยายดูให้ออกถึงจะจิ้มหมุดบนแผนที่เราตามได้ถูกจุด ย่อพอดีกรอบอย่างเดียว
 * มองไม่เห็นแน่นอน
 *
 * ใช้ CSS transform ล้วน (ไม่แตะ src) รูปจึงไม่ต้องโหลดใหม่ตอนซูม
 */
function createZoomPane(stage, image) {
  const view = { scale: 1, tx: 0, ty: 0 };
  const listeners = [];
  let natural = { w: 0, h: 0 };

  function apply() {
    image.style.transform = `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})`;
    for (const fn of listeners) fn(view);
  }

  function fit() {
    const box = stage.getBoundingClientRect();
    if (!box.width || !box.height || !natural.w || !natural.h) return;
    view.scale = Math.min(box.width / natural.w, box.height / natural.h);
    view.tx = (box.width - natural.w * view.scale) / 2;
    view.ty = (box.height - natural.h * view.scale) / 2;
    apply();
  }

  /** ยึดจุดที่เมาส์ชี้ไว้กับที่ — ไม่งั้นมินิแมพที่กำลังส่องอยู่จะเลื่อนหลุดกรอบทุกครั้งที่ซูม */
  function zoomAt(factor, x, y) {
    const next = Math.min(Math.max(view.scale * factor, 0.05), 30);
    if (next === view.scale) return;
    const ratio = next / view.scale;
    view.tx = x - ratio * (x - view.tx);
    view.ty = y - ratio * (y - view.ty);
    view.scale = next;
    apply();
  }

  image.addEventListener("load", () => {
    natural = { w: image.naturalWidth, h: image.naturalHeight };
    image.style.width = `${natural.w}px`;
    image.style.height = `${natural.h}px`;
    fit();
  });

  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    try { stage.setPointerCapture(event.pointerId); } catch { /* จับไม่ได้ก็ลากได้ตามปกติ */ }
    drag = { x: event.clientX, y: event.clientY, tx: view.tx, ty: view.ty };
    stage.classList.add("grabbing");
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    view.tx = drag.tx + (event.clientX - drag.x);
    view.ty = drag.ty + (event.clientY - drag.y);
    apply();
  });
  const stop = () => { drag = null; stage.classList.remove("grabbing"); };
  stage.addEventListener("pointerup", stop);
  stage.addEventListener("pointercancel", stop);

  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    const box = stage.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.2 : 1 / 1.2, event.clientX - box.left, event.clientY - box.top);
  }, { passive: false });

  stage.addEventListener("dblclick", fit);

  return {
    fit,
    zoomBy(factor) {
      const box = stage.getBoundingClientRect();
      zoomAt(factor, box.width / 2, box.height / 2);
    },
    onView(fn) { listeners.push(fn); },
  };
}

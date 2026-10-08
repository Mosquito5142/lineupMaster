/* bookmarklet "ส่งเข้า LineupMaster" — รันบนหน้า tracker.gg ของผู้ใช้เอง (ไม่ได้ถูกโหลดเป็นสคริปต์ของหน้าเว็บนี้)
 *
 * tracker.gg กันบอตด้วย 403 จึงให้เบราว์เซอร์จริงของผู้ใช้เป็นคนดึงรายการ แล้วส่งต่อให้เซิร์ฟเวอร์หน้าจัดการ
 * ในเครื่อง (tools/web_manage.py · /api/tracker/push) — ไม่มีการเลี่ยงระบบกันบอตใดๆ
 *
 * เซิร์ฟเวอร์เปลี่ยนพอร์ตทุกรอบ (8760-8799) → ยิง ping หาทุกพอร์ตพร้อมกัน เอาตัวที่ตอบรหัสลับถูก
 * __KEY__ / __PORT_FIRST__ / __PORT_LAST__ ถูกแทนตอนสร้างลิงก์ (tracker_bookmarklet ใน web_manage.py)
 * ห้ามมี ``//`` ต่อท้ายบรรทัดโค้ด — ลิงก์ javascript: ต้องไม่พังเมื่อโดนบีบเป็นบรรทัดเดียว
 */
(async () => {
  const KEY = "__KEY__";
  const PORTS = Array.from({ length: __PORT_LAST__ - __PORT_FIRST__ + 1 }, (_, i) => __PORT_FIRST__ + i);
  const API = "https://api.tracker.gg/api/v1/valorant/guides";
  const MAX_PAGES = 40;
  const say = (text) => alert("LineupMaster: " + text);

  /* ตัวละครจาก URL ของหน้านี้ — ไม่เจอก็ถามเอา */
  let agent = new URL(location.href).searchParams.get("agent");
  if (!agent || agent === "all") {
    const found = location.pathname.match(/\/agents?\/([a-z0-9-]+)/i);
    agent = found ? found[1] : "";
  }
  if (!agent || agent === "all") agent = prompt("ส่งไลน์อัพของตัวละครอะไร? (ชื่ออังกฤษ เช่น sova)") || "";
  agent = agent.trim().toLowerCase();
  if (!agent) return;

  /* fetch ไปเครื่องตัวเอง — Chrome รุ่นใหม่ถามสิทธิ์ "เข้าถึงอุปกรณ์ในเครือข่ายภายใน" ครั้งแรก (กดอนุญาต) */
  const local = async (url, init = {}) => {
    try {
      return await fetch(url, { ...init, targetAddressSpace: "loopback" });
    } catch (error) {
      if (!(error instanceof TypeError) || error.message.includes("Failed to fetch")) throw error;
      return fetch(url, init);
    }
  };

  const findServer = async () => {
    const probe = async (port) => {
      const base = `http://127.0.0.1:${port}`;
      const stop = new AbortController();
      const timer = setTimeout(() => stop.abort(), 2500);
      try {
        const reply = await local(`${base}/api/tracker/ping?k=${encodeURIComponent(KEY)}`, { signal: stop.signal });
        if (!reply.ok) throw new Error("not ours");
        return base;
      } finally {
        clearTimeout(timer);
      }
    };
    try {
      return await Promise.any(PORTS.map(probe));
    } catch {
      return null;
    }
  };

  const base = await findServer();
  if (!base) {
    say("หาหน้าจัดการคลังไม่เจอ — เปิดหน้าจัดการคลัง (เว็บ) ของ LineupMaster ค้างไว้ก่อน\n" +
        "และถ้าเบราว์เซอร์ถามสิทธิ์เข้าถึงเครือข่ายภายใน/localhost ให้กดอนุญาต\n" +
        "(ถ้าเพิ่งติดตั้งโปรแกรมใหม่ ลองลากลิงก์จากหน้าตั้งค่ามาทับ bookmarklet เดิม)");
    return;
  }

  const rows = (json) => {
    if (Array.isArray(json)) return json;
    const data = json && json.data;
    if (Array.isArray(data)) return data;
    const inner = data && (data.guides || data.items || data.results);
    return Array.isArray(inner) ? inner : (json && (json.guides || json.items)) || [];
  };

  /* ดึงทุกหน้าของตัวละครนี้ (~500 ใบต่อหน้า) — หยุดเมื่อหน้าว่างหรือไม่มีใบใหม่ */
  const items = [];
  const seen = new Set();
  try {
    for (let page = 1; page <= MAX_PAGES; page++) {
      const url = `${API}?agent=${encodeURIComponent(agent)}&map=all&objective=all&sort=ranking&date=all` +
        (page > 1 ? `&page=${page}` : "");
      const reply = await fetch(url);
      if (!reply.ok) throw new Error(`tracker.gg ตอบ ${reply.status}`);
      const fresh = rows(await reply.json()).filter((row) => row && row.id != null && !seen.has(row.id));
      if (!fresh.length) break;
      for (const row of fresh) { seen.add(row.id); items.push(row); }
    }
  } catch (error) {
    say(`ดึงรายการจาก tracker.gg ไม่สำเร็จ: ${error.message}`);
    return;
  }
  if (!items.length) {
    say(`ไม่เจอไลน์อัพของ "${agent}" — เช็คชื่อตัวละครในลิงก์ของหน้านี้`);
    return;
  }

  try {
    /* text/plain = ไม่ต้อง preflight ของ CORS (เซิร์ฟเวอร์อ่านเป็น JSON เอง) */
    const reply = await local(`${base}/api/tracker/push?k=${encodeURIComponent(KEY)}`, {
      method: "POST", headers: { "Content-Type": "text/plain" },
      body: JSON.stringify({ agent, items }),
    });
    const result = await reply.json();
    if (!reply.ok) throw new Error(result.error || reply.status);
    say(`ส่งแล้ว ${result.count} ใบของ ${result.agent} — กลับไปหน้า LineupMaster แท็บ "หาไลน์อัพจากเว็บ" รายการจะอัปเดตเอง`);
  } catch (error) {
    say(`ส่งเข้า LineupMaster ไม่สำเร็จ: ${error.message}`);
  }
})();

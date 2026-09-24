/* ช่อง "สกิล" แคบตามตัวละคร — ฟังก์ชันล้วน ไม่แตะ DOM จะได้ทดสอบด้วย node ได้
 * (tests/web/scope.test.js) · ในเบราว์เซอร์กลายเป็นฟังก์ชัน global ให้ app.js/source.js เรียก
 */

/** ตัวเลือกช่องสกิลของแท็บ "หาไลน์อัพใหม่" จากแคตตาล็อกของเว็บ
 *
 * แคตตาล็อกมีชื่อสกิลของทุกตัวรวมกัน 87 ชื่อ เลือกไซเฟอร์แล้วยังเห็น Recon Bolt/Snake Bite
 * ปนเต็มไปหมด · ชื่อสกิลของเว็บไม่ซ้ำข้ามตัวละคร (วัดจากข้อมูลจริงแล้ว) จึงดูจากแคตตาล็อก
 * เองได้เลย ไม่ต้องพึ่ง AGENT_ABILITIES ที่เก็บแท็กของเรา (cage) ไม่ใช่ชื่อของเว็บ (Cyber Cage)
 *
 * agent ว่าง = ทุกตัว: จัดกลุ่มตามตัวละครและบอกในป้ายว่าเป็นของใคร จะได้ไม่งงว่าชื่อไหนของตัวไหน
 *
 * ถ้าแคตตาล็อกอัปเดตแล้วมีสองตัวละครใช้ชื่อสกิลซ้ำกันขึ้นมา (ผิดจากที่วัดไว้ตอนนี้): โหมดระบุตัว
 * ยังถูกต้องอยู่ (กรองตาม a ก่อนแล้วค่อยนับ) การกรองในหน้าเว็บก็ยังถูก มีแค่ป้ายตอน agent ว่าง
 * ("ทั้งหมด") ที่จะเพี้ยน — เครดิตให้ตัวละครแรกที่เจอในแคตตาล็อกและรวมจำนวนของทั้งคู่เป็นก้อนเดียว
 */
function sourceAbilityChoices(catalog, agent, agentName = (id) => id) {
  const tally = new Map();   // ชื่อสกิล -> { who, n }
  for (const l of catalog) {
    if (!l.ab || (agent && l.a !== agent)) continue;
    const hit = tally.get(l.ab);
    if (hit) hit.n += 1;
    else tally.set(l.ab, { who: l.a, n: 1 });
  }
  return [...tally]
    .sort(([abA, x], [abB, y]) =>
      (agent ? 0 : x.who.localeCompare(y.who)) || y.n - x.n || abA.localeCompare(abB))
    .map(([ab, { who, n }]) =>
      [ab, agent ? `${ab} (${n})` : `${ab} · ${agentName(who)} (${n})`]);
}

/** ค่าที่เลือกไว้เดิมยังอยู่ในตัวเลือกใหม่ไหม — อยู่ = คงไว้, ไม่อยู่ = "" (ทั้งหมด)
 *
 * กันค้างค่าที่มองไม่เห็นในช่อง: เปลี่ยนตัวละครแล้วสกิลเดิมเป็นของตัวอื่น ถ้าไม่ล้าง รายการจะ
 * ว่างเปล่าโดยที่ช่องสกิลดูเหมือนไม่ได้กรองอะไรอยู่
 */
function keptValue(choices, value) {
  return value && choices.some(([id]) => id === value) ? value : "";
}

if (typeof module !== "undefined") module.exports = { sourceAbilityChoices, keptValue };

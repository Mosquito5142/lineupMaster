/* เมนูซ้าย — ปุ่ม .tab (คลัง/คอมมูนิตี้/นำเข้า/ตั้งค่า) สลับหน้าด้วยตัวสลับแท็บเดิมใน source.js
 * ส่วน "ต้องแก้" กับ "ยังไม่ปักหมุด" คือหน้าคลังที่กรองไว้แล้ว — ไฮไลต์เมนูให้ตรงกับที่ดูอยู่
 */

(() => {
  const libTab = document.querySelector('.tab[data-tab="library"]');
  const flagItem = $("side-flag");
  const pinItem = $("btn-unpinned");

  let viaShortcut = false;     // มาจากเมนูต้องแก้/ยังไม่ปักหมุด — อย่าล้างตัวกรองที่เพิ่งเปิด
  function showLibrary() {
    if ($("tab-library").hidden) {
      viaShortcut = true;
      libTab.click();
      viaShortcut = false;
    }
  }

  /** ไฮไลต์เมนูตามตัวกรองที่เปิดอยู่ — ต้องแก้/ยังไม่ปักหมุด ชนะ "คลังของฉัน" */
  function syncSide() {
    const onLibrary = !$("tab-library").hidden;
    const flag = $("f-flag").classList.contains("on");
    const pin = pinItem.classList.contains("on");
    flagItem.classList.toggle("on", onLibrary && flag);
    pinItem.classList.toggle("on", onLibrary && pin && !flag);
    libTab.classList.toggle("on", onLibrary && !flag && !pin);
  }

  flagItem.addEventListener("click", () => {
    showLibrary();
    if (pinItem.classList.contains("on")) pinItem.click();
    if (!$("f-flag").classList.contains("on")) $("f-flag").click();
    syncSide();
  });
  // ปุ่ม "ยังไม่ปักหมุด" ตัวกรองจริงอยู่ใน app.js (สลับ .on แล้ว render) — ตรงนี้แค่พามาหน้าคลัง
  pinItem.addEventListener("click", () => {
    showLibrary();
    if ($("f-flag").classList.contains("on")) $("f-flag").click();
    syncSide();
  });
  libTab.addEventListener("click", () => {
    if (viaShortcut) return;
    // กด "คลังของฉัน" ตรงๆ = ดูทั้งคลัง (ปิดตัวกรองทางลัดทั้งสอง)
    setTimeout(() => {
      if ($("f-flag").classList.contains("on")) $("f-flag").click();
      if (pinItem.classList.contains("on")) pinItem.click();
      syncSide();
    });
  });
  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => setTimeout(syncSide));
  $("f-flag").addEventListener("click", () => setTimeout(syncSide));
  $("f-reset").addEventListener("click", () => setTimeout(syncSide));
  window.syncSide = syncSide;
})();

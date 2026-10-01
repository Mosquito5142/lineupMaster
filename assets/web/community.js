/* แท็บ "คอมมูนิตี้" — ดู/เอาไลน์อัพของเพื่อนเข้าคลัง · กดคะแนน ✓ใช้ได้จริง / ✗ใช้ไม่ได้ · แชร์ของเราขึ้นไป
 *
 * ทุกอย่างผ่าน /api/community/* (tools/community_web.py) ซึ่งคุยกับ Supabase ต่ออีกที
 * สามหน้าจอตามสถานะ: ยังไม่ตั้งเซิร์ฟเวอร์ → ยังไม่ล็อกอิน → ใช้งาน
 */

const COM = { state: null, items: [], loaded: false };

async function comApi(path, body) {
  const url = `/api/community/${path}${path.includes("?") ? "&" : "?"}t=${encodeURIComponent(TOKEN)}`;
  const response = await fetch(url, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {});
  const data = await response.json().catch(() => ({ error: "อ่านคำตอบจากเซิร์ฟเวอร์ไม่ได้" }));
  if (response.status === 401) {           // หมดเวลาล็อกอิน — กลับไปหน้าล็อกอิน
    COM.state = { ...(COM.state || {}), user: null };
    showComScreen();
  }
  if (!response.ok) throw new Error(data.error || `ผิดพลาด ${response.status}`);
  return data;
}

function showComScreen() {
  const s = COM.state || {};
  $("com-setup").hidden = !!s.configured;
  $("com-login").hidden = !s.configured || !!s.user;
  $("com-main").hidden = !s.configured || !s.user;
  if (s.user) $("c-user").textContent = `ล็อกอินเป็น ${s.user.name}`;
}

async function openCommunity() {
  try {
    COM.state = await comApi("state");
  } catch (error) { say(error.message, "err"); return; }
  showComScreen();
  if (!COM.state.user) return;
  if (!COM.loaded && STATE) {
    const agents = STATE.agents.map((a) => [a.id, a.th]);
    fill($("c-agent"), agents, { blank: ALL, value: $("f-agent").value || "" });
    fill($("c-map"), STATE.maps.map((m) => [m, m]), { blank: ALL });
    COM.loaded = true;
  }
  await loadFeed();
}

async function loadFeed() {
  $("c-count").textContent = "กำลังโหลด…";
  try {
    const query = new URLSearchParams({ agent: $("c-agent").value, map: $("c-map").value });
    const data = await comApi(`feed?${query}`);
    COM.items = data.items;
    renderFeed();
  } catch (error) { $("c-count").textContent = ""; say(error.message, "err"); }
}

const comAgentTh = (id) => (STATE?.agents.find((a) => a.id === id) || {}).th || id;
const comAbilityTh = (id) => (STATE?.abilities.find((a) => a.id === id) || {}).th || id || "";

function renderFeed() {
  const grid = $("c-grid");
  grid.innerHTML = "";
  const shown = COM.items.filter((it) => !($("c-hide-have").checked && it.have));
  for (const it of shown) {
    const card = document.createElement("article");
    card.className = "card com-card";
    const side = SIDE_TH[it.side] || it.side;
    card.innerHTML = `
      <img loading="lazy" src="${escapeHtml(it.image_url)}" alt="">
      <div class="meta">
        <div class="name">${escapeHtml(it.title)}</div>
        <div class="slots">
          <span>${escapeHtml(comAgentTh(it.agent))}</span><span>${escapeHtml(it.map)}</span>
          <span>${escapeHtml(side)} ${escapeHtml((it.site || "").toUpperCase())}</span>
          <span class="abil">${escapeHtml(comAbilityTh(it.ability))}</span>
        </div>
        <div class="com-row">
          <span class="com-score" title="คนที่บอกว่าใช้ได้จริง / ใช้ไม่ได้">✓${it.works} ✗${it.broken}</span>
          <span class="hint">โดย ${escapeHtml(it.own ? "เรา" : it.owner_name || "?")}</span>
        </div>
        <div class="com-row">
          <button type="button" class="chip vote-up${it.mine === 1 ? " on" : ""}" title="ใช้ได้จริง (กดซ้ำ = ถอน)">✓ ใช้ได้</button>
          <button type="button" class="chip vote-down${it.mine === -1 ? " on bad" : ""}" title="ใช้ไม่ได้ (กดซ้ำ = ถอน)">✗ ใช้ไม่ได้</button>
          <span class="spacer"></span>
          ${it.have
            ? '<span class="hint">มีในคลังแล้ว</span>'
            : '<button type="button" class="primary take">เอาเข้าคลัง</button>'}
        </div>
      </div>`;
    card.querySelector("img").addEventListener("click", () => openComDetail(it));
    card.querySelector("img").style.cursor = "zoom-in";
    card.querySelector(".vote-up").addEventListener("click", () => comVote(it, it.mine === 1 ? 0 : 1));
    card.querySelector(".vote-down").addEventListener("click", () => comVote(it, it.mine === -1 ? 0 : -1));
    const take = card.querySelector(".take");
    if (take) take.addEventListener("click", () => comTake(it, take));
    grid.append(card);
  }
  $("c-empty").hidden = shown.length > 0;
  $("c-count").textContent = `${shown.length} ใบ`;
}

/* ---------- รายละเอียดใบ (M9): รูปใหญ่ + แผนที่หมุดยืน/ตก + คะแนน + เอาเข้าคลัง ---------- */
let cdMap = null;
let cdItem = null;
function openComDetail(it) {
  cdItem = it;
  $("cd-title").textContent = it.title;
  $("cd-meta").textContent = [comAgentTh(it.agent), it.map, SIDE_TH[it.side] || it.side,
    (it.site || "").toUpperCase(), comAbilityTh(it.ability)].filter(Boolean).join(" · ");
  $("cd-img").src = it.image_url;
  $("cd-note").textContent = it.note || "";
  $("cd-score").textContent = `✓ ${it.works}   ✗ ${it.broken}`;
  $("cd-owner").textContent = `แชร์โดย ${it.own ? "เรา" : it.owner_name || "?"}`;
  $("cd-up").classList.toggle("on", it.mine === 1);
  $("cd-down").classList.toggle("on", it.mine === -1);
  $("cd-take").hidden = !!it.have;
  $("com-detail").showModal();
  if (!cdMap) cdMap = createMapView($("cd-map"));
  cdMap.setMap(it.map, TOKEN);
  const from = it.stand_x != null ? [it.stand_x, it.stand_y] : null;
  const to = it.target_x != null ? [it.target_x, it.target_y] : null;
  cdMap.setData({ pins: [], labels: {}, callouts: [], current: from ? { from, to } : null, pending: null });
}

async function comVote(it, value) {
  try {
    await comApi("vote", { id: it.id, value });
    await loadFeed();
  } catch (error) { say(error.message, "err"); }
}

async function comTake(it, button) {
  button.disabled = true;
  try {
    const result = await comApi("take", { id: it.id });
    say(result.message);
    await load();                  // คลังของเราเปลี่ยน — วาดแท็บคลังใหม่
    await loadFeed();
  } catch (error) { button.disabled = false; say(error.message, "err"); }
}

/** แชร์จากแท็บคลัง — ส่งหลายใบได้ ใบที่แชร์ไม่ได้บอกเหตุผลทีละใบ */
async function comShare(rels) {
  if (!rels.length) return;
  if (!(await uiConfirm("รูป หมุด ชื่อ และโน้ตจะขึ้นไปบนเซิร์ฟเวอร์ให้เพื่อนเห็น\n" +
                        "ใบที่ดึงมาจากเว็บอื่นจะถูกข้าม เพราะไม่ใช่รูปของเรา",
                        { title: `แชร์ ${rels.length} ใบขึ้นคอมมูนิตี้?`, ok: "แชร์" }))) return;
  try {
    const result = await comApi("share", { rels });
    const lines = result.skipped.map((s) => `• ${s.rel.split("/").pop()}: ${s.why}`);
    say(`แชร์แล้ว ${result.shared.length} ใบ` + (lines.length ? ` · ข้าม ${lines.length} ใบ` : ""),
        result.shared.length ? "ok" : "err");
    if (lines.length) await uiAlert(lines.join("\n"), { title: `ข้าม ${lines.length} ใบ` });
    await load();
  } catch (error) { say(error.message, "err"); }
}

function wireCommunity() {
  document.querySelector('.tab[data-tab="community"]').addEventListener("click", openCommunity);
  $("com-save").addEventListener("click", async () => {
    try {
      COM.state = await comApi("config", { url: $("com-url").value, anon_key: $("com-key").value });
      showComScreen();
      say("บันทึกแล้ว — ล็อกอินต่อได้เลย");
    } catch (error) { say(error.message, "err"); }
  });
  $("com-login-btn").addEventListener("click", async () => {
    try {
      location.href = (await comApi("login", {})).url;     // Discord ยืนยันแล้วเด้งกลับมาหน้านี้เอง
    } catch (error) { say(error.message, "err"); }
  });
  $("c-logout").addEventListener("click", async () => {
    COM.state = await comApi("logout", {});
    showComScreen();
  });
  for (const id of ["c-agent", "c-map"]) $(id).addEventListener("change", loadFeed);
  $("c-hide-have").addEventListener("change", renderFeed);
  $("c-reload").addEventListener("click", loadFeed);
  $("cd-close").addEventListener("click", () => $("com-detail").close());
  $("cd-up").addEventListener("click", async () => { await comVote(cdItem, cdItem.mine === 1 ? 0 : 1); $("com-detail").close(); });
  $("cd-down").addEventListener("click", async () => { await comVote(cdItem, cdItem.mine === -1 ? 0 : -1); $("com-detail").close(); });
  $("cd-take").addEventListener("click", async () => { await comTake(cdItem, $("cd-take")); $("com-detail").close(); });
  $("btn-share").addEventListener("click", () => current && comShare([current]));
  $("bulk-share").addEventListener("click", () => comShare([...picked]));

  // ลิงก์ตรงเข้าหน้าไหนก็ได้ — หน้าเข้าโปรแกรม (launcher) เปิดมาพร้อม #community / #flag / ...
  // และหลังล็อกอิน Discord (/community/callback เด้งกลับมาที่ #community)
  routeHash();
  window.addEventListener("hashchange", routeHash);
}

function routeHash() {
  const target = location.hash.slice(1);
  if (!target) return;
  history.replaceState(null, "", location.pathname + location.search);
  const waitState = setInterval(() => {
    if (!STATE) return;
    clearInterval(waitState);
    // ต้องแก้/ยังไม่ปักหมุด ไปผ่านเมนูซ้าย (shell.js) ตรงๆ — ห้ามกด "คลังของฉัน" ก่อน เพราะมันล้างตัวกรองทิ้ง
    if (target === "flag") {
      if (!$("side-flag").classList.contains("on")) $("side-flag").click();
      return;
    }
    // #lineup=<rel> — หน้าต่อรูปกด "บันทึกแล้วไปปักหมุด": ล้างตัวกรองให้เห็นใบนี้แน่ๆ แล้วเลือกเลย
    if (target.startsWith("lineup=")) {
      const rel = decodeURIComponent(target.slice(7));
      document.querySelector('.tab[data-tab="library"]').click();
      $("f-reset").click();
      const open = () => {
        select(rel);
        // รอให้ตารางจัดหน้าเสร็จก่อน (แท็บเพิ่งโผล่ + รูปย่อยังโหลด) ไม่งั้นเลื่อนไปผิดที่
        setTimeout(() => document.querySelector(`.card[data-rel="${CSS.escape(rel)}"]`)
          ?.scrollIntoView({ block: "center" }), 400);
      };
      if (STATE.lineups.some((lu) => lu.rel === rel)) open();
      else load(rel).then(open);          // หน้าเปิดค้างไว้ก่อนบันทึก — ยังไม่รู้จักใบนี้
      return;
    }
    if (target === "unpinned") {
      if (!$("btn-unpinned").classList.contains("on")) $("btn-unpinned").click();
      return;
    }
    const tab = ["community", "settings", "source"].includes(target) ? target : "library";
    document.querySelector(`.tab[data-tab="${tab}"]`).click();
    // เบราว์เซอร์ไม่ยอมเปิดหน้าต่างเลือกไฟล์ให้เองถ้าผู้ใช้ไม่ได้กด — บอกวิธีแทน
    if (target === "add") say("กด “เพิ่มไลน์อัพ” มุมขวาบน หรือ Ctrl+V วางรูปจากคลิปบอร์ด");
  }, 100);
}

wireCommunity();

# ตรวจไลน์อัพตัวละครใหม่ทีละรูป — คู่มือสำหรับ Claude

> ผู้ใช้จะบอกแค่ **ตัวละคร + แมพ** เช่น "ทำ viper แมพ ascent, bind" → อ่านไฟล์นี้แล้วทำตามทีละขั้นจนจบ
> ไม่ต้องถามซ้ำเรื่องที่ไฟล์นี้ตอบไว้แล้ว · เคยทำจริงกับ KAY/O 241 ใบ (2026-09-25) ได้ผลดี

## เป้าหมาย
ผู้ใช้โหลดไลน์อัพของตัวละครนั้นมาจากหน้า **"หาไลน์อัพจากเว็บ"** ทั้งกองโดยไม่ได้คัด ให้ Claude **ดูรูปทุกใบด้วยตาจริง** แล้ว:
- ปักหมุดจุดยืน + จุดตกให้ตรงกับรูป (ไม่ใช่กลางโซน)
- ตั้งชื่อไฟล์ให้สื่อ: `<ยืน> → <จุดตก> (<สกิลไทย>)`
- ย้ายโฟลเดอร์ที่ผิดฝั่ง/ผิดไซต์
- ตัดใบซ้ำ/ใบเสีย
- แท็กสกิล

จากนั้นสรุปรายใบให้ผู้ใช้ดู

## กติกาเหล็ก
- **ข้อมูลจริงอยู่ที่ `dist/LineupMaster/data/`** (ตั้งแต่ 2026-09-26 ข้อมูลย้ายเข้า data/ ข้าง exe เหลือแค่ตัวโปรแกรม) ไม่ใช่รากโปรเจกต์ · `--root dist/LineupMaster/data` เสมอ
- **ไม่แตะตัวละครอื่น** โดยเฉพาะโซวา ผู้ใช้ทำรูปเองดีอยู่แล้ว · ใบที่ผู้ใช้วางเข้าคลังเอง (ไม่ได้มาจากเว็บ) เครื่องมือข้ามให้เอง
- **ห้ามลบถาวร:** ตัดใบ = ย้ายเข้า `.trash` เท่านั้น ถ้าผู้ใช้อยากล้างถัง ให้บอกวิธีให้เขาลบเอง
- **Python บนเครื่องนี้:** `.venv\Scripts\python.exe` ใช้ไม่ได้ (ชี้ไปเครื่องอื่น) และ**ห้ามแก้ `.venv/pyvenv.cfg`** ให้ใช้

  ```
  PYTHONPATH=".venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 <script>
  ```

- **ก่อนแก้จริง `LineupMaster.exe` ต้องปิดอยู่** (`tasklist | grep -i lineupmaster`) ถ้าเปิดอยู่ให้บอกผู้ใช้ปิด ห้าม kill เอง
- `browser.py`, `app.py`, `README.md`, `config.yaml` มีงานเก่าที่ยังไม่ commit ค้าง ผู้ใช้ไม่ได้ใช้ git แล้ว **ไม่ต้อง commit ก็ได้**

## ขั้น 0 — เช็คว่าพร้อม
1. ผู้ใช้โหลดรูปมาแล้วหรือยัง: ดูว่ามีโฟลเดอร์ `dist/LineupMaster/data/lineups/<แมพ>/*/<agent>/` หรือเปล่า
   - ยังไม่มี = บอกผู้ใช้ไปโหลดเองในหน้า "หาไลน์อัพจากเว็บ" (เลือกตัวละคร + แมพ → เอามาทีละใบ/ทั้งหน้า)
   - Claude โหลดแทนไม่ได้ เพราะหน้าเว็บต้องต่อรูปหลายขั้นเป็นใบเดียวในเบราว์เซอร์
   - ชื่อโฟลเดอร์ตัวละครเป็นตัวเล็กตามเว็บ: `kayo`, `viper`, `killjoy` …
2. รันขั้น 1 ดูก่อน ถ้าขึ้น `!! สกิลที่ยังไม่มีแท็ก: [...]` ให้เพิ่มแท็กก่อน (ทำแบบเดียวกับที่เพิ่ม KAY/O):
   - `tools/lineup_sources.py` → `ABILITY_WORDS`: คำในชื่อสกิลของเว็บ → แท็ก เช่น `("zero", "knife")`
   - `src/lineupmaster/browser.py` → `ABILITY_TH` (แท็ก → ชื่อไทย) และ `AGENT_ABILITIES["<agent>"]`
   - แก้ `browser.py` แล้วต้องบิ้ว exe ใหม่ตอนจบ (`tools/build_exe.py`) ตัวกรองสกิลในเกมถึงจะรู้จัก

## ขั้น 1 — เตรียม
```
PYTHONPATH=".venv/Lib/site-packages" C:/Users/PC/AppData/Local/Programs/Python/Python312/python.exe -X utf8 tools/review_prepare.py --root dist/LineupMaster/data --agent <agent> --maps <แมพ1,แมพ2>
```
- ได้โฟลเดอร์ `dist/LineupMaster/data/.cache/<agent>-review/`
  - `input-<แมพ>-<ฝั่ง>[-n].json` ชุดละ ≤22 ใบ
  - `map-<แมพ>.png` แผนที่อ้างอิงมีเส้นตาราง + ชื่อโซน
  - `BRIEF.md` คู่มือสำหรับผู้ดูรูป
- ข้ามใบที่เคยตรวจแล้วเอง (`done.json`) · `--maps` ว่าง = ทุกแมพที่มีรูปของตัวนั้น
- ดู `map-<แมพ>.png` สักใบว่าตัวหนังสือชัด (ไม่ใช่กล่อง □)

## ขั้น 2 — ดูรูป (subagent อ่านรูปได้ · ครั้งละไม่เกิน 4 ตัวพร้อมกัน)
- ต่อ **แมพ×ฝั่ง** ให้ subagent หนึ่งตัว (ถ้าฝั่งเดียวแตกเป็น `-1`/`-2` ให้ตัวเดียวทำทั้งคู่ จะได้เทียบใบซ้ำได้ครบ)
- ใช้ `model: sonnet` · `run_in_background: true`
- **นำร่องก่อน:** ปล่อยแมพ/ฝั่งที่เล็กที่สุดชุดเดียว → ตรวจเองตามขั้น 3 → ถ้าผ่านค่อยปล่อยที่เหลือ

ข้อความสั่ง subagent (แทน `<...>`):

```
You are reviewing VALORANT <agent> lineup screenshots one by one with your own eyes (use the Read tool to open every image).
Working folder: C:/Users/PC/Desktop/CODE/lineupMaster/dist/LineupMaster/data/.cache/<agent>-review/
1. Read BRIEF.md there first — it is your full instructions (output format, rules, coordinate self-check section).
2. Do chunk(s) `input-<map>-<side>[-n].json` and write the matching `out-<map>-<side>[-n].json` (one entry per input image, in the out file matching its input chunk). If there are several chunks of the same map+side, judge duplicates across all of them together.
3. Reference map: `map-<map>.png` — all coordinates must be on that image.
Rules: open EVERY image, never guess from filenames; the in-game minimap may be rotated vs the reference map; check every coordinate against the reference map (walkable area; site landings inside the site's olive box); `web_ability` is authoritative — only call two lineups duplicates if their web abilities match; do not modify/move/delete any file except writing the out files.
Reply in under 8 lines: kept/dropped counts, notable uncertainties, output path(s).
```

## ขั้น 3 — ตรวจผล (Claude ทำเอง ห้ามข้าม)
- **สุ่มเปิดรูปเทียบ 2–3 ใบต่อชุดแรก** โดยเฉพาะใบที่ตกในไซต์ ว่า `target_xy` อยู่ในกรอบไซต์ฝั่งที่ถูก (เคยเจอ: มินิแมพหมุนแล้วแปลงกลับด้าน)
  - ผิดให้ `SendMessage` กลับไปหา subagent ตัวเดิม บอกจุดที่ผิดพร้อมพิกัดที่ถูก แล้วให้ไล่ตรวจทั้งชุดใหม่
  - ถ้ากติกาควรเพิ่ม ให้แก้ `tools/review_brief.md` ด้วย (รอบหน้าจะได้ไม่พลาดซ้ำ)
- ครบทุกชุดแล้วรันแบบทดลอง ตัวนี้**ตรวจความครบให้เองด้วย** (ทุกใบมีผล · พิกัด 0–1 · ใบที่ถูกอ้างว่า "ซ้ำ" ต้องถูกเก็บ):

  ```
  ... tools/apply_review.py --root dist/LineupMaster/data --agent <agent> --dry-run
  ```

  - ไม่ผ่านจะบอกว่าใบไหน · ผ่าน = ได้ตัวเลข เก็บ/ตัด และหน้า `<agent>-review-dryrun.html`
  - สคริปต์ใช้สกิลตามเว็บเสมอ และยกเลิกการตัด "ซ้ำ" ที่สกิลตามเว็บไม่ตรงกันให้เอง
- ถ้าอยากชัวร์ขึ้นอีก ก๊อป `lineups`, `*.json`, `*.yaml`, `.cache/<agent>-review` ไป temp แล้วรันแบบจริงกับ `--root <temp>` ก่อน
  - เทียบ hash ไฟล์ของตัวละครอื่นก่อน/หลังว่าไม่เปลี่ยน

## ขั้น 4 — แก้จริง
```
... tools/apply_review.py --root dist/LineupMaster/data --agent <agent>
```
- สำรอง json เดิมไว้ที่ `.trash/<เวลา>-<agent>-review/_json/` ก่อนแก้
- ย้าย/เปลี่ยนชื่อ/ตัดผ่าน `lineupmaster.library` (หมุด/แท็ก/journal ตามไปเอง)
- ปักหมุด + แท็กสกิล · จดใบที่ตรวจแล้วลง `done.json`
- เช็คหลังแก้: `dist/LineupMaster/LineupMaster.exe --list` นับรูปได้ = เดิม − จำนวนที่ตัด
- ถ้าแก้ `browser.py` ในขั้น 0: บิ้ว exe ใหม่ (`tools/build_exe.py` ต้องปิด exe ก่อน)

## ขั้น 5 — สรุปให้ผู้ใช้
- ส่ง `dist/LineupMaster/data/<agent>-review.html` (`SendUserFile`, display render)
  - รายใบ: รูป · เก็บ/ตัด + เหตุผล · ชื่อเดิม→ใหม่ · ยืน→ตก + ความมั่นใจ
- บอกเป็นภาษาไทยสั้นๆ:
  - จำนวนเก็บ/ตัด
  - จำนวนความมั่นใจจุดตก high/mid/low (low ส่วนใหญ่ = แฟลชที่ไม่เห็นจังหวะแตก)
  - ย้อนกลับได้จาก `.trash` + `_json`
  - ใบไหนหมุดเพี้ยนขยับเองได้ในหน้า "จิ้มหมุดบนแผนที่"

## เครื่องมือที่เกี่ยวข้อง
| ไฟล์ | หน้าที่ |
|---|---|
| `tools/review_prepare.py` | เตรียม input/แผนที่อ้างอิง/BRIEF · ข้ามใบที่ตรวจแล้ว |
| `tools/review_brief.md` | ต้นฉบับคู่มือผู้ดูรูป (เติมชื่อตัว/สกิลให้เอง) — แก้กติกาที่นี่ |
| `tools/apply_review.py` | ตรวจผล + ลงมือ + หน้าสรุป (`--dry-run` ไม่แตะอะไร) |
| `tools/lineup_sources.py` | แคตตาล็อกเว็บ + `ability_tag()` แปลงชื่อสกิลเว็บเป็นแท็ก |
| `src/lineupmaster/library.py` | move/rename/remove ที่ลากหมุด/แท็ก/journal ตาม |

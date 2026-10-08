# tracker.gg เป็นแหล่งไลน์อัพที่สาม

แท็บ "หาไลน์อัพจากเว็บ" มี ValoLineups Pro (`vlp`), ValCompanion (`vc`) และเพิ่ม tracker.gg (`tg`)

## ข้อเท็จจริงของเว็บ (ตรวจในเบราว์เซอร์จริง 2026-10-02)
- รายการ: `https://api.tracker.gg/api/v1/valorant/guides?agent=<agent>&map=all&objective=all&sort=ranking&date=all`
  (`&page=2` ต่อหน้า) ~500 ใบ/หน้า · ตอบ **403 กับทุกอย่างที่ไม่ใช่เบราว์เซอร์** — ไม่พยายามเลี่ยง
- ฟิลด์: `id urlSlug title description videoUrl previewImageUrl score views dateCreated attributes{map agent ability side location}`
- วิดีโอ: `https://customer-9h7e8ahl6hivmjb6.cloudflarestream.com/<videoUrl>/manifest/video.m3u8` (HLS ≤360p, 10-30 วิ)

## โครงสร้าง
1. **bookmarklet** `assets/web/bookmarklet.js` — ผู้ใช้ลากจากหน้าตั้งค่าไปวางแถบบุ๊กมาร์ก กดบนหน้า tracker.gg
   → อ่านตัวละครจาก `?agent=` (ไม่มีก็ถาม) → ดึงทุกหน้า → POST ไป `http://127.0.0.1:<พอร์ต>/api/tracker/push?k=<รหัสลับ>`
   - พอร์ตเปลี่ยนทุกรอบ (8760-8799) → ping ทุกพอร์ตพร้อมกัน `/api/tracker/ping` เอาตัวที่รหัสถูก
   - รหัสลับถาวรสุ่มครั้งแรกเก็บที่ `.cache/tracker/key.txt` ฝังตอนสร้างลิงก์ (`GET /api/tracker/status` ได้ `bookmarklet`)
   - ส่งเป็น `text/plain` เพื่อไม่ต้อง preflight; ตอบ `OPTIONS` + `Access-Control-Allow-Private-Network`/`-Local-Network`
     ให้ Chrome รุ่นที่ถามสิทธิ์เครือข่ายภายใน · CORS เฉพาะ `https://tracker.gg`/`www.tracker.gg`
2. **เซิร์ฟเวอร์** เก็บ (ผ่านตัวกรองฟิลด์) ที่ `.cache/tracker/guides-<ตัวละคร>.json` ทับทั้งชุดของตัวละครนั้น
   แล้วทิ้งแคตตาล็อกในหน่วยความจำ; `lineup_sources._fetch_tg` อ่านไฟล์พวกนี้ (ไม่ต่อเน็ต)
   - รูปแบบกลาง: `uid tg:<id>`, `src tg`, `side` (all → `both: true` ตัวกรองฝั่งนับเข้าทั้งสองฝั่ง),
     `ab` = ชื่อสกิลของเกม (`ability_tag()` แปลงเป็นแท็ก), `st` เดา A/B/C จากชื่อ, `video` = รหัสสตรีม, `thumb` = previewImageUrl, `n = 0`
3. **เปิดเป็นวิดีโอ** คลิกใบ `tg` → หน้าเว็บเรียก `POST /api/video/open {uid}` → `clipgrab.open_stream()` (PyAV อ่าน HLS ตรงๆ
   remux เป็น `proxy.mp4` ใน `.cache/clips/tg-<id>/` เวลานับจาก 0) แล้วใช้หน้าทำวิดีโอเดิม · แมพ/ฝั่ง/สกิล/ชื่อเติมจากใบ
   คำอธิบายของเว็บเข้าช่อง "วิธียิง" · เก็บเข้าคลังผ่าน `source/take` + `plan` เหมือนใบคลิป YouTube (จด `tg:<id>` ว่าเอาแล้ว)
4. หน้าแท็บแหล่งเช็ค `tracker/status` ทุกครั้งที่เปิดแท็บ ถ้ามีรายการใหม่ส่งเข้ามาจะอ่านแคตตาล็อกใหม่เอง (ไม่ยิงเว็บอื่นซ้ำ)

## นอกขอบเขตรอบนี้
- แปลงพิกัด `location` ของ tracker.gg เป็นพิกัดแมพของเรา (เก็บไว้ในฟิลด์ `xy` ของใบแล้ว ผู้ใช้จิ้มหมุดเอง)
- เก็บหลายใบพร้อมกันจากโหมดตาราง (ใบวิดีโอต้องตัดต่อทีละใบ)

## ยังไม่ได้ทดสอบกับของจริง
สภาพแวดล้อมพัฒนาไม่มีเน็ตถึง tracker.gg/Cloudflare และไม่มี PyAV: เทสต์ใช้ข้อมูลสังเคราะห์ + `open_stream` ปลอม
สิ่งที่ต้องลองบนเครื่องผู้ใช้: (ก) รูปทรง JSON ที่ API ตอบ (bookmarklet รับ `data[]`/`data.guides`/อาเรย์ล้วน) และ CSP ของ tracker.gg
ไม่บล็อก `connect-src` ไป 127.0.0.1 (ข) PyAV เปิด `.m3u8` ของ Cloudflare ได้ (ค) Chrome ถามสิทธิ์เครือข่ายภายในแล้วผ่าน

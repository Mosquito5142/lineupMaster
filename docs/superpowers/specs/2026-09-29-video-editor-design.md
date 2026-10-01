# Video editor page for clip lineups (ValoPlant / YouTube)

Date: 2026-09-29 · Status: design approved in chat and waiting for the spec review.

## Goal

Today a timestamped YouTube link, such as one from ValoPlant's share button, pasted into the "หาไลน์อัพจากเว็บ" tab opens the image-sheet screen: a frame strip, a sheet and a GIF bar.

The change: a clip lineup opens a **full video editor page** instead.
- The user trims, speeds up or cuts parts of the clip and saves it as an **animation-only lineup**.
- The page is also the home for future video tools (arrows, text and so on; not in this spec).

## Decisions (from the owner)

- The page lives in the **web manager** (`tools/web_manage.py` + `assets/web/`). The Qt compose tool is unchanged.
- Output is **animation only**: an animated WebP stored as the lineup itself, the same as today's "เก็บแค่ภาพเคลื่อนไหว". No still cover.
- **One chapter per link.** Paste a timestamped link, edit that chapter, save, done. There is no chapter list sidebar.
- Playback uses a **local proxy mp4** of the chapter, not an embedded YouTube player. This gives frame stepping and an exact preview, with no ads and no embed restrictions.
- Speed and cut: the system first speeds up still parts automatically, then the user can adjust or add their own.
- Lineups from the image sites (ValoLineups Pro, ValCompanion) keep the existing image-sheet screen.

## 1. Page and flow

Layout:
- Left: a large `<video>` player and, under it, the controls.
  - Play/pause, previous/next frame, current time and total length.
  - A timeline with a motion graph and the kept range handles. Speed and cut parts are drawn on it.
  - Buttons: ✨ หาช่วงให้ · ตั้งจุดเริ่ม (I) · ตั้งจุดจบ (O) · ×2 · ×4 · ตัดข้าม · ล้าง · 👁 ดูตัวอย่าง.
- Right: the same fields the source tab has (name, map, agent, side, site, ability, วิธียิง) and the existing mini map pin pane, including autopin from the name.
  - Below them: the output length, a warning when it is over the limit, and 💾 บันทึกเข้าคลัง.

Flow:
1. Paste the link. The page opens with "กำลังโหลดคลิป…" (about 2–5 s).
2. The suggested plan is applied automatically: the throw range, with still runs over 1 s inside it set to ×4. If it looks right, the user saves straight away.
3. Adjust:
   - Drag the range handles, or press I/O at the current frame.
   - Drag to select a part of the timeline, then press ×2, ×4 or ตัดข้าม. Clicking a part and pressing ล้าง removes it.
4. 👁 ดูตัวอย่าง plays the plan exactly: `playbackRate` per part, and cut parts are jumped over.
5. Save:
   - Render the file.
   - Add it to the library with its pins and ability tag.
   - Record the link as taken.
   - Return to the source tab.

Keys: Space play/pause · ←/→ one frame · Shift+←/→ one second · I / O set start/end.

Length rule:
- The output length after speed and cuts must be between **0.3 s and `GIF_MAX` (10 s)**. The source range may be longer.
- Out of range: the save button turns red and says by how much.

## 2. Backend

### 2.1 Opening a clip: `clipgrab.open_video(link, root, aliases) -> Clip`

Reuses:
- `parse_link`, `_fetch_info`, `segment`, and the side/site/map/agent guesses.
- The existing cache folder `.cache/clips/<vid>-<start>/` and `clip.json`.

New work:
- **Proxy.**
  - Stream-copy (no re-encode) the chapter's video-only 720p avc stream into `proxy.mp4`.
  - Source: `_RangeReader`, including its 403 refresh.
  - The copy starts at the keyframe before the chapter start. Store that time as `proxy_offset` in `clip.json`: clip time = proxy time + offset.
  - Write to `proxy.mp4.part`, then rename.
- **Motion.**
  - Decode the local proxy at 10 fps and compute frame differences, the same measure `pick_throw` uses.
  - Store them as `motion_times` and `motion` in `clip.json`.
  - The page draws them as the motion graph; `suggest_plan` uses them.
- No audio.
- The existing `load()` (thumbnail frames, used by the compose tool) is unchanged.

### 2.2 Plan

The plan is a plain dict in clip seconds:

```json
{"start": 184.5, "end": 196.0,
 "parts": [{"from": 186.0, "to": 190.5, "speed": 4},
           {"from": 192.0, "to": 193.5, "speed": 0}]}
```

- `speed` is one of 1, 2, 4 or 0 (0 = cut). Time not covered by a part plays at 1.
- `clipgrab.clean_plan(plan) -> dict`:
  - Clamps parts into [start, end] and drops empty parts.
  - Sorts the parts. Where parts overlap, the later-added one wins.
  - Rejects unknown speeds with `ValueError`.
- `clipgrab.plan_length(plan) -> float`: the output seconds. The same formula is mirrored in `video.js` for the live display.
- `clipgrab.suggest_plan(clip) -> dict | None`:
  - The range comes from `pick_throw` on the motion data.
  - Each still run longer than 1 s inside the range gets `speed: 4`.
  - If the result is still over `GIF_MAX`, start is moved later until it fits.
- The last plan used is saved to `clip.json` as `plan`. Reopening the same link restores it.

### 2.3 Render: `clipgrab.render(clip, plan) -> Path`

- Validates with `clean_plan` and `plan_length`.
- Walks output time in steps of 1/`GIF_FPS`:
  - Each step advances clip time by the current part's speed / `GIF_FPS`.
  - Cut parts are skipped.
- Decodes `proxy.mp4` sequentially and takes the first frame at or after each target time.
- Encodes animated WebP: `libwebp_anim`, `GIF_WIDTH` 640, `GIF_FPS` 20, `ANIM_QUALITY` 75, loop 0.
- Cache name: `anim-plan-<sha1(plan)[:10]>-20fps-q75.webp`. The same plan is not rendered twice.
- `make_gif` stays for the compose tool.

### 2.4 Web server (`tools/web_manage.py`)

- `POST /api/video/open {link}` → `{uid, name, map, agent, side, site, ability, duration, start, end, offset, motion:{times, values}, plan}`, where `plan` is the saved plan or the suggestion. Runs outside the store lock, like `/api/clip/load`.
- `GET /api/video/file?uid=` → `proxy.mp4` as `video/mp4`, **with `Range` support (206 Partial Content, `Accept-Ranges: bytes`)**. Without it the browser cannot seek.
- `POST /api/video/save {uid, plan, name, map, side, site, agent, ability, howto, stand, target}`:
  - Renders outside the lock.
  - Inside the lock, it goes through the existing `take` path with animation-only on: `lib.add` + positions + ability tag + taken record.
  - It also saves `plan` to `clip.json`.
- The existing `/api/clip/*` routes stay until the new page is proven; they are removed in a later cleanup.

### 2.5 Web page

- New `assets/web/video.js`, plus a video page section in `index.html` and styles in `theme.css`.
- `source.js`: when a pasted link or source entry is a YouTube clip, open the video page instead of the sheet screen.
- The old clip bar and GIF bar in `clip.js` stay reachable until the cleanup.

## 3. Errors

- Opening fails (network, repeated 403, video removed or private): show the message and a ลองใหม่ button. Nothing is written except `.part` files.
- A `.part` proxy or render is never served or used.
- Render fails: show a toast. The page keeps the plan so the user can retry.
- Saving with an invalid plan: the server answers 400 with the reason (too short, too long, bad speed).
- Cache cleanup:
  - When the server starts, `proxy.mp4` files in `.cache/clips` not modified for 30 days are deleted.
  - Cache only; library files are never touched.

## 4. Tests

- `tests/test_clipgrab.py`:
  - `clean_plan`: clamping, overlap (later wins), bad speed, empty part.
  - `plan_length`: plain range, ×2/×4 parts, cut parts, a part crossing the range edges.
  - `suggest_plan` on synthetic motion data: still runs over 1 s become ×4, short ones do not, and the result is capped at `GIF_MAX`.
  - The render time walk: a pure helper, `plan_times(plan, fps) -> list[float]`, is tested for step sizes and cut skipping. `render` uses it.
  - `render` end to end on a small generated mp4 (PyAV writes a few seconds of synthetic frames). Checks: output is an animated WebP (`is_animated`), the frame count matches `plan_times`, and a second render reuses the cache.
- `tests/test_web_*`:
  - Range serving: a full request gets 200; `bytes=100-199` gets 206 with 100 bytes and a correct `Content-Range`; an out-of-range request gets 416.
  - `/api/video/save` with a stubbed render: the lineup is added animation-only, with pins, ability tag and taken record. An invalid plan gets 400.
- `node --test tests/web/`: `planLength` in `video.js` matches the Python cases.
- Manual: open `https://youtu.be/Qlbwecza9GI?t=376`. Check that the proxy plays, frame stepping works, the preview follows ×4 and cut parts, and the saved lineup autoplays when zoomed in the overlay.
- All existing tests still pass. Rebuild the exe with LineupMaster.exe closed.

## Out of scope

- Chapter list or whole-video import (the owner chose one chapter per link).
- A still cover image.
- Drawing arrows or text on the video (future tools on this page).
- Changes to the Qt compose tool.

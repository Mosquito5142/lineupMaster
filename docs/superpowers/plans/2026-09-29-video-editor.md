# Video editor page: implementation plan

> For agentic workers: executed inline in this session (superpowers:executing-plans style). Checkbox steps.

**Goal:** A clip lineup (YouTube or ValoPlant link) opens a video editor. It has a local proxy mp4, trim, ×2/×4/cut parts and a preview, and saves the result as an animation-only lineup.

**Architecture:**
- `clipgrab.py` gains three things: a proxy writer, motion data, pure plan functions (`clean_plan`, `plan_length`, `plan_times`, `suggest_plan`) and `render`.
- `web_manage.py` gains:
  - `/api/video/open`.
  - `/api/video/file`, served with HTTP Range.
  - A `plan` pre-step on `/api/source/take`, so saving reuses `take` instead of a new save route (a small change from the spec).
- `assets/web/video.js` replaces the sheet pane (left column) with the video pane for `src === "yt"` lineups. The right column (fields, pin map, take/skip) is reused.

**Tech stack:** Python 3.12, PyAV 18 (stream copy, `libwebp_anim`), yt-dlp, and plain JS in the browser.

## Global constraints

- Output: animated WebP, `GIF_WIDTH` 640, `GIF_FPS` 20, `ANIM_QUALITY` 75, loop 0. Output length must be from 0.3 s to `GIF_MAX` (10 s).
- Speeds are {0, 1, 2, 4}, where 0 means cut.
- Never hold the Store lock while touching the network or rendering.
- `make_gif`, `load` and the compose tool keep working.
- Cache cleanup removes only `proxy.mp4` files older than 30 days, and only under `.cache/clips`.

## Tasks

- [ ] **1. Plan functions and tests**
  - Add `clean_plan`, `plan_length`, `plan_times`, `still_runs`, `suggest_plan` to `clipgrab.py`.
  - Add tests in `tests/test_clipgrab.py` (PlanTest).
- [ ] **2. Proxy, motion, `open_video`, `render`, `prune_proxies`**
  - `Clip` gains `proxy_offset`, `fps`, `motion_times`, `motion`, `coarse_times`, `coarse`, `plan`.
  - `load()` must not treat a frameless cached `clip.json` as complete.
  - Test `render` end to end on a synthetic mp4 written with PyAV.
- [ ] **3. Web server**
  - Add `SourceBrowser.video_open`, `video_file`, `video_render`.
  - Add a Range-capable `_send_file`.
  - Routes: `/api/video/open` and `/api/video/file`.
  - `take` pre-step for `plan`; `take` saves `howto`.
  - Call `prune_proxies` at start.
  - Tests: Range (200/206/416) and take with a stubbed render.
- [ ] **4. Web page**
  - `video.js` with `cleanPlan`/`planLength` mirrors, exported for node.
  - Video pane HTML and CSS.
  - `source.js` hooks: `showCurrent` pane switch, `takeCurrent` plan branch, clip button → `openVideo`.
  - `tests/web/video.test.js`.
- [ ] **5. Verification**
  - Run the full unittest and node suites.
  - Manual run in the browser pane with Qlbwecza9GI?t=376.
  - Rebuild the exe once the user has closed it.

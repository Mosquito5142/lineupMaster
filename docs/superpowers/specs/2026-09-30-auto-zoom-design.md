# F10 auto-zoom follow mode

Date: 2026-09-30 · Status: approved in chat ("ทำเลย")

## Goal

Clutch situations leave no time to press numpad. A new mode on **F10** reads the zone name, the same way F9 does. On every confirmed zone change it:

- zooms straight to the best lineup for that zone, full screen, with animations autoplaying;
- shows a small minimap in the bottom-right corner (stand, target line, zone ring);
- speaks the lineup (name and howto).

F9 stays the old follow mode (big map and zone ring). F9 and F10 are exclusive: turning one on turns the other off.

## Limits (stated to the owner)

- Position is the OCR'd zone name, not coordinates. The image changes per zone crossing, about 2 s late (confirm = 2).
- Intent is a heuristic, and every zone change is logged so accuracy can be checked later.
- No extra game reading: no spike state, timer or enemies.

## Behaviour

- Candidates are lineups of the current map and side whose stand pin lies inside the zone ring that `follow_zone` computes, after the filters. They are ranked by the scores below.
- The browser shows exactly these candidates, zoomed on #1 (`Browser.auto_rels`).
  - numpad 4/6 cycle through them.
  - numpad 5 unzooms to a grid of them.
  - numpad * plays the paired animation.
  - F7/F8 act on the current one.
- Any other navigation key (map, site, side, show-all, map toggle) drops the auto list and falls back to normal browsing. The next zone change takes over again.
- A zone with no candidates shows the placeholder "<zone> — ไม่มีไลน์อัพแถวนี้" plus the minimap with the ring. A stale image is never kept.
- The header tail reads `F10 ซูมตามตัว · <zone> · กำลังไป A · เปิดทาง · 1/3`.

## Intent (`src/lineupmaster/intent.py`, pure functions)

**Regions.** Each callout label maps to a region:
- a leading `A`/`B`/`C` token gives `a`/`b`/`c`;
- a label containing `mid` gives `mid`;
- `Attacker Spawn` gives `atk`, `Defender Spawn` gives `def`;
- anything else takes the nearest site centre.

Site centres are the `X Site` callouts; without one, the mean of that site's callouts is used.

**In site.** The region is a site and the zone point is within `SITE_R` (0.11) of that site's centre.

**Trail.** It holds confirmed zones with their first/last seen times. It resets after 30 s with no reading, or when the map changes.

**Heading.**
- If the current region is a site, the heading is that site.
- Otherwise it is the site whose distance dropped the most from the previous distinct zone to the current one.
- With no previous zone, the nearest site.

**Site dwell.** Time spent continuously in-site in the heading site.

**Phase.**
- attack: `post` if in-site with site dwell ≥ 8 s; `info` in the attacker spawn region; otherwise `entry`.
- defense: `retake` if the trail (last 20 s) contains a different site region from the heading, or the player is outside the heading site and moving toward it; otherwise `hold`.

**Purpose of a lineup**, from its pins and site folder (`c` = centre of the lineup's site):

| side | stand in site | target in site | purpose |
|---|---|---|---|
| attack | yes | yes | post |
| attack | no | yes | entry |
| attack | any | no | info |
| defense | yes | any | hold |
| defense | no | yes | retake |
| defense | no | no | hold |

Without a target pin or a site, the purpose is `None`.

**Score.** Ties break by name.
- +3 if `site == heading`;
- +2 if `purpose == phase`;
- + (1 − min(1, stand distance to zone point / 0.2));
- + 0.1 × min(uses, 5).

## Log

On every F10 zone change, one JSON line goes to `.cache/auto-zoom.jsonl`: time, map, side, zone, region, heading, phase, top-3 rels. A `switch` line is added when 4/6 moves while the auto list is active. The file is trimmed to its last half once it passes 1 MB.

## Config

`hotkeys.auto_zoom = "f10"` (DEFAULTS). The existing `auto.*` settings (interval, confirm, blank_limit) apply to both modes.

## Tests

- `tests/test_intent.py`: regions, site centres, heading (straight, rotate A→mid→B), phase (entry / post after dwell / info in spawn; defense hold / retake), purpose table, ranking order, trail reset.
- Browser: `auto_zoom` on a synthetic map sets `auto_rels` ranked, zooms and returns the zone. An empty zone gives an empty list. A navigation key clears the list (app-level).
- The full suite stays green; rebuild the exe.

# Command exercise replay: handoff (5 Oct 2026)

For the next chat and for the owner. The reader has no memory of the build. Everything here was checked against branch `claude/command-exercise` on 5 Oct 2026: the files were opened, the page was built and measured in a browser. Where something was not checked, the text says so.

A review of this handoff on the same day raised twenty points. Each was checked again in the code or in the browser, and this text and the layout document were corrected. The page itself was not changed.

Companion files:

- `docs/command_exercise_layout.md`: the layout as built, measured in a browser, with ten reference images.
- `docs/command_exercise_plan.md`: the specification, with build notes on top (stages 1 to 4 and two fix passes).

Words used:

- **Subdistrict** (tambon): Mae Sai district has eight in the data.
- **Place record**: one statement in 2024 news about water depth at a named place. 21 records, 12 with a point.
- **Exercise item** (inject): an invented call or report, tagged "EX". 14 exist.
- **Lost shelter access**: a resident had a shelter of the chosen set within a 2 km walk before the flood, and has lost it at this replay hour. It is not a count of people stranded.
- **Planning class**: the A to E class of the signed protocol. **FPPS** is its 0 to 100 score.
- **O1, SE1**: two protocol cases. O1 is the project's own radar candidates of 16 Sep 2024. SE1 is the scenario built from the 2024 season envelope.
- **Trainee mode / hindsight mode**: the default hides everything after the replay hour; hindsight shows all.
- **Clock card**: region B1, top of the left column. The code calls it the situation card (`mae-sai-command-situation.tsx`), and so do the sentences about widths under 900 px, where a short form of it is all that is left of the left column.
- **Queue**: the owner's word (R17) for the subdistrict table, region B2. The code keeps the word (`mae-sai-command-queue.tsx`).
- **Right card** and **inspector**: region D. The inspector is its Detail tab: the detail of a subdistrict, of an exercise item or of a report saved on this device.
- **Map workspace**: the older Command page, a map with the retained research ranking. It is at `/command/` since R19 and was at `/command/archive/` before.
- **Planning overview**: the text page of the Planning section, one case at a time. It is at `/command/ver2/` since R19 and was at `/command/` before.
- **The pitch**: the hackathon pitch on Sat 31 Oct 2026, the date in the owner decision sheet. The same sheet gives Sun 18 Oct as the feature freeze.
- **HQ1 to HQ13**: the open questions of this handoff (section 9). "H12" alone is an item of the replay roadmap and is a different thing.

## 1. What this page is, and what it is not

1. It is a full-screen map that replays the Mae Sai flood of 9 to 19 September 2024, hour by hour (replay hours 0 to 264), for people who coordinate rescue.
2. The owner approved its purpose as an "exercise and after-action tool for rescue coordinators" (decision R18). Trainees read the situation, assign invented calls to callsigns and write a short brief.
3. It is not real-time, not an official warning and not a dispatcher. Nothing on it reaches a responder. The banner says so on every screen and cannot be closed.
4. The permitted use is set by the replay data itself (`permitted_use` in `timeline.json`): "Preparedness learning, planning exercises and post-event prioritisation discussion in competition and preview builds. Not for emergency response, evacuation orders or any operational decision; not an official warning."
5. Decision D7: the replay is the narrative surface for cases O1 and SE1 and is not a new case. So no score and no class is computed for a replay hour. The left half of the table is a count from the model. The right half is the protocol's fixed result, and it is empty today.

## 2. Where things are

| What | Where |
|---|---|
| Branch | `claude/command-exercise`. Local only: it was never pushed, so no preview address exists. |
| Based on | `claude/unify-lineages` (PR #43), merged into this branch on 5 Oct 2026 in commit `a1f06c6`. That merge took the unified branch as it stood at `c3cd262`. |
| What this branch lacks | One later commit of the unified branch: `a1a8a96`, "test(offline): wait for the map notice to settle before measuring it". It changes one file, `apps/web/scripts/browser-offline-smoke.mjs` (14 lines added, 2 removed). So this branch is not "PR #43 plus the page" until that commit is merged in (section 6.0). |
| Master | Not touched by this work. Whether PR #43 has been merged into master was not checked here: nothing was fetched. The local copy of the remote's master was last fetched on 4 Oct 2026; it ends at `aef8d99`, the merge of PR #42, and does not hold the unified branch. |
| Route | `/command/exercise/` (temporary). Root element: `main.command-page[data-command-exercise]`. |
| Route file | `apps/web/src/app/command/exercise/page.tsx` |
| Specification | `docs/command_exercise_plan.md` |
| Plan page (web) | https://claude.ai/artifact/PdXnwp2zzq52pKYarkSS1F ("Mae Sai Command Plan"). It was last updated on 4 Oct 2026: before the owner decisions of 5 Oct, before the build notes and before R19. The plan file in the repository is newer and wins. |
| Owner decision sheet | `docs/owner_decision_sheet_2026-10-05.md`. Questions Q10 to Q20 concern this page. Q5 concerns the older ranking on the map workspace at `/command/` (the sheet's heading still names `/command/archive/`, its address before R19). |
| Decision log | `docs/decision-log-d1-d16.md`, rows R17 (replace `/command/`), R18 (purpose, Thai text) and R19 (the swap of the Planning addresses). Row D7 is the "not a scored case" rule. |
| Reference images | `docs/command_exercise/01-rest-en.jpg` to `10-setup-sheet-en.jpg` (taken after the merge, at replay hour 84) |
| Merge report of the unified branch | `docs/unified_lineage_merge_report.md` |

Three things are on the owner's machine and not in the repository:

- the checkout of this branch: `C:/Users/iputu/fg-wt/command`;
- the earlier screenshots: `C:/Users/iputu/fg-wt/command-shots/`, one folder per build step (`stage0`, `s1` to `s4`, review `v1`, fix `f1`, review `v2`, fix `f2`, and `handoff` with the PNG originals of the ten reference images). About 1,050 PNG files in all. The folders `f2/scripts` and `handoff/scripts` hold the capture scripts. `handoff/scripts/measure.mjs` and `measure2.mjs` are the scripts that measured the layout document; their results (JSON files and about twenty more PNG files: focus mode, narrow windows, notices, dialogs) are in `handoff/measurements`. `handoff/review-fix` holds the scripts, results and screenshots of the checks made after the review of this handoff (sheets and dialogs, row heights with the controls open, the app-status pill with the service worker on);
- a Python environment that has pytest: `C:/Users/iputu/Documents/Flood Guard Clauudd/.claude/worktrees/2d5-map-assets-plan-d4f947/.venv` (Python 3.11.8). This checkout has no `.venv` of its own, and the `python` on the path belongs to another tool and has no pytest.

### Run it locally

From the repository root (commands of `README.md`):

```
pnpm install --frozen-lockfile
pnpm --filter @floodguard/web dev
```

Then open `http://localhost:3000/command/exercise/?t=84&lang=en`. `t` is the replay hour (0 to 264) and `lang` is `en` or `th`. Hour 84 is the modelled peak (12 Sep 12:00).

Opening the page with `lang=` in the address also stores that language for the whole site in this browser (section 4). Leave `lang` out to keep the stored language.

The development server writes `apps/web/AGENTS.md` and `apps/web/CLAUDE.md` and edits `apps/web/next-env.d.ts`. Remove the first two and restore the third before a commit.

The built site can be served without the development server. This is what the layout document was measured on:

```
pnpm --filter @floodguard/web build:competition
node apps/web/scripts/preview-static.mjs 4781
```

Then open `http://127.0.0.1:4781/command/exercise/?t=84&lang=en`. This preview sends the production security headers of `vercel.json`.

Checks that take a few minutes each:

```
pnpm lint
pnpm typecheck
pnpm test:web
```

The Python wording lint takes about five minutes: it lints its whole corpus about two hundred times. A plain `python -m pytest` does not run in this checkout: it answers "No module named pytest". Use one of these two:

```
uv sync --extra dev --extra theos2
uv run pytest -q tests/test_replay_wording_lint.py
```

```
"C:/Users/iputu/Documents/Flood Guard Clauudd/.claude/worktrees/2d5-map-assets-plan-d4f947/.venv/Scripts/python.exe" -m pytest -q tests/test_replay_wording_lint.py
```

The first pair is the way of `README.md`; it builds a `.venv` in this checkout and was not tried for this handoff. The second line uses the environment listed above and is what ran the lint for this handoff.

### Take screenshots

1. Start one of the two servers above.
2. Launch headless Chromium with `launchFloodGuardBrowser` from `apps/web/scripts/browser-launch.mjs`.
3. Open the page and wait for `main[data-command-ready="true"]`. Then wait for the network to go quiet (the grey street tiles), then about one second more.
4. Useful hooks: `[data-region="A"]` to `"I"` for the regions, `[data-command-row]` for the button of a table row, `[data-command-tool="fit"]` (and `view`, `find`, `focus`, `zoom-in`, `zoom-out`, `basemap`) for the tools, `[data-command-legend="chip"]`, `[data-command-card="chip"]`, `.leaflet-marker-icon[data-item]` for an exercise marker, `[data-command-action="details"]` in its popup, `[data-command-dialog]` on an open sheet (`setup`, `log`, `brief`, `help`, `info`).
5. `[data-command-row]` is not the row. It is a button inside the first cell, 31.4 px tall (106 px wide on a desktop, 131 px on a tablet). The row is the element around it that carries `data-tambon`, and a press anywhere on the row selects it. The height of a row is also the distance between two of these hooks: 46.5 px in English, 45.1 px in Thai, 44 px on a tablet.
6. The fit tool switches between the town and the district. Exercise markers stand apart only at the town zoom.
7. To see the app-status pill as a visitor does, let the browser context run service workers. The measuring scripts block them, and the pill is then the short one (layout document, weak spot 7).

## 3. What is built

Paths in this section are under `apps/web/src/` unless they start with another folder. The letters are the regions of the screen; `docs/command_exercise_layout.md` gives their positions.

| Part or behaviour | What it does | Files | Tests |
|---|---|---|---|
| Route and shell | Loads the replay data, keeps the replay hour, the language, the selection and which panel is open. Writes `t` and `lang` into the address. Measures the clear rectangle. | `app/command/exercise/page.tsx`, `components/mae-sai-command-exercise.tsx`, `lib/flood-timeline-command-replay.ts`, `lib/flood-timeline-command-data.ts`, `lib/flood-timeline-layout.ts` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command-replay.test.ts`, `lib/flood-timeline-command-data.test.ts`, `lib/flood-timeline-layout.test.ts` |
| A. Banner and information drawer | The exercise line in English or Thai. The (i) button opens permitted use, limits, 26 assumptions, 10 sources and the note that the Thai text was not reviewed by a native speaker. | `components/mae-sai-command-chrome.tsx`, `lib/flood-timeline-command-copy.ts` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command-copy.test.ts` |
| B1. Clock and figures | Replay time, replay hour, phase, assumed river stage, three model figures, open exercise items, the line "what changed since the hour before", a model-limit line, the button of the situation brief. | `components/mae-sai-command-situation.tsx`, `lib/flood-timeline-command.ts` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command.test.ts`, `components/mae-sai-command-markers.test.tsx` |
| B2. Subdistrict table | Eight rows, two column groups. Left: this hour's count (lost shelter access with a bar and a change arrow, residents in modelled water, the "+" mark, place records). Right: O1 chip, SE1 chip, planning position; all dashes today. Three controls. The order is held while the pointer is in the table. | `components/mae-sai-command-queue.tsx`, `lib/flood-timeline-command-table.ts`, `lib/flood-timeline-command.ts` | `components/mae-sai-command-queue.test.tsx`, `lib/flood-timeline-command-table.test.ts`, `lib/flood-timeline-command.test.ts` |
| C. Navigation | Public, this page, the Studio replay at the same hour, the Exercise menu (setup, log, situation brief), language, help. On a tablet: one menu button. | `components/mae-sai-command-chrome.tsx` | `components/mae-sai-command-exercise.test.tsx`, `components/mae-sai-command-brief.test.tsx` |
| D. Right card, Detail of a subdistrict | This hour's figures, impassable road length, key facilities in water, the summary at the modelled peak (held back in trainee mode until hour 84), the place records, one card per protocol case ("Not issued yet"). | `components/mae-sai-command-inspector.tsx`, `lib/flood-timeline-command-table.ts` | `components/mae-sai-command-queue.test.tsx`, `lib/flood-timeline-command-table.test.ts` |
| D. Right card, an exercise item | The item's fields, "How to get near (facts only)", "Shelters near this point", the urgency rule, and the fixed bar Assign, Brief, Done and a fourth button (acknowledge, drop). | `components/mae-sai-command-incident.tsx`, `lib/flood-timeline-command-brief.ts`, `lib/flood-timeline-command-log.ts` | `components/mae-sai-command-brief.test.tsx`, `lib/flood-timeline-command-brief.test.ts`, `lib/flood-timeline-command-log.test.ts` |
| D. Right card, "Known by now" | Two fixed lines: first that no public hourly river record was found, then the sentence on the place records that have a point (how many, and at how many of them the model is consistent, wet or dry). Then dated rows, newest first, each with its evidence tag. The Trainee / Hindsight switch. A place link moves the map. | `components/mae-sai-command-feed.tsx`, `lib/flood-timeline-command-feed.ts`, `lib/flood-timeline-command-reports-copy.ts` | `lib/flood-timeline-command-feed.test.ts`, `components/mae-sai-command-markers.test.tsx` |
| E. Tool rail, view popover, find box | Seven round tools: view, basemap, zoom in, zoom out, fit (town or district), find a place, focus mode. The find box lists only what is known by the replay hour in trainee mode. | `components/mae-sai-command-chrome.tsx`, `components/mae-sai-command-find.tsx`, `lib/flood-timeline-command-table.ts` | `components/mae-sai-command-exercise.test.tsx`, `components/mae-sai-command-queue.test.tsx`, `lib/flood-timeline-command-table.test.ts` |
| F. Time dock | Previous and next event, play, one hour back and forward, three speeds, eleven day chips, a track with event marks, the phase band and rain bars. Everything after the playhead is hatched. | `components/mae-sai-command-timebar.tsx`, `lib/flood-timeline-command-replay.ts`, `lib/flood-timeline-command-feed.ts` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command-replay.test.ts`, `lib/flood-timeline-command-feed.test.ts` |
| G. Legend | A chip that opens three tabs: Map, Reports, Exercise. | `components/mae-sai-command-chrome.tsx` | `components/mae-sai-command-exercise.test.tsx`, `components/mae-sai-command-markers.test.tsx` |
| H. Watermark, credits, scale bar | "EXERCISE · ฝึกซ้อม" tiled across the map, inside the map and under the names and markers. | `components/mae-sai-command-chrome.tsx`, `components/mae-sai-command-map.tsx` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command-map.test.ts` |
| I. One-line notice | What failed, the tap the page waits for, Undo for 10 seconds, a new exercise call, the offline basemap note. One at a time. | `components/mae-sai-command-chrome.tsx`, `components/mae-sai-command-exercise.tsx` | `components/mae-sai-command-brief.test.tsx`, `components/mae-sai-command-markers.test.tsx` |
| Help sheet | Opened with the `?` key or the help button of the navigation. A short introduction, the five steps of the act flow, eight rows of keys, the line that names the official numbers 1784, 1669 and 191 and says this page does not reach them, and a link to the information drawer. | `components/mae-sai-command-chrome.tsx` (`CommandHelpSheet`), `lib/flood-timeline-command-copy.ts` (`COMMAND_HELP`, `COMMAND_HELP_KEYS`), `lib/flood-timeline-command-act-copy.ts` (`COMMAND_HELP_ACT_STEPS`) | `components/mae-sai-command-exercise.test.tsx`, `components/mae-sai-command-brief.test.tsx`, `lib/flood-timeline-command-copy.test.ts` |
| Focus mode | Key F or the last tool of the rail. The clock card and the table fold to one line each and the time dock to a 44 px bar; the model tag stays in sight. The map is not fitted again. Focus mode is part of the replay state and is not written into the address. | `lib/flood-timeline-command-replay.ts` (the `focus` field), `components/mae-sai-command-exercise.tsx`, `components/mae-sai-command-situation.tsx`, `components/mae-sai-command-queue.tsx`, `components/mae-sai-command-timebar.tsx` | `components/mae-sai-command-exercise.test.tsx`, `lib/flood-timeline-command-replay.test.ts` |
| Keys | One function turns a key press into an action: Space, the arrows (with Shift for a day), `[` and `]`, F, `?`, U and Escape. It leaves keys held with Alt, Ctrl or the Command key to the browser, and text fields and open dialogs to themselves. The layout document, section 10, has the full map. | `commandKeyAction` in `lib/flood-timeline-command-replay.ts`; the listener is in `components/mae-sai-command-exercise.tsx` | `lib/flood-timeline-command-replay.test.ts` |
| The map | Grey street tiles (online only) or terrain shading, modelled water in two blue tones with a hatch for the lowest confidence, a veil outside the district, roads in four line styles, subdistrict outlines and names, reported shelters, the command centre, 42 key facilities (off by default), the season envelope (hindsight only), the staging point and a dashed straight line to the selected item. | `components/mae-sai-command-map.tsx`, `lib/flood-timeline-command-map.ts`, `components/mae-sai-map-kit.tsx` | `lib/flood-timeline-command-map.test.ts`; the map layer itself has no mounted test (checked in a browser) |
| Markers and popups | Place records (speech bubble with a count), exercise items (octagon or rounded square), reports saved on this device (dashed sign on the subdistrict name), count marks at the district zoom, "no reports received" marks. Popups are built from text nodes only. | `components/mae-sai-command-markers.tsx`, `lib/flood-timeline-command-incidents.ts`, `lib/flood-timeline-command-reports-copy.ts` | `components/mae-sai-command-markers.test.tsx`, `lib/flood-timeline-command-incidents.test.ts` |
| Brief sheet and situation brief | A nine-line brief of one item, Thai first, with Share (where the browser has it), Copy and a two-line text-message version. The situation brief gives the three figures, the three subdistricts with the most lost access and roads newly impassable. | `components/mae-sai-command-brief.tsx`, `lib/flood-timeline-command-brief.ts`, `lib/flood-timeline-command-act-copy.ts` | `components/mae-sai-command-brief.test.tsx`, `lib/flood-timeline-command-brief.test.ts` |
| Setup sheet | Roster of callsigns, staging point (two reported sites or a tap on the map), start hour, mode, items on or off, speed, pause for a life-at-risk item, reset. | `components/mae-sai-command-setup.tsx`, `lib/flood-timeline-command-log.ts` | `components/mae-sai-command-brief.test.tsx`, `lib/flood-timeline-command-log.test.ts` |
| Exercise log | Every action with replay time, device time, role, callsign and action. The newest 50 rows on screen, up to 500 kept, CSV export with a `simulated` column. | `components/mae-sai-command-setup.tsx`, `lib/flood-timeline-command-log.ts`, `lib/flood-timeline-command-device.ts` | `lib/flood-timeline-command-log.test.ts`, `lib/flood-timeline-command-device.test.ts` |
| Wording | Every string of the page and every panel as rendered passes the shared wording lint in both languages. | `lib/replay-wording-rules.json`, `lib/replay-wording-lint.ts` | `lib/replay-wording-lint.test.tsx`, `tests/test_replay_wording_lint.py` |

Test counts on this branch, run for this handoff on 5 Oct 2026: `pnpm test:web` ran 109 files and 1,324 tests, all passing. 15 of those files are the page's own, with 339 tests. The Python wording lint passed with 72 tests.

### File map

Components (`apps/web/src/components/`):

| File | What it does | Depends on |
|---|---|---|
| `mae-sai-command-exercise.tsx` | The shell: state, keys, focus handling, the clear rectangle, and where every panel is placed. | every other file in this table and every library below |
| `mae-sai-command-exercise.module.css` | The page tokens (`--c-*`), regions A, B1, C, E, F, G, H, I, popups and tooltips of the map, dialogs, and the breakpoints. | the Command palette in `apps/web/src/app/globals.css` |
| `mae-sai-command-map.tsx` | The Leaflet map: panes, basemap, water painter, roads, veil, names, shelters, envelope, selection outline, staging point, fits inside the clear rectangle. | `mae-sai-command-markers.tsx`, `mae-sai-map-kit.tsx`, `lib/flood-timeline-command-map.ts`, `lib/flood-timeline-layout.ts`, `lib/flood-timeline-envelope.ts`, `mae-sai-command-chrome.tsx`, the copy files, Leaflet |
| `mae-sai-command-markers.tsx` | Marker drawings as inline SVG, popups, the marker layer, legend glyphs. | `lib/flood-timeline-command-incidents.ts`, `lib/flood-timeline-command-feed.ts`, `lib/flood-timeline-command-reports-copy.ts`, `lib/flood-timeline-reported-depths.ts`, `lib/public-report.ts`, `mae-sai-map-kit.tsx` |
| `mae-sai-command-markers.module.css` | Styles of markers, count marks, device signs and item popups. | page tokens |
| `mae-sai-command-chrome.tsx` | Banner, information drawer, help sheet, navigation, tool rail, view popover, legend, watermark, credits, notice, the shared dialog wrapper. Exports `COMMAND_EXERCISE_ROUTE`. | the copy files, `mae-sai-command-markers.tsx` (glyphs), `mae-sai-command-map.tsx` |
| `mae-sai-command-situation.tsx` | B1, the clock card, and its two-line form in focus mode. | `lib/flood-timeline-command.ts`, copy files |
| `mae-sai-command-queue.tsx` | B2, the table, its controls, the tablet tabs. | `lib/flood-timeline-command-table.ts`, `lib/flood-timeline-command.ts` |
| `mae-sai-command-queue.module.css` | Table styles and the plan chips. | page tokens |
| `mae-sai-command-inspector.tsx` | D, the right card, its chip, the subdistrict detail and the case cards. | `lib/flood-timeline-command-table.ts`, `components/command-workspace.tsx` (for `ACTION_TEXT`) |
| `mae-sai-command-inspector.module.css` | Card and detail styles. | page tokens |
| `mae-sai-command-incident.tsx` | The inspector of an exercise item with its action bar, and of a device sign. | `lib/flood-timeline-command-brief.ts`, `lib/flood-timeline-command-log.ts`, `lib/public-report.ts` |
| `mae-sai-command-feed.tsx` | "Known by now" and the mode switch. | `lib/flood-timeline-command-feed.ts` |
| `mae-sai-command-feed.module.css` | Feed styles. | page tokens |
| `mae-sai-command-find.tsx` | The find-place box. | `lib/flood-timeline-command-table.ts` |
| `mae-sai-command-find.module.css` | Find-box styles. | page tokens |
| `mae-sai-command-timebar.tsx` | F, the time dock. | `lib/flood-timeline-command-replay.ts`, `lib/flood-timeline-command-feed.ts`, `mae-sai-command-feed.tsx` (mode switch) |
| `mae-sai-command-brief.tsx` | The brief sheet. | `lib/flood-timeline-command-brief.ts`, `mae-sai-command-chrome.tsx` (dialog) |
| `mae-sai-command-setup.tsx` | The setup sheet and the log sheet, and the CSV download. | `lib/flood-timeline-command-log.ts`, `mae-sai-command-chrome.tsx` |
| `mae-sai-command-act.module.css` | Styles of the action bar, the sheets and the staging badge. | page tokens |
| `mae-sai-map-kit.tsx`, `mae-sai-map-kit.module.css` | Shared with the Studio replay: canvas overlay, popup and tooltip builders from text nodes, keyboard handling of popups. | Leaflet only |

Libraries (`apps/web/src/lib/`), all pure functions unless noted:

| File | What it does | Depends on |
|---|---|---|
| `flood-timeline-command.ts` | The figures: district figures, rows per subdistrict, change since the hour before, rounding, the order of the rows with its rules. No score, class or position. | `flood-timeline.ts`, `flood-timeline-evacuation.ts` |
| `flood-timeline-command-table.ts` | Table rows as printed, the hold of the order, the planning overlay reader, subdistrict detail, peak summary, the find index. | `planning-assessment-overlay.ts`, `flood-timeline-command.ts`, `flood-timeline-command-feed.ts`, `flood-timeline-command-map.ts` |
| `flood-timeline-command-feed.ts` | The dated rows of "Known by now", `knownBy(t)`, what each mode shows at an hour, the marks of the time track. | `flood-timeline.ts`, `flood-timeline-command.ts`, `flood-timeline-evacuation.ts` |
| `flood-timeline-command-incidents.ts` | Parser of the exercise file, the urgency rule, how each marker state is drawn, marker placement, count marks, device reports per subdistrict, modelled depth at a point. | `flood-timeline.ts`, `flood-timeline-command.ts` |
| `flood-timeline-command-brief.ts` | Facts about an item (nearest counted shelters, access node, nearest road under 0.3 m, staging), the brief, the text-message version, the situation brief. | `flood-timeline-command.ts`, `flood-timeline-command-feed.ts`, `flood-timeline-command-incidents.ts`, `flood-timeline-command-log.ts`, `flood-timeline-command-map.ts`, the copy files |
| `flood-timeline-command-log.ts` | Callsign rule, roster, setup, the five handling states, undo, the log, CSV export, the storage keys. | `flood-timeline-command-replay.ts`, `flood-timeline-command-incidents.ts`, `flood-timeline-command-feed.ts` |
| `flood-timeline-command-device.ts` | Reads and writes the three storage keys in the browser, with a memory fallback. Not pure. | `flood-timeline-command-log.ts`, React |
| `flood-timeline-command-replay.ts` | Replay state, speeds, event stops, the keys, `t` and `lang` in the address. | `flood-timeline-link.ts`, `policy-links.ts` |
| `flood-timeline-command-map.ts` | Water tones, label points, the veil, the scale bar, road style per state, whether a reported site is wet. | `flood-timeline.ts` |
| `flood-timeline-command-data.ts` | Fetches the replay files, the optional overlays, the peak summary, the exercise file and the envelope raster. Not pure. | `flood-timeline.ts`, `flood-timeline-command-incidents.ts`, `flood-timeline-command-table.ts`, `flood-timeline-envelope.ts`, `flood-timeline-evacuation.ts` |
| `flood-timeline-command-copy.ts` | The copy file: English and Thai wording of the banner, clock, figures, table, inspector, tools, legend, help and drawer. | `flood-timeline-copy.ts`, `flood-timeline-command.ts` |
| `flood-timeline-command-reports-copy.ts` | Wording of markers, popups, the feed and the two modes. | `flood-timeline-command-feed.ts`, `flood-timeline-command-incidents.ts` |
| `flood-timeline-command-act-copy.ts` | Wording of the act flow: action bar, brief sheet, setup, log, notices. | `flood-timeline-command-brief.ts`, `flood-timeline-command-log.ts` |

Other files the page needs:

| File | Role |
|---|---|
| `apps/web/public/exercises/mae-sai-2024/injects.v1.json` | The exercise items file: 14 invented items (2 at life at risk, 4 urgent, 8 of information), English and Thai, each "EX-nn", marked `"simulated": true`. |
| `apps/web/src/lib/flood-timeline-layout.ts` | `clearRect`, `clearRectPadding`, `panIntoRect`, `popupFitInRect` (added by this branch beside the Studio helpers). |
| `apps/web/src/lib/planning-assessment-overlay.ts` | The strict parser of a planning result file (came with the unified branch). |
| `apps/web/src/lib/use-public-reports.ts` | `useStoredPublicReports`: reads the reports the Public page saved in this browser. |
| `apps/web/src/lib/flood-timeline-envelope.ts`, `flood-timeline-reported-depths.ts` | Shared with Studio. This branch added one optional argument to each (hatch colours; a time horizon for the popup). Studio passes neither. |

What this branch changed outside its own files (`git diff --stat claude/unify-lineages...HEAD`): `apps/web/src/app/layout.tsx` (the app-status pill hides itself on this page), `components/command-workspace.tsx` (`ACTION_TEXT` exported), `components/mae-sai-flood-timeline.tsx` and its style sheet (three helpers moved to the map kit), `components/public-report-page.tsx` (one sentence), `lib/use-public-reports.ts`, `lib/flood-timeline-envelope.ts`, `lib/flood-timeline-reported-depths.ts`, `lib/flood-timeline-layout.ts`, both wording-lint tests, and `lib/public-report.test.ts`.

## 4. Data the page reads, what it stores, and what it never sends

### Files it reads

All are static files of the site. The replay files are the same `r4` files the Studio replay uses, in `apps/web/public/studies/mae-sai-2024-timeline/r4/`.

| File | Size | Feeds |
|---|---|---|
| `timeline.json` | 353 kB | Phases, river stage keyframes, days, shelters (19 reported, 113 candidates, the plan), 21 place records, hourly rain at two gauges, dated checks, sources, assumptions, limits, permitted use. Almost every panel. |
| `tambons.geojson` | 46 kB | Outlines, names, the veil, which subdistrict a point lies in. |
| `roads.geojson` | 713 kB | Road lines and their state per hour, impassable length, named roads. |
| `facilities.geojson` | 10 kB | The 42 key facilities and "facilities in water". |
| `access-nodes.bin` | 436 kB | Lost shelter access, for the 2024 set and for the plan's sites; the access line of an item. |
| `hand-codes.png` | 898 kB | The water layer, and the modelled depth at a point. |
| `hillshade.webp` | 156 kB | Terrain shading when the street tiles are not there. |
| `exports/tambon_replay_summary.json` | 100 kB | "At the modelled peak" in the subdistrict detail. |
| `unosat4009/envelope.png` | 17 kB | The 2024 season envelope, hindsight mode only. |
| `apps/web/public/exercises/mae-sai-2024/injects.v1.json` | 15 kB | The exercise items. |
| `/planning-overlays/mae-sai-2024/o1.json` and `se1.json` | do not exist | The plan columns. Each load asks for both and gets "404"; the table then shows dashes. |

Together the page reads about 2.7 MB of replay data. It does not read the satellite images, the VIIRS maps or the other export files.

The one outside address is the grey street basemap: `https://tile.openstreetmap.org`. Without it the page shows terrain shading and says so.

### What it stores on the device

All in the browser's local storage. In a private window the exercise still runs and lasts until the page is closed.

| Key | Holds | Written by | Cleared by |
|---|---|---|---|
| `floodguard:command-exercise:setup:v1` | Roster of callsigns, staging point, start hour, mode, items on or off, speed, pause for a life-at-risk item | Setup sheet, the mode switch, the speed buttons, the view popover | "Reset exercise" (undo for 10 seconds) |
| `floodguard:command-exercise:handling:v1` | Per item: state, callsign, urgency set by the operator, drop reason | Assign, Done, and the other actions | "Reset exercise" |
| `floodguard:command-exercise:log:v1` | The exercise log, newest 500 rows | Every action and every setup change | "Reset exercise" |
| `floodguard:public-reports:v1` | Up to 50 reports saved by the Public report page | The Public page only. This page reads it and never writes it. | Nothing on either page. Only clearing the site's data in the browser. |
| `floodguard:language:v1` | English or Thai, shared by the whole site | The language button, or opening the page with `lang=` in the address. Measured in a fresh browser: `?t=84&lang=th` stored "th" at once; with no `lang` in the address nothing was stored. | Nothing; it is overwritten |

"Reset exercise" removes every key that starts with `floodguard:command-exercise:` and no other key (`commandKeysToClear` in `lib/flood-timeline-command-log.ts`). The address bar holds `t` and `lang` and nothing else of the page.

### What it never sends

- The page makes no request that carries data. It only fetches its own static files and street tiles.
- A brief leaves the device only through the device's own share sheet, the clipboard, or a text-message link. That link is `sms:?&body=...` with no recipient filled in.
- A brief and the CSV hold no rain value, no free text of an item, no note of a device report and no statement text of a place record. Tests in `lib/flood-timeline-command-brief.test.ts` and `lib/flood-timeline-command-log.test.ts` check this.
- The log stores roles and callsigns, never names. A callsign with seven or more digits is refused before it is stored.

## 5. Decisions made, and choices the owner has not confirmed

### Decided by the owner

| Decision | Recorded in |
|---|---|
| `/command/` is to be replaced entirely by a rescue-coordination exercise replay of Mae Sai 2024, with "a full-screen map and HUD panels". | R17, part 1 |
| The queue. R17's words: "Its queue shows two things side by side: the residents cut off at the replay hour, and the protocol's planning score." The build differs from these words in two places. The left group counts residents who lost shelter access, which is not a count of people cut off or stranded. The right group shows the two class chips and a planning position, and no score: the score is printed only in the inspector's case card (builders' choice 10 below; sheet Q13). | R17, part 1 |
| The class is shown from both cases (O1 and SE1), each labelled. One is chosen later. | R17, part 1 |
| Public reports and SOS are to be tried on the map as markers with popups. The page must not read as a feed of incoming calls. | R17, part 1 |
| Purpose: "exercise and after-action tool for rescue coordinators". Banner: "Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning". | R18, part 1; plan, "Owner decisions" 1 |
| No Thai reviewer is available. The assistant writes and checks the Thai text, and the page says that no native speaker reviewed it. | R18, part 2; plan, "Owner decisions" 2 |
| The map workspace is the default Planning page at `/command/` again, and the planning overview is at `/command/ver2/`. | R19 (the owner's request of 5 Oct, built on the unified branch) |
| The owner continues the Command page in a new chat. | The owner's request that opened this handoff. The brief of the handoff adds the Public view; section 7 covers it. |

Not in this table, because the decision log does not record them as owner decisions:

- **The look of the GISTDA disaster platform.** R17 records only the full-screen map and the HUD panels. The clean look copied from the GISTDA screenshot is written in the plan (section 3), and the build brief names it as the owner's reference. The colour, overlap, Thai and touch rules are the plan's (sections 3 and 8).
- **That `/command/archive/` only forwards.** R19 lists it as point a, a choice made while building that the owner has not decided.

### Recorded two ways: owner decision in the plan file, build choice in R18

The plan file opens with "Owner decisions, 5 Oct 2026" and lists these three there. R18 lists the same three under "What was built on that basis, and is not an owner decision". The two files have to agree; HQ10 asks which is right.

| Item | Plan file, "Owner decisions" | Decision log, R18 | Asked in |
|---|---|---|---|
| Plan choices 2 to 6 are built as recommended and stay provisional | Decision 3: they "proceed as recommended" and are "provisional until the owner answers each one" | Built as recommended; they "stay provisional until the owner answers" | Sheet Q12 to Q16; HQ1, HQ4, HQ10 |
| Choice 7 (a tag on the 2024 pleas that news reprinted) is not applied | Decision 4: "not approved" | "not applied" | Sheet Q17; HQ10 |
| No SOS practice mark | Decision 5: "not built" | "The SOS practice mark is not built" | Sheet Q14; HQ10 |

### The five provisional plan choices (R18)

| Plan choice | As built | Sheet question |
|---|---|---|
| 2. Addresses and name | Header name "Command (exercise)" / "ฝึกซ้อมสั่งการ" is built inside the page. No address was changed. | Q12. Its address half is overtaken by R19 and is asked again in HQ1; the name is part of HQ4. |
| 3. Defaults of the two rankings | Left: sorted by lost shelter access, 2024 shelter set, all residents at road nodes. Right: planning position from SE1; both chips always shown. | Q13 |
| 4. Reports this week | Place records, exercise items, and reports of this device as a sign on the subdistrict. Nothing travels between devices. | Q14 |
| 5. Exercise items | 14 items, written by the assistant in both languages. | Q15 |
| 6. The future | Hidden by default (trainee mode). Hindsight is one switch away. | Q16 |

### Choices the builders made (not confirmed by the owner)

Sheet Q20 asks about ten of these. Two of its ten have changed since the sheet was written: the urgency rule was reworded (number 12 below), and the shelter star at the district zoom now has a 44 px target (it was 28 px).

| # | Choice | Where it shows |
|---|---|---|
| 1 | The page opens at replay hour 36 (10 Sep 12:00), the midday before the river rises. | First visit without `t` |
| 2 | The clock card is taller than the plan's 164 px (193 px in English, 200 px in Thai at 1440 x 800). | B1 |
| 3 | The model-limit line stands on the card at every hour ("the current is not modelled" before the river falls). The plan asked for it only while the water recedes. | B1 |
| 4 | Roads that are passable again are not named while the river falls. A road is named only when it becomes impassable as a whole. | B1, situation brief |
| 5 | The "+" mark is on every row where more than half of the residents had no shelter in reach before the flood: six rows with the 2024 set. | B2 |
| 6 | Order of the rows: a row with a higher printed figure always passes; a lead of 25 residents is needed between rows that print the same figure; a row above zero always passes a row at zero. | B2 |
| 7 | The three controls of the table start behind a button on screens up to 840 px tall and on a tablet. | B2 |
| 8 | The footer of the table is short; the full sentence of the plan is one hover or tap away. | B2 |
| 9 | Ordering by planning is switched off until a case gives a planning position. A unit with several rows shows the row of its first flood input. | B2 |
| 10 | The planning score is printed only in the inspector's case card, with tier, protocol versions and anchors. The O1 chip is amber, as the protocol's display rule says. | D |
| 11 | A share just under the whole is printed ">99%"; a share on a base under ten residents is left out. | D |
| 12 | The urgency rule has two steps. Life at risk: people on a roof, or people standing in water at chest height or above. Urgent: an infant or a bedridden person, or no food for a day. | Legend, item inspector, the exercise file |
| 13 | The 14 items: their places, hours and wording. Each has a point of its own, 130 to 310 m from a community point. | Map |
| 14 | Items arrive at their hour in both modes and are never listed in "Known by now". Playback pauses when a life-at-risk item arrives. | Map, time dock |
| 15 | An item of information shows no waiting clock on the map. | Markers |
| 16 | In trainee mode a shelter counts from the start of the day it is first reported; a news article with a date and no time counts from the end of its day. | Map, feed |
| 17 | In trainee mode a shelter's occupancy counts are held back, in the inspector and in the popup. | D, popups |
| 18 | Rows of "Known by now": one row per statement, shelters one row per day, rain only when an hour reaches 10 mm, a model row from 10 residents on. | Feed |
| 19 | The event buttons stop at every hour that has a mark on the track. | F |
| 20 | Water and terrain shading are drawn inside the eight subdistricts only. | Map |
| 21 | The town view of the fit tool is the located place records and the command centre, with about 500 m around them. | E |
| 22 | The legend leaves out two styles the data has no case of (a road outside the model, a reported site in modelled water). It has three tabs. | G |
| 23 | Wet facilities are blue and a wet shelter is struck through in dark ink, so red stays for impassable roads. | Map |
| 24 | The watermark lies under names and markers, not over them. | H |
| 25 | A count mark at the district zoom is two pills: place records, and exercise items behind the "EX" tag. They are never added. | Map |
| 26 | The season envelope is an ink-and-white hatch on this page; Studio keeps its yellow. | Map, hindsight |
| 27 | The map's own arrow keys are off, so the arrows always step the replay. | Keys |
| 28 | A new device starts with five example callsigns (BOAT-1, BOAT-2, WADE-1, TRUCK-1, MED-1). | Setup sheet |
| 29 | A closed item can be reopened. Acknowledge and Drop are behind the fourth button. | Action bar |
| 30 | A report saved on this device has no Assign and no brief. No brief is built from a place record. | D |
| 31 | The role of a log row follows from the action; the page has no role picker. | Log |
| 32 | Mode, items, pause and speed are stored with the setup. The language in the address wins over the stored one. | Device |
| 33 | The replay pauses when a brief opens. Reset closes its sheet and can be undone for 10 seconds. The key U undoes. | Act flow |
| 34 | The brief adds the urgency in brackets, the callsign on its first line, and the point to four decimals. | Brief |
| 35 | The find box lists at most six names and leaves out the candidate sites. | E |
| 36 | Each page load asks for two overlay files that do not exist, so the browser console shows two "404" lines. | Console |
| 37 | Importing `ACTION_TEXT` brings the code of the old Command workspace into this page's bundle. | Bundle size |
| 38 | The list of pages on which the app-status pill hides itself is now set per build profile, so the public build names no Command address (made during the merge). | `apps/web/src/app/layout.tsx` |

## 6. What is not done, in the order to do it

### 6.0 First: bring the branch level with the unified branch and master

1. This branch holds the unified branch as it stood at `c3cd262`. One later commit is missing: `a1a8a96`, which changes only `apps/web/scripts/browser-offline-smoke.mjs` (section 2).
2. Once PR #43 is in master, merge master into this branch with a merge commit. No rebase and no squash: either would remove the signing commits (section 8, "Signed files"). The merge needs a fetch, which this handoff did not make.
3. Run the checks of section 2, then `apps/web/scripts/browser-offline-smoke.mjs`. By the local copies of the branches it is the only file such a merge changes; look at the merge's own list of files to be sure.
4. Only then push the branch and open a draft pull request, if the owner says yes to HQ2.

What can start before the owner answers HQ1, at the temporary address:

- 6.3, the browser smoke of the new page. Keep the address in one constant of the smoke, so the swap changes one line.
- 6.4, the full `pnpm verify:frontend`.
- 6.5, the tablet pass, and 6.6, the polish round.
- From 6.2, the part that names no address: the page asking the service worker to save the replay data.

What waits for HQ1: 6.1, and from 6.2 the entries that name the page's address (the install list and `STAFF_OFFLINE_PATHS`).

### 6.1 Reconcile the addresses with R19, then swap the page into `/command/`

The state today:

| Address | Shows today | Owner decision |
|---|---|---|
| `/command/` | The older map workspace (with its retained research ranking) | R17: the exercise page replaces it. R19: the workspace is the default again. |
| `/command/ver2/` | The planning overview (text page) | R19 |
| `/command/archive/` | One sentence and a forward to `/command/` | R19, point a (a build choice) |
| `/command/cases/` | Case list | unchanged |
| `/command/exercise/` | The new exercise page | temporary |
| `/command/planning/` | Nothing | The plan proposed it for the overview, before R19 |

R17 and R19 pull in different directions, and R19 says so (its point h). This is open question HQ1 in section 9. Do not move anything before the owner answers.

A link to `/command/` means the map workspace today, and a link to `/command/ver2/` the planning overview. After the swap each such link has to point at the page it means, so each one needs a decision. This command lists the files that name a Command address:

```
grep -rl "/command/" apps/web/src apps/web/scripts apps/web/public
```

Found today: under `apps/web/src`, 22 files that are not tests (20 code files and 2 JSON copy files) and 11 test files; 18 files under `apps/web/scripts`; under `apps/web/public`, the eight briefs and `landing/product/capture-manifest.json`.

Once answered, the swap touches at least:

- `apps/web/src/app/command/page.tsx` and the new home of whatever leaves `/command/`.
- `COMMAND_EXERCISE_ROUTE` in `components/mae-sai-command-chrome.tsx`, and the test that pins it (`components/mae-sai-command-exercise.test.tsx`, "lives at the temporary route").
- `apps/web/src/app/layout.tsx` (the per-profile list above) and `STAFF_OFFLINE_PATHS` in `components/pwa-register.tsx`.
- `apps/web/src/lib/replay-wording-lint.test.tsx`: it names `src/app/command/exercise/page.tsx` in three places.
- `apps/web/scripts/write-offline-assets.mjs` (the install list and the list of required pages).
- 18 script files under `apps/web/scripts/` name `/command/` today; `browser-offline-smoke.mjs` alone has 56 such lines, many with selectors of the workspace.
- The research-score checks (`apps/web/scripts/research-score-guard.mjs`, used by `offline-smoke.mjs` and `browser-offline-smoke.mjs`). Today they require `/command/` to show exactly the eight retained values under their label. With the exercise page there, the page list of those checks must change on purpose. Note that the exercise page will print "Class E never means safe" once a class E is issued, and the guard's list of written forms matches "Class" followed by a letter.
- The eight published briefs link "Planning" to `/command/?aoi=...`. Their hashes are pinned in `apps/web/public/briefs/catalog.json`, so they cannot be rebuilt casually. After the swap such a link would land on the exercise replay whatever the case. The workspace answers this today with one line that names the case (R19, point i). The exercise page has nothing for it.
- The header "Planning" link of every other page (`components/workspace-header.tsx`).
- The landing links, which the plan's own route step named: `components/landing/landing-nav.client.tsx`, `components/landing/landing-page.tsx`, `components/landing-v1/scene-frame.tsx`, `components/landing-v1/supporting-sections.tsx`, and the copy files `lib/landing-v1/story.json` and `lib/landing/copy.en.json`. All of them link to `/command/`.
- `components/policy-page.tsx`: one link to `/command/`.
- The links between the Planning pages, and from Studio and the evidence library: `components/command-workspace.tsx`, `components/planning-candidate-overview.tsx`, `components/candidate-case-context.tsx`, `components/research-report-notice.tsx`, `components/command-archive-forward.tsx`, `components/studio-workspace.tsx`, `components/evidence-library.tsx`, and `lib/case-selection.ts`, which names three Command addresses (`/command/`, `/command/ver2/` and `/command/archive/`).
- The route files `app/command/page.tsx`, `app/command/ver2/page.tsx` and `app/command/archive/page.tsx`.
- The eleven test files that name a Command address: in `components/`, `command-case-notice.test.tsx`, `command-workspace.test.tsx`, `landing-v1/scene-frame.test.tsx`, `mae-sai-command-exercise.test.tsx`, `planning-pages.test.tsx`, `public-case-summary.test.tsx`, `pwa-register.test.tsx` and `workspace-header.test.tsx`; in `lib/`, `case-selection.test.ts`, `policy-links.test.tsx` and `replay-wording-lint.test.tsx`.
- `apps/web/scripts/build-case-briefs.mjs`: it writes the "Planning" link of the briefs for the next build (`/command/ver2/` today).

### 6.2 The offline pass

Nothing of the page is in the offline lists yet. Measured on the competition build of this branch:

| Item | State |
|---|---|
| Blocking install | 144 files, 11,079,970 bytes: 11.1 of the 12.0 MB budget. About 0.9 MB is left. The page's code chunks are already inside it (every script chunk is). |
| The page itself (`/command/exercise/`, 62 kB of HTML) | Not in the install list of `write-offline-assets.mjs`, and not in `STAFF_OFFLINE_PATHS`. Without a connection the address does not open (read from `apps/web/public/sw.js`: a page that is not saved has no fallback; not tried in a browser). |
| The exercise file (15 kB) | Not in the install list. |
| The replay data | Saved only after the Studio replay page has rendered: that page posts `FLOODGUARD_CACHE_CASE_REPLAY` to the service worker (`components/mae-sai-flood-timeline.tsx`). The Command page posts nothing. The bucket is 25 files, 6,296,150 bytes of a 6.5 MB budget; the export files (which hold the peak summary) are a second bucket, 906,375 of 1,000,000 bytes. |
| Street tiles | Never cached. The terrain shading stands in. |

To do: add the page and the exercise file to the install list (about 77 kB), have the page post the worker's existing message once it has rendered, and add the route to the offline smokes. The budget check (`apps/web/scripts/offline-install-budget.mjs`) fails the build above 12,000,000 bytes.

### 6.3 Browser smokes for the new page

None exists. No smoke script names `/command/exercise/`, so `pnpm verify:frontend` does not open the page in a browser.

- Model a new smoke on `apps/web/scripts/study-browser-smoke.mjs`. It drives the Studio replay on the built site with its own small static server, blocks every other origin, turns service workers off, collects page errors and failed requests, and uses `expect.poll` for anything that settles late.
- Add the route to `ROUTES` in `apps/web/scripts/csp-smoke.mjs`.
- Allow the two expected "404" requests for the overlay files, or the smoke will fail on them.
- Worth checking in it: the banner text, the figures at hour 84 (~7,100, ~16,100, ~164 km), no panel overlap, the selected subdistrict inside the clear rectangle, trainee mode at hour 20 (no place record in the find box), the path select, assign, brief, done, and the two storage rules (reset clears only the Command keys).

### 6.4 The full `pnpm verify:frontend`

Not run on this branch as one command. During the merge these parts were run and passed: lint, typecheck, contract tests, web tests, both builds, `verify:profiles`, `offline-smoke.mjs`, the three `node --test` files, `test:evidence-assets`, `verify-study-assets.mjs`, `browser-offline-smoke.mjs` and `csp-smoke.mjs`. Not run: `study-browser-smoke`, `policy-browser-smoke`, `browser-evidence-library-smoke`, and the full Python suite.

### 6.5 The tablet and phone pass

- Tablet (1024 x 700) is built and measured; see the layout document. It was never tried on a real tablet or with a finger.
- Below 900 px wide only a short form exists: banner, a short situation card, the map, the legend chip, the menu and a three-button time dock. The card says that the table and the map tools need a wider window. The bottom sheet of the plan is not built.
- The acceptance test of the plan (two people, five timed questions on a tablet) was not run.

### 6.6 The polish round that was skipped

The build ran five stages and two review-and-fix rounds. The last visual polish round did not run. The list "Known weak spots" in `docs/command_exercise_layout.md` is its starting point.

### 6.7 Real planning classes in the right-hand columns

Waits for the owners' answers to Q1 to Q4 of the decision sheet (and Q5 before any protocol score appears on a Command page).

- The reader is `readCommandOverlay` in `apps/web/src/lib/flood-timeline-command-table.ts`; the loader is `loadCommandOverlays` in `apps/web/src/lib/flood-timeline-command-data.ts`.
- It expects `apps/web/public/planning-overlays/mae-sai-2024/se1.json` and `o1.json`.
- A file is used only when `parsePlanningAssessmentOverlay` accepts it, it is a portfolio case and not a fixture, it is the case asked for, and its publication level is `public`. Anything else gives the empty state.
- A Python test stands in the way on purpose: `tests/test_owner_unblocker_records.py` fails while any `planning-overlays` folder exists under the public web folder. It has to be changed in the same reviewed step that publishes a result.
- The chip styles with real classes were only ever seen on invented fixture units. Look at them with the first real file.
- The Planning view preset of the plan (class letters at the subdistrict names, replay paused) is not built.

### 6.8 Review findings skipped or only partly fixed

From the two fix reports. Rows that say "measured today" or "seen in" were checked again for this handoff; the other rows are as the fix reports state them.

| Finding | State |
|---|---|
| Markers that cover each other at the town zoom | Partly fixed. One overlapping pair remains at 1440 x 800 (a place-record bubble over the star of the shelter at the same place) and two or three at 1024 x 700. |
| Touch targets of 44 px | Partly fixed, measured today. Two places fall short: the place-record chip on the clock card is 190 x 19 px (its larger hit area is cut off by the chip's own `overflow: hidden`); in "Known by now" a source link answers on about 27 px of height and a place link on about 33 px. A third falls short in part: in the setup sheet the radio of "A point on the map" answers on its own 18 x 18 px only. Its label beside it is 329 x 20 px (353 x 21 px in Thai) and answers on a band 45 px tall, through an invisible extension, and the button "Pick on the map" in the same row is 44 px tall. So the choice has a 44 px target, but the round radio itself has not. The second code review named this control (353 x 21), and fix report f2 says that the smaller controls reach 44 px. |
| What was scanned for small targets | The first measurements of this handoff scanned the page at rest, the town view, an item popup, the item inspector, "Known by now" and the open legend. Sheets and dialogs were left out. After the review these were scanned too, at 1440 x 800 and 1024 x 700 in both languages, each control scrolled to the middle of its sheet first: the setup sheet, the log sheet, the help sheet, the information drawer, the situation brief and the brief of an item; the view popover, the find box, the Exercise menu, the tablet menu and the two trays of the action bar. Only the radio above was found under 44 px. Not scanned: the popups of place records and of shelters, and any width under 900 px. |
| Bottom sheet below 900 px | Not built; the page says so. |
| Shelters dated by day appear at 00:00 of that day in trainee mode; the command centre appears on 11 Sep although its first source is dated 12 Sep | Left as the plan says. Open question HQ8. |
| The assumptions in the information drawer name later facts (for example the knot of 11 Sep 02:00) at every hour | Left: they are the replay data's own text, in a list that is closed until opened. |
| The site's skip link stays in English when the page is Thai | Left: it belongs to `apps/web/src/app/layout.tsx`, which every page shares. |
| No test mounts the marker layer | Left: the tests run without a browser document. The decisions are pure functions with tests. A browser smoke (6.3) would close this. |
| Automated check that the watermark reads over water | Done by eye only. |
| A time readout on the playhead; a night band on the rain row | Not done. |
| Motion: cross-fade of the water and of the figures, a flash on a row that changes place, popups that rise | Not done. |
| Phone width: the shelter count badge covers the start of a subdistrict name | Left. The same badge also touches the name "แม่สาย" at the district zoom on a desktop (seen in `docs/command_exercise/01-rest-en.jpg`). |
| One Thai tag in the table head on a tablet sits tight in its box | Left. |
| The Evidence view (candidate sites, satellite images) | Not built. The view popover no longer offers it. |
| A path on the road network; a roster shared between devices | Not built (the plan puts both after the first release). |
| Text-message part counts | Arithmetic of the standard only; no carrier was tried. Share was tried with a stand-in for the browser's share sheet only. |
| A commit message of fix pass f2 lists two small items that are in the commit before it | Not amended (history is never rewritten on this branch). |

### 6.9 Thai text

- All Thai on the page was written by an AI assistant and checked in two review passes by an AI assistant. No native speaker has read it.
- The information drawer says so in both languages, and says the English text is the reference where the two differ.
- The wording lint's own Thai list is unsigned too. That is item H12 of the replay roadmap, due 22 Oct 2026, which R18 also names. It is not one of the questions of section 9: those are numbered HQ1 to HQ13 so that the two cannot be mixed up.
- One label is of a different kind in the two languages: the third speed button reads "Drill" in English and "1 ชม./นาที" (one hour per minute) in Thai. A review asked for the Thai form because the Thai word for "drill" also means "exercise".

## 7. The Public view

The next chat works on the Public view too. This is what the report and SOS pages do today.

### The report page (`apps/web/src/components/public-report-page.tsx`)

| Question | Answer |
|---|---|
| What does it store? | One record per report under the key `floodguard:public-reports:v1`, at most 50: a report id, the broad area (id and names), a depth band (ankle, knee, waist, chest) and depth in cm, a note of up to 500 characters, yes or no for "a photo was attached", the time saved, and `storage_scope: "device_local"`. The rules are in `apps/web/src/lib/public-report.ts`. |
| What about the photo? | It is previewed while the form is open. Only the yes or no is stored. The image file is not stored. |
| What does it send? | Nothing. `addReport` in `apps/web/src/lib/use-public-reports.ts` writes to local storage and nowhere else. The page says: "This note is not sent to an agency or shared with others." |
| No coordinates? | None. A report names a broad area only. |
| Can a report be deleted? | The page has no delete control. |

### The SOS page (`apps/web/src/components/public-sos-page.tsx`)

| Question | Answer |
|---|---|
| What does it store? | Nothing. |
| What does it send? | Nothing by itself. It shows three official numbers as phone links (1784, 1669, 191). After a three-second press and hold it offers "Call DDPM 1784" and "Compose SMS to 1784". The message body is the broad area and the household needs saved on the device. The phone or message app does the sending, and only when the person presses send there. |
| What does it read? | The household plan saved on the device (key `floodguard:household-plan:v2`), for the needs it lists. |

Other Public tabs call two outside services that the security header names: an address search and a walking router. They were not read for this handoff.

### What this branch changed in the Public view

Two things, both for the competition build only:

1. One sentence on the report page, after the promise that nothing is sent: "It also appears on this device's Command exercise map." It is shown only when `competitionPagesAvailable()` is true. `apps/web/src/lib/public-report.test.ts` checks it.
2. `useStoredPublicReports` in `apps/web/src/lib/use-public-reports.ts`: a read-only view of the stored reports that follows the browser's `storage` event and the window's focus.

### How a device report reaches the Command map today

1. A person saves a report on the Public page, in the same browser.
2. The Command page reads the same storage key through `useStoredPublicReports`. A report saved in another tab shows without a reload.
3. `deviceReportsByTambon` (`lib/flood-timeline-command-incidents.ts`) keeps the reports whose area is one of the eight subdistricts.
4. The map shows a dashed sign above that subdistrict's name with the count. It is never a dot at a point.
5. Its popup reads "This device · the date saved · not part of the 2024 replay · tambon (subdistrict) only", with Details only. The note stays behind a tap and never enters a brief or the CSV.

Nothing crosses from one device to another. A report on a phone never shows on a tablet.

### Stage B: reports between devices (not built)

The plan (section 6) lists what an opt-in relay would need:

- a report contract in `packages/contracts`;
- report endpoints in `services/api`, with storage, a rate limit and a host;
- a `connect-src` change in `vercel.json`, and CORS settings;
- consent text in both languages with a version number, replacing today's promise that nothing is sent;
- a named data controller and a contact for deletion;
- a stated retention period (proposed: 72 hours, then deletion);
- a legal check of explicit consent for health-related needs and of storage outside Thailand;
- a screen that says a relay does not replace calling 1784, 1669 or 191.

Proposed fields: subdistrict, an optional coarse 250 m cell chosen by the reporter, depth, need categories, a band for the number of people, time and consent version. Free-text notes are dropped or held until moderated. Never collected at any stage: name, ID, house number, exact position, the photo file, nationality, device identifiers.

### The compact map notice on the Public home map

- When the map background cannot load, the Public home map shows one line and one button ("Map background unavailable", "Options"), 62 px tall, directly below the button "View map results as a list". The full sentence and the actions open behind "Options". The code is in `apps/web/src/components/geo-map.tsx`; `browser-offline-smoke.mjs` measures it at nine screen sizes.
- It was built during the merge of the unified branch and was not a question to the owner (R17, point h). Sheet Q19 asks the owner to confirm it.
- While it is shown the map is at least 448 px tall, so a short screen scrolls 88 px further.
- Three small overlaps remain that do not involve the notice (merge report, item 14; sheet Q48): with the map at its smallest (360 px tall) the attribution line overlaps the list button by 3 px; at 320 px wide in English it overlaps the priority card by 10 px; the location card of the address search can lie over the map tools on a short map.
- This branch did not touch that code.

### The public-production profile

Built with `pnpm --filter @floodguard/web build:public`. Checked by building it on this branch on 5 Oct 2026.

| It ships | It removes |
|---|---|
| `/` and `/public/`: the Public experience with five tabs (home, report, shelter, prepare, SOS). 55 files in the blocking install, 3.0 MB. | The route folders `command`, `studio`, `policy` and `public-cases` are moved aside before the build (`apps/web/scripts/build-profile.mjs`). |
| The Public data of Mae Sai (`offline-demo/mae-sai/public-bundle.json`, `public-areas.json`). | From the output: `landing`, `policy`, `command`, `studio`, `studies`, `evidence-library`, `public-case-projections`, `briefs`, `public-cases`, the staff bundles under `offline-demo`, the proposal evidence and the replay list (`apps/web/scripts/write-offline-assets.mjs`). |

- `apps/web/scripts/profile-artifact-smoke.mjs` fails the public build when any shipped file holds the text `/command/`. That is why lists of staff pages are compiled per profile (`layout.tsx`, `pwa-register.tsx`).
- So the new page exists in the competition build only. The sentence on the report page is not shown in the public build.
- One thing does ship that should be looked at: `exercises/mae-sai-2024/injects.v1.json` is a static file, it is in no removal list, and the public build of this branch contains it. It holds invented text only and is marked as simulated; no public page links to it. Open question HQ5.
- Seen in the same build, and not from this branch: the static folder `geoai/` (the images and the JSON file of the historical GeoAI research report) is in the public output too. Whether a public page uses it was not checked.

## 8. Rules that bite

| Rule | What it means in practice | Enforced by |
|---|---|---|
| The wording lint | Text may not say the page shows the present moment, may not promise what will happen, may not read as an official notice of danger, and may not present agreement between two data sets as proof. A plain "not" does not excuse a banned word: only the exact denials on the allow list pass ("not real-time", "not an official warning" and a few more). It has 18 rules and 14 allow entries, in English and Thai. | `apps/web/src/lib/replay-wording-rules.json`, read by both linters |
| Its file lists (Python) | Scans only what it lists: the manifest, bake scripts, `JSON_DOCUMENTS` (with the exercise file), `TEXT_DOCUMENTS` (the decision log, the plan, this handoff and the layout document), demo documents. A new document must be added to `TEXT_DOCUMENTS` by hand. The plan is also one of the targets the seeded-failure test plants a bad string in; the handoff and the layout document are read by the same loop and were left out of the targets to keep the run short. | `tests/test_replay_wording_lint.py` |
| Its file lists and fixed counts (web) | Picks up `src/components/mae-sai-*.tsx` and `src/lib/flood-timeline*.ts` by name, plus two route pages by path. Rendered panels are counted by hand: 13 around the map, `COMMAND_TABLE_PANEL_COUNT = 31`, `COMMAND_REPORT_PANEL_COUNT = 23`, `COMMAND_ACT_PANEL_COUNT = 29` per language. The test pins 270 linted items that carry a language tag, 193 of them rendered panels of this page. Add or remove a panel and the counts must change. | `apps/web/src/lib/replay-wording-lint.test.tsx` |
| D7: no score or class per replay hour | The figures hold no key named score, class, priority, FPPS, rank or position. The left group never prints those words. Ordering by planning never reads the hour's count. The briefs hold no score and no class. | `lib/flood-timeline-command.test.ts`, `components/mae-sai-command-queue.test.tsx`, `lib/flood-timeline-command-table.test.ts`, `lib/flood-timeline-command-brief.test.ts` |
| The banner | The approved line, word for word, with its parts joined by real text. No control closes it. | `lib/flood-timeline-command-copy.test.ts`, `components/mae-sai-command-exercise.test.tsx` |
| The watermark | "EXERCISE · ฝึกซ้อม" in both languages at once, tiled, so a cropped photo keeps the label. | the same two tests; over water it was checked by eye |
| Exercise items are never mistaken for real ones | The file must be marked simulated; every id starts "EX-"; no text shaped like a phone number, a soi, a house number or a person's title; urgency must follow from stated facts. Every marker and count mark wears the "EX" tag. Items and place records are never added together. | `parseExerciseFile` in `lib/flood-timeline-command-incidents.ts` and its tests; `components/mae-sai-command-markers.test.tsx` |
| The security header (CSP) | The page's own code contacts only its own origin and the street tile host (`tile.openstreetmap.org`). The header does not hold it to those two: its `connect-src` also allows `services.arcgisonline.com`, `a.tile.opentopomap.org`, `geocode.arcgis.com` and `routing.openstreetmap.de`, which other pages use. A new request from this page to one of those four would not be blocked, so the rule "two hosts only" is kept by the code and by review. No change of the header was needed. A relay (stage B) would need a `connect-src` change. | `vercel.json` (for every host outside its list), `apps/web/scripts/csp-smoke.mjs` (the route is not in its list yet) |
| Two deployment profiles | Competition has Command and Studio. Public-production has neither, and no shipped file may name a Command address. | `apps/web/scripts/build-profile.mjs`, `write-offline-assets.mjs`, `profile-artifact-smoke.mjs`, `verify-deployment-profiles.mjs` |
| Offline budgets | Blocking install: 12,000,000 bytes (11,079,970 used). Replay data on request: 6,500,000 bytes (6,296,150 used). Export files: 1,000,000 bytes (906,375 used). Over budget fails the build. | `apps/web/scripts/offline-install-budget.mjs`, `case-replay-inventory.mjs` |
| Trainee mode never shows a later hour | Feed rows, place records, shelter states, popup lines, the peak summary, the find box and the phase band's spoken name are all cut at the replay hour. | `feedAt`, `placeRecordsAt`, `placeRecordHorizon`, `reportedSiteHour` in `lib/flood-timeline-command-feed.ts`; `commandFindManifestAt` in `lib/flood-timeline-command-table.ts`; their tests and `components/mae-sai-command-markers.test.tsx` |
| Privacy of the brief, the CSV and the roster | First and last line of a brief are the exercise tag. No rain value, no free text, no note, no statement text. The CSV ends with `simulated` = true on every row and guards against spreadsheet formulas. Callsigns only: at most 12 characters, seven or more digits refused. | `lib/flood-timeline-command-brief.ts`, `lib/flood-timeline-command-log.ts` and their tests |
| Research scores on the Planning pages | `/command/ver2/` and `/command/archive/` must show no research score and no class; `/command/` must show exactly its eight retained values under their label. | `apps/web/scripts/research-score-guard.mjs`, used by `offline-smoke.mjs` and `browser-offline-smoke.mjs` |
| No planning result under the public web folder yet | Fails while a `planning-overlays` folder exists there, or any file there says it is a planning result. | `tests/test_owner_unblocker_records.py` |
| The AIT and MBRSC guard | No committed code may read those two flood products without a recorded grant, and no figure may stand beside their names. | `src/floodguard/ait_mbrsc_guard.py`, `tests/test_ait_mbrsc_guard.py` |
| Signed files | Never edit `docs/proposal_execution/planning_protocol_v1a.json`, `planning_protocol_v1b.json`, `RECEIPTS.jsonl`, or `docs/proposal_execution/automated_track/geoid_m1_v2_freeze_receipt.json` and the files it binds. Merge with a merge commit; a squash or a rebase removes the signing commits. | `tests/test_planning_protocol.py` |
| Published briefs | The eight briefs have pinned hashes; rebuilding them changes the hashes. | `apps/web/public/briefs/catalog.json` |
| Python versions | CI runs Python 3.12. The local environment is 3.11. A test can pass locally and fail in CI, or be skipped in one and run in the other (for example where an imaging package is missing). | `.github/workflows/ci.yml` |
| Browser checks on a slow runner | Three checks of `apps/web/scripts/study-browser-smoke.mjs` failed only on CI and were hardened: (1) the sticky replay stage measured once, before it had stuck; (2) a tap on a place-record marker that lay under a map chip on the Thai phone layout; (3) the search for a clear spot on the map, which refused a map without street tiles. The pattern for every new browser check: wait for a settled state with `expect.poll`, never look once; and do not depend on street tiles, which CI does not load. | commits `37d9225`, `4b206de`, `eebd353` |
| The development server leaves files | `apps/web/AGENTS.md`, `apps/web/CLAUDE.md`, and an edited `apps/web/next-env.d.ts`. | nothing; clean up by hand |

## 9. Open questions for the owner

The questions are numbered HQ1 to HQ13 ("handoff question"), so that none is taken for item H12 of the replay roadmap. Each can be answered with its number and one word, for example `HQ1 yes`. "Yes" means "as recommended". HQ10 asks for one word for each of three items.

| # | Question | Recommendation |
|---|---|---|
| HQ1 | Addresses. When the exercise page takes `/command/` (R17), where do the map workspace and the planning overview go? This is also the address half of sheet Q12. Option 1: the map workspace returns to `/command/archive/` and the planning overview stays at `/command/ver2/`. Option 2: the map workspace returns to `/command/archive/` as in option 1, and the planning overview moves to `/command/planning/` as the plan said, with `/command/ver2/` forwarding to it. Option 3: nothing moves, and the exercise page keeps `/command/exercise/` for the pitch. | **Option 1.** It changes the meaning of two addresses only, old `/command/archive/` links already mean the workspace, and nothing new is invented. Also say what a `/command/?aoi=...` link from a brief should do: recommended, forward it to the overview of that case. |
| HQ2 | May the branch be pushed and a draft pull request opened, so that a preview address exists for a tablet? (Sheet Q11.) | **Yes**, after PR #43 is in master and master is merged into this branch (section 6.0). Nothing is merged into master by this. |
| HQ3 | Should the older research ranking leave the map workspace before the swap? (Sheet Q5.) | **Yes.** Otherwise two kinds of score for the same eight subdistricts stand on Command pages once SE1 fills the table. |
| HQ4 | Do plan choices 3 to 6 stand as built, and the header name of choice 2, "Command (exercise)" / "ฝึกซ้อมสั่งการ"? (Sheet Q13 to Q16 and the name half of Q12; table in section 5.) A yes here says nothing about addresses: those are HQ1. | **Yes**, after looking at the page. Read the 14 items first (Q15). |
| HQ5 | The exercise file ships in the public build. Remove it there? | **Yes.** Add `exercises` to the removal list and to the artifact check. It is invented text, but it belongs to a staff page. |
| HQ6 | Offline: put the page and the exercise file in the install list, and save the replay data when the page is opened? | **Yes.** About 77 kB of the 0.9 MB left in the budget; the replay data is the bucket Studio already uses. |
| HQ7 | Below 900 px wide: build the bottom sheet, or keep the note "needs a wider window" for the pitch? | **Keep the note.** The users are at a desk or a tablet. |
| HQ8 | In trainee mode, should a shelter with a date and no time appear at the end of its day, like a news article? | **Yes.** One rule for every date-only item, and nothing appears before it could have been known. The command centre would then appear one day later than it does today (its first use is dated 11 Sep, its first source 12 Sep). |
| HQ9 | Do the builders' choices in section 5 stand? (Sheet Q20 covers ten of them.) | **Yes**, and name any number to change. |
| HQ10 | Three things stand as owner decisions in the plan file and as build choices in R18 (section 5): (a) plan choices 2 to 6 are built as recommended; (b) no tag on the 2024 pleas that news reprinted (sheet Q17); (c) no SOS practice mark (sheet Q14). Do (b) and (c) stay as built, and which record is right for each of the three? | **(b) no tag for the pitch; (c) no mark.** For the record, give one word for each of a, b and c: `decided` or `build choice`. For example: `HQ10 a build choice, b decided, c decided`. The plan file or R18 is then corrected so that the two agree. |
| HQ11 | Run the skipped polish round, limited to the "Known weak spots" list? | **Yes**, after the address swap. |
| HQ12 | Stage B (reports between devices) before the pitch? | **No.** It needs an API, a host, consent text, a data controller and a legal check. |
| HQ13 | Confirm the compact map notice on the Public home map? (Sheet Q19.) | **Yes.** |

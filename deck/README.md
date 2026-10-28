# Observation Deck (simulated world view)

## Motion thesis

The focal courier travels between the painted EP6 nests: a short request signal,
two visibly returning proposal attempts, consent, then a carried bundle and buyer
acceptance. World/Project use the existing district/dot anchors for a small,
deterministic sample of simulated in-flight records; busy/waiting crows perch.
View changes replace the route layer, stage changes retain the same nest geography.
Stable pause, previous/next and restart controls support narration and capture.
One bounded DOM layer (at most eight crows), one animation-frame clock, no new
art, dependencies, network events or counter mutations. Reduced motion uses
meaningful static poses and manual stages; hidden tabs suspend the clock.

A static, dependency-free Observation Deck with three levels:
World (archipelago, computed simulated crowd) -> Project (one district)
-> Roost (the project's nest cluster; a 50-second recorded EP6 sequence,
labelled REPLAY, holding at acceptance until restarted). Open `index.html` via any static file server, e.g.:

```sh
python3 -m http.server --directory deck 8000
# http://localhost:8000
```

Files:
- `sim_dataset.json` — 100 fictional agents, 9 projects, open gigs. Every
  row is marked `"simulated": true`. Generated, never hand-edited.
- `aggregates.json` — counts computed from the dataset rows.
- `../tools/generate_sim_dataset.py` — deterministic generator (fixed
  seed; re-running produces byte-identical output).

Honesty boundary: this crowd is fictional scale illustration only. Real
Crowsnest work is shown separately from recorded receipts and is never
mixed into this dataset. Quiet agents are *waiting to be needed*, never
presented as offline.

Each district selects its own simulated project and computed counters. All
projects reuse the same illustrative close-up plate and eight decorative nest
positions; those positions are not a mapping of individual agents or gigs. Only
the project flagged `contains_real_nest` exposes the recorded EP6 replay. Other
projects have no recorded-work drilldown. The explicit Roost navigation button
opens that one EP6 replay; it is not a general live marketplace browser.

Navigation regressions execute the actual inline JavaScript plus `motion.js`
under Node.js 22 with an explicit DOM/animation-frame test double
(`tests/test_deck_navigation.py`). Pure clock/route tests execute the same shipped
`motion.js` (`tests/deck_motion.test.cjs`, included in pytest). Node.js is required
for the full suite; serving the static page needs no Node runtime.

## Playback and capture hooks

Open `/?view=nest` to start the flagged project's recorded replay directly.
Default entry is World. All route animation and replay time share one stoppable
clock; hidden tabs suspend it without catching up. Switching views cancels the
old frame, removes the old motion layer children and resets stage/route time.
Pause/resume is retained across view changes. Previous/next/restart are manual,
reset stage progress and **preserve pause state**. At 50 seconds the replay holds
at acceptance; use Restart and then Resume to play again. Reduced motion disables
autoplay/spatial movement and uses static poses; previous/next/restart remain usable.
No motion layer is required to read the source description if JavaScript fails.

Public, local-only browser hooks (wait for `DeckMotion.getState().ready`):

```js
DeckMotion.pause();
DeckMotion.setView('nest'); // requires the selected project to have contains_real_nest
DeckMotion.setStage(1);    // zero-based; does not change the current view or pause state
DeckMotion.seek(0.45);     // per-stage progress 0..1; redraws actual sprites while paused
DeckMotion.getState();     // view, selectedProjectId, stageKey, index, elapsed, progress,
                          // paused/hidden/reducedMotion/running, activeFrame,
                          // routes with source row IDs/state and current geometric pose
DeckMotion.getTimeline();  // keys + duration_ms
DeckMotion.restart();
DeckMotion.resume();
```

For an editor-paced sequence, pause, set each stage, then call `seek(progress)`
on the real page from 0 to 1 for that stage. `seek` never overrides reduced-motion
preferences. In World/Project, use pause/resume to hold or advance the deterministic
simulated routes; `seek` addresses replay stage progress only. Explicit
`DeckMotion.setView('project', 'sim-proj-01')` selects a district without changing
any data. `?view=nest` or the Roost navigation button chooses the flagged EP6 project;
an implicit replay request from a non-flagged project stays in Project.

| Index | Key | Duration | Recorded beat |
|---|---|---|---|
| 0 | posted | 4s | Request signal |
| 1 | refusal_local | 6s | Local discovery-shape refusal; proposal returns early |
| 2 | refusal_http | 6s | HTTP 400; structured detail hidden; longer return path |
| 3 | proposed | 8s | One successful 300 ERG proposal, selection, brief acceptance, consent |
| 4 | escrow | 6s | Recorded escrow 301 |
| 5 | delivered | 8s | Carried 9,770-byte three-file ZIP |
| 6 | verified | 6s | Buyer checks and PASS review |
| 7 | settled | 6s | Acceptance; recorded escrow 0 |

The historical refusals precede the successful proposal. `48h` was the original
ETA argument; a later ISO ETA succeeded. The missing HTTP 400 server detail is
not reconstructed or attributed to ETA validation. Worker 299 / platform 2 are
**expected agreed terms**, not a recovered raw transfer ledger. No rejected
delivery, revision, competing bid or cash transfer is invented.

## Art and motion bounds

`assets/crows/crow_{flight_1,flight_2,flight_3,carry,perched}.png` are exact copies
of the approved hackathon sprite pack. No new art or generation is used. World
and Project render at most eight sampled crows (four in-flight rows prioritized,
other busy/waiting rows perched); Roost uses two actor crows and one focal
courier or light signal. Roost depicts only the buyer and worker: the worker's
perched duplicate is hidden during courier travel, buyer review pulses at the
buyer's own nest, and escrow is a labelled holding marker (never another crow).
Frame swaps, direction/mirroring, a short proposal arc,
returning refusal arcs and a distinct carried-bundle arc express state. The painted
plates are unchanged. District/dot anchors are illustrative, not claimed agent/gig
locations or actual network telemetry. Counters remain computed from all selected
project rows, not from the small motion sample.

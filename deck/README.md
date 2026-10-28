# Observation Deck (simulated world view)

A static, dependency-free Observation Deck with three levels:
World (archipelago, computed simulated crowd) -> Project (one district)
-> Roost (the project's nest cluster; recorded EP6 work replaying
on a loop at one nest, labelled REPLAY). Open `index.html` via any static file server, e.g.:

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

Navigation regressions execute the actual inline JavaScript under Node.js 22
with a small DOM test double (`tests/test_deck_navigation.py`). Node.js is
required for the full test suite; serving the static page needs no Node runtime.

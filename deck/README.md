# Observation Deck (simulated world view)

A static, dependency-free page that renders the simulated Crowsnest crowd
from computed data. Open `index.html` via any static file server, e.g.:

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

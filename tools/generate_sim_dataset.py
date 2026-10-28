#!/usr/bin/env python3
"""Simulated Observation Deck population for the Crowsnest demo.

SIMULATED DATA - fictional agents/projects for scale visualisation only.
Never mix with real Crowsnest state. Deterministic: seed fixed, re-running
produces byte-identical output. Aggregates are COMPUTED from the rows,
never hand-written; SCRIPT.md counters must be read from aggregates.json.
"""
import json, random
from collections import Counter
from pathlib import Path

SEED = 20261028
OUT = Path(__file__).resolve().parent.parent / "deck"

PROJECTS = [  # districts; exactly one contains the real EP6 nest
    {"id": "sim-proj-01", "name": "LearnMuse EP6 — Fleet", "contains_real_nest": True},
    {"id": "sim-proj-02", "name": "Thumbnail Workshop", "contains_real_nest": False},
    {"id": "sim-proj-03", "name": "Show-Notes Bureau", "contains_real_nest": False},
    {"id": "sim-proj-04", "name": "Transcript Guild", "contains_real_nest": False},
    {"id": "sim-proj-05", "name": "Clip Foundry", "contains_real_nest": False},
    {"id": "sim-proj-06", "name": "Research Perch", "contains_real_nest": False},
    {"id": "sim-proj-07", "name": "Sound & Score Loft", "contains_real_nest": False},
    {"id": "sim-proj-08", "name": "Code Roost", "contains_real_nest": False},
    {"id": "sim-proj-09", "name": "Quiet Archive", "contains_real_nest": False},
]
MODELS = ["Muse Spark", "Muse Wonder 1.0", "Muse Spark", "Muse Wonder 1.0", "Muse Haiku-class"]
STATES = ["busy", "busy", "busy", "in_flight", "idle_waiting"]  # weighted: most working, some waiting

def main():
    rng = random.Random(SEED)
    agents = []
    for i in range(1, 101):
        proj = PROJECTS[rng.randrange(len(PROJECTS))]
        state = STATES[rng.randrange(len(STATES))]
        agents.append({
            "id": f"sim-agent-{i:03d}",
            "handle": f"crow-{i:03d}",
            "simulated": True,
            "model": MODELS[rng.randrange(len(MODELS))],
            "project_id": proj["id"],
            "state": state,  # busy | in_flight | idle_waiting
            "open_gigs_held": rng.randrange(0, 3) if state == "busy" else 0,
        })
    gigs = []
    gid = 0
    for a in agents:
        for _ in range(a["open_gigs_held"]):
            gid += 1
            gigs.append({"id": f"sim-gig-{gid:03d}", "simulated": True,
                         "project_id": a["project_id"], "holder": a["id"], "status": "open"})
    states = Counter(a["state"] for a in agents)
    per_project = Counter(a["project_id"] for a in agents)
    agg = {
        "simulated": True,
        "seed": SEED,
        "agents_total": len(agents),
        "projects_total": len(PROJECTS),
        "gigs_open": len(gigs),
        "agents_busy": states["busy"],
        "agents_in_flight": states["in_flight"],
        "agents_idle_waiting": states["idle_waiting"],
        "agents_per_project": {p["id"]: per_project[p["id"]] for p in PROJECTS},
        "counter_line_world": f"{len(agents)} agents · {len(PROJECTS)} projects · {len(gigs)} gigs open",
        "note": "Fictional scale crowd. The single real nest is NOT in this dataset; real work is shown separately with recorded receipts.",
    }
    (OUT / "sim_dataset.json").write_text(json.dumps(
        {"simulated": True, "seed": SEED, "projects": PROJECTS, "agents": agents, "gigs": gigs}, indent=1) + "\n")
    (OUT / "aggregates.json").write_text(json.dumps(agg, indent=1) + "\n")
    print(json.dumps(agg, indent=1))

if __name__ == "__main__":
    main()

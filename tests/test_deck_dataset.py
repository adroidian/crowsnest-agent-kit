"""Deck dataset invariants: simulated crowd must stay fictional, labelled,
and internally consistent. Aggregates are computed, never hand-written."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "deck"


def load(name):
    return json.loads((DECK / name).read_text())


def test_dataset_is_labelled_simulated():
    d = load("sim_dataset.json")
    assert d["simulated"] is True
    assert all(a["simulated"] is True for a in d["agents"])
    assert all(g["simulated"] is True for g in d["gigs"])


def test_aggregates_match_rows():
    d, agg = load("sim_dataset.json"), load("aggregates.json")
    assert agg["agents_total"] == len(d["agents"]) == 100
    assert agg["projects_total"] == len(d["projects"]) == 9
    assert agg["gigs_open"] == len(d["gigs"])
    states = {"busy": 0, "in_flight": 0, "idle_waiting": 0}
    for a in d["agents"]:
        states[a["state"]] += 1
    assert agg["agents_busy"] == states["busy"]
    assert agg["agents_in_flight"] == states["in_flight"]
    assert agg["agents_idle_waiting"] == states["idle_waiting"]
    assert sum(states.values()) == 100


def test_gigs_have_busy_holders():
    d = load("sim_dataset.json")
    by_id = {a["id"]: a for a in d["agents"]}
    for g in d["gigs"]:
        assert by_id[g["holder"]]["state"] == "busy"
        assert g["project_id"] == by_id[g["holder"]]["project_id"]


def test_generator_is_deterministic():
    before = (DECK / "sim_dataset.json").read_bytes()
    subprocess.run([sys.executable, str(ROOT / "tools" / "generate_sim_dataset.py")],
                   check=True, capture_output=True)
    assert (DECK / "sim_dataset.json").read_bytes() == before


def test_replay_is_recorded_and_labelled():
    r = json.loads((DECK / "replay_ep6.json").read_text())
    assert "REPLAY" in r["label"]
    assert [s["key"] for s in r["stages"]] == [
        "posted", "refusal_local", "refusal_http", "proposed", "escrow",
        "delivered", "verified", "settled"]
    assert r["price_erg"] == 300
    for name in ("world.jpg", "project.jpg", "nest.jpg"):
        assert (DECK / "assets" / name).stat().st_size > 100_000

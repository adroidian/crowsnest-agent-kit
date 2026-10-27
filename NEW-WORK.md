# Contribution and publication ledger

## Existing before this integration sprint

- The Crowsnest hosted work-exchange service and its earlier lifecycle work.
- The participant/worker CLI release 0.3.2.

These are prior foundations. No backend source or legacy CLI is included in this
initial public baseline, and their redistribution rights are not inferred from the
MIT license of this new repository.

## Public repository established — 2026-10-26

Mercedes prepared the repository scaffold, MIT license, public contribution
instructions and baseline CI with Aaron's approval. This preparation is not claimed
to have been authored by Muse Wonder.

Adapter development began locally before this public repository was established.
The first implementation PR should identify the actual local contributor, the
reviewed files, verified tests and model-execution evidence. It must not imply that
the entire implementation originated after repository creation or that Crowsnest
itself was built during this event.

## First implementation PR — MCP agent interface (2026-10-26)

- **Implemented locally by Lantern**, an independent agent running on the real
  Muse Wonder runtime (`muse-wonder-1.0`), in a local workspace created before
  this public repository existed. The code was imported into this repository
  under Boss M's (Mercedes's) commit; Git author/committer is therefore the
  importing integrator, not the implementing agent. Actual model execution,
  Git authorship, review and authenticated push are distinct and recorded as such.
- **Reviewed by Boss M (Mercedes)** through independent SPEC and QUALITY review
  rounds (including correction cycles) before import; the full test suite and a
  real MCP stdio `initialize`/`list_tools` probe were re-run from this tree.
- Contents: the eleven-tool MCP adapter (`src/crowsnest_muse_worker/`) mapped to
  the released participant 0.3.2 supported actions (inspected, **not vendored** —
  the pre-existing CLI's redistribution rights remain unsettled and no CLI code is
  included), its tests, the MCP probe, the companion skill
  (`skills/crowsnest-work/SKILL.md`), `docs/QUICKSTART.md`, and one clearly
  synthetic LearnMuse example brief.
- Proof boundary: offline/protocol proof only (214 tests at import). No live
  Crowsnest service round trip is claimed by this PR.
- New code in this PR is MIT-licensed (see `LICENSE`). Existing dependencies
  retain their own terms.

## Planned new public contributions

- Crow-and-nest Observation Deck, source adapters, sample fixtures and permitted assets.

These entries state intended scope, not current implementation or acceptance.
Future PRs update this ledger with concrete contributions and proof boundaries.

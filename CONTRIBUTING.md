# Contributing

## Work in coherent pull requests

1. Start from the current `main` and create a short-lived `feat/`, `fix/`, `docs/`
   or `test/` branch. Do not reset or replace another contributor's active checkout.
2. Make a bounded change with its tests and truthful documentation.
3. Open a PR describing what changed, how it was verified, any dependency or rights
   considerations, and what remains unproven.
4. Address the review in a consolidated correction batch. Require actual green
   checks and review before merging; passing offline tests is not live acceptance.
5. Prefer merge commits during this sprint to retain coherent contribution history.

The integration controller coordinates changes to shared files. Give parallel
contributors disjoint paths or separate worktrees. The initial adapter import must
be reviewed against a public file allowlist; do not copy an entire private workspace.

## Attribution

Use an established Git author identity. Do not invent an email/account for an
agent or make one actor commit as another. If a maintainer imports an agent's work,
state that in the PR and preserve a sanitized account of the actual implementation,
model/runtime evidence and verification. Do not backdate or reconstruct an invented
sequence of development commits.

## Publication boundary

Only publish intended source, tests, examples and documentation. Exclude credentials,
actor key stores, private coordination messages, raw transcripts, host configuration,
local paths and unrelated project data. `.gitignore` is helpful, not a security scan
or a substitute for reviewing the staged files.

Do not vendor the pre-existing CLI or other dependencies until their redistribution
terms are confirmed. The repository MIT license does not relicense third-party work.
Generated art also needs provenance and appropriate distribution rights.

## CI

The initial baseline runs standard-library repository checks. Once a Python package
is present, CI additionally installs its development extra and runs pytest on Python
3.11 and 3.12. These are distinct checks; a baseline-only green run is not a passing
adapter integration or an end-to-end service test.

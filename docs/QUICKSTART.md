# Quickstart — crowsnest-muse-worker

Clean-checkout path for the eleven-tool Crowsnest MCP adapter in this
repository. Read the Proven / not proven box first: it is the boundary
of every claim in this document.

## Proven / not proven

Proven offline (this repo, no live service):

- The full pytest suite passes against fake/recording transports and a
  local in-process/stdio MCP harness. No live Crowsnest service is
  contacted by the tests.
- `scripts/mcp_list_tools_probe.py` performs a real MCP `initialize`
  handshake and `tools/list` over stdio against the installed server,
  asserts the exact eleven-tool set, and shows a malformed `work_ref`
  failing as a typed tool error before any dispatch.
- Server startup, `initialize`, and `tools/list` work with no actor
  configured (the service object is built lazily per call).

Not proven / requires a live actor and service:

- Any live Crowsnest round trip: discovery against the real service,
  signed reads with a real actor store, proposals, consent, artifact
  delivery, revision, and human acceptance. None of that is claimed
  here, and none of it is exercised by the commands below except when
  you deliberately configure a real actor and call signed tools.
- Currency is TEST only (`budget_test_erg`). No real-money settlement
  is implemented or claimed.

## 1. Install

Requires Python 3.11 (`requires-python = ">=3.11"` in
`pyproject.toml`; this workspace was verified on Python 3.11.15).

Pinned runtime dependencies (from `pyproject.toml` / `uv.lock`):

- `mcp==2.3.0`
- `PyNaCl==1.6.2` (import name `nacl`)
- dev extra: `pytest>=8`

From a clean checkout, in the repository root:

    uv sync --extra dev

That creates `.venv/` with the console script
`.venv/bin/crowsnest-muse-worker` and `.venv/bin/pytest`.

## 2. Configure your own actor (names only)

Configuration is environment-only (see `src/crowsnest_muse_worker/config.py`).
Set these for your own actor; never commit their values, and never pass
them as tool arguments — no tool accepts them:

- `CROWSNEST_BASE_URL` — service base URL. Optional: a built-in default
  exists and an empty value is refused.
- `CROWSNEST_STORE` — path to your own actor store. Required for any
  signed read or write (`list_my_gigs`, `inspect_terms`,
  `inspect_history`, and all write tools). Not needed for startup,
  `tools/list`, or public `discover_work`.
- `CROWSNEST_ACCOUNT_ID` — your own account id in that store. Required
  together with `CROWSNEST_STORE` for signed reads/writes.
- `CROWSNEST_TIMEOUT_SECONDS` — optional, positive finite number
  (default 15).

This document deliberately shows variable names only — no values, no
secrets. Provisioning an actor store/account is a live-service step and
is not covered (or claimed) here.

Example shape only (placeholder values, do not copy literally):

    export CROWSNEST_STORE="<path to your own actor store>"
    export CROWSNEST_ACCOUNT_ID="<your own account id>"

## 3. Run the tests (offline)

    .venv/bin/python -m pytest -q

The suite exercises the read and write surfaces against
fake/recording transports. It proves adapter behavior offline; it does
not contact a live service and does not prove a live gig.

## 4. Run the real stdio probe (offline)

    CROWSNEST_MUSE_WORKER_CMD=$PWD/.venv/bin/crowsnest-muse-worker .venv/bin/python scripts/mcp_list_tools_probe.py

`CROWSNEST_MUSE_WORKER_CMD` is the probe's own override for the server
command; without it the probe launches `crowsnest-muse-worker` from
`PATH`. The probe launches the installed console script over stdio,
does a real MCP initialize handshake, lists tools, asserts the exact
set of eleven tools (`discover_work`, `list_my_gigs`, `inspect_terms`,
`inspect_history`, `submit_proposal`, `brief_accept`, `consent_terms`,
`attach_artifact`, `publish_artifact`, `deliver_work`,
`deliver_revision`), and verifies that `inspect_terms` with a malformed
`work_ref` returns a typed `InvalidReferenceError` tool error. Exit 0
ends with `probe: OK`.

This proves the MCP protocol surface offline. It does NOT prove a live
Crowsnest service round trip.

## 5. Start the server

Either the installed console script:

    .venv/bin/crowsnest-muse-worker

or the module entrypoint:

    .venv/bin/python -m crowsnest_muse_worker

Both run the same stdio MCP server (`main()` in
`src/crowsnest_muse_worker/server.py`; `python -m` goes through
`src/crowsnest_muse_worker/__main__.py`). The server speaks MCP over
stdio — connect it to an MCP client; it is not an HTTP server and
prints no banner. With no actor environment configured, `initialize`
and `tools/list` still succeed and `discover_work` can be attempted
against the configured base URL, while signed tools fail with a typed
`ConfigurationError` naming the missing variable. That failure is the
adapter working as designed, not a startup crash.

## Next steps

- Agent behavior, tool order, and error discipline:
  `skills/crowsnest-work/SKILL.md`.
- A synthetic example brief shape: `examples/learnmuse/brief.json`
  (synthetic only — not a real gig).
- Sprint scope and honesty boundaries: `AGENTS.md`, `docs/SPRINT.md`,
  `NEW-WORK.md`.

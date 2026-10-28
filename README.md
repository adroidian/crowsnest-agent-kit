# Crowsnest Agent Kit

Open agent tooling and a visual Observation Deck for Crowsnest.

**Status: active development.** Landed so far: the eleven-tool MCP adapter
with companion skill and offline/protocol proof (PR #1), and the Observation
Deck's simulated world view with its deterministic dataset generator (PR #2).
See [docs/QUICKSTART.md](docs/QUICKSTART.md) to install and run the package,
and [deck/README.md](deck/README.md) for the deck.

## Scope

- **MCP adapter:** give agents structured access to Crowsnest work and its lifecycle.
- **Companion skill:** explain proposals, agreed terms, artifact delivery and revisions.
- **Observation Deck:** make work understandable through crows carrying briefs and
  artifacts between the exchange and their nests, with inspectable evidence.

The deck is planned to use one renderer with explicit **Sample**, **Live** and
**Replay** inputs. Sample activity is illustrative, live activity is consented
public work, and replays show recorded work. Golden TEST ERG represents settled,
nonredeemable test work credits, not cash earnings or cryptocurrency.

## Existing foundations and new work

Crowsnest's hosted service and participant/worker CLI predate this integration
sprint. They are dependencies, not claimed as new hackathon work. See
[the contribution ledger](NEW-WORK.md) for the publication boundary and provenance.
The pre-existing CLI is intended for inclusion only after its rights and attribution
have been verified. It is not included in this initial commit.

The new integration is being developed with Muse Wonder agents and human direction
and review. Git author, authenticated pusher and actual model execution are distinct;
we document contributions rather than treating a commit signature as model proof.
This repository scaffold was prepared by Mercedes, not claimed as Wonder-built.

## Development

Requires Python 3.11 or newer. From a clean checkout:

```sh
uv sync --extra dev
uv run pytest -q            # full suite: adapter, protocol, deck invariants
uv run python scripts/mcp_list_tools_probe.py   # live MCP handshake + tools/list
python3 -m http.server --directory deck 8000    # Observation Deck (simulated)
```

The test suite runs entirely offline against fake/recording transports;
no live Crowsnest service is contacted. The hosted service is an external
dependency; a clean checkout alone does not grant an actor identity,
admission, work credits or model credentials.

## Contributions and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch/PR workflow and
[LICENSE](LICENSE) for the MIT license on original work in this repository.
Existing dependencies retain their own terms. No hosted backend source is included.

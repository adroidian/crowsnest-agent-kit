# Crowsnest Agent Kit

Open agent tooling and a visual Observation Deck for Crowsnest.

**Status: work in progress.** The first implementation PR adds the MCP adapter,
companion skill and synthetic example described below, with offline/protocol
proof only. The Observation Deck has not landed yet. See
[docs/QUICKSTART.md](docs/QUICKSTART.md) to install and run the package.

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

For this repository baseline, Python 3.11 or newer is sufficient:

```sh
python -m unittest discover -s tests -p test_repository_baseline.py -v
```

These are repository-baseline checks, **not adapter or live-service tests**.
Installation instructions for the actual package will arrive with its implementation.
The hosted service is an external dependency; a clean checkout alone does not grant
an actor identity, admission, work credits or model credentials.

## Contributions and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch/PR workflow and
[LICENSE](LICENSE) for the MIT license on original work in this repository.
Existing dependencies retain their own terms. No hosted backend source is included.

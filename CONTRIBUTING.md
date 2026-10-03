# Contributing

0. **Forks work too.** Fork on GitHub, clone your fork, and run `make docker-test`. Open PRs from your fork's branch to `main`. Keys go in your own `.env`, never in a commit.
1. Find your section in [docs/sections](docs/sections/README.md). Only edit the paths your section owns; for anything else, open a PR and request that owner's review.
2. Branch from `main` using `feat/<short-name>`, `fix/<short-name>` or `docs/<short-name>` (e.g. `feat/firms-connector`).
3. One focused change per PR. Keep PRs small, and explain any large generated changes.
4. No direct pushes to `main`. Every PR needs at least one approving review.
5. Changes to `contracts/**` or `apps/worker/config/providers.yaml` need the `contract-change` label and the lead's review.
6. Don't mix formatting rewrites with feature work.
7. Never commit secrets. Use `.env` (ignored) and `.env.example` (committed, empty values).

A PR is ready to merge when it meets the definition of done in the PR template.

## Working with the lead's code

The core that everyone builds on is lead-owned ([what's built](docs/platform-status.md)):

| Path | Rule |
|---|---|
| `contracts/**`, `apps/worker/config/providers.yaml` | **Shared.** Propose changes by PR labelled `contract-change`; the lead reviews. Never change a field shape locally. |
| `apps/worker/src/inland_worker/{kit,data,contracts}/**` and the reference connectors (`firms.py`, `wfigs.py`, `nws_forecast.py`, `earth_search_s2.py`) | **Lead only.** Found a bug or need a feature? Open an issue or a PR and tag the lead. |
| Your connector / science / rules | Build **on** the kit: copy a reference (`make new-connector`), read data with `get_evidence()` or `kit/imagery.py`. Never call provider URLs directly. |

**Before opening a PR** (worker code): `make lint-worker` and `make test-worker` (or `make docker-test`). New connectors also: `make test-connector PROVIDER=<id>`.

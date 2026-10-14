# Contributing

Issues and pull requests are welcome.

1. Fork, clone, and run `make docker-test` (or `make test`). Everything runs offline on recorded fixtures.
2. Branch from `main` (`feat/<name>`, `fix/<name>`, `docs/<name>`) and keep each PR to one focused change.
3. Every change needs tests: a success case and an empty/failure case. Don't weaken tests to make them pass.
4. Changes to `contracts/**` or `apps/worker/config/providers.yaml` change shared formats: say so in the PR.
5. Provider calls only go through the worker's connector kit (`apps/worker/src/inland_worker/kit/`); see the
   [connector guide](docs/connectors/connector-guide.md).
6. Never commit secrets. Keys go in `.env` (git-ignored); new settings go in `.env.example` with an empty value.

Before opening a PR (worker code): `make lint-worker` and `make test-worker`. New connectors also:
`make test-connector PROVIDER=<id>`.

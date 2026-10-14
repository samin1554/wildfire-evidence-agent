# Inland Resilience Agent: developer commands.
# Full stack: make dev · make test · make e2e · make down

WORKER := apps/worker
ENVFILE := $(if $(wildcard .env),--env-file ../../.env,)

.PHONY: dev down logs migrate migrate-down seed test test-api test-web test-integration lint e2e e2e-ui \
        docker-build docker-test docker-test-live docker-fetch demo-line-fire help worker-install test-worker test-live lint-worker format-worker validate-contracts \
        test-connector record-fixture derive-fixtures new-connector

help:            ## list commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

worker-install:  ## install the worker's Python deps (uv)
	cd $(WORKER) && uv sync

test-worker:     ## all offline worker tests (no keys, no network)
	cd $(WORKER) && uv run pytest

test-live:       ## real calls to real providers (keys from .env)
	cd $(WORKER) && uv run $(ENVFILE) pytest -m live -s tests/live

lint-worker:     ## ruff lint + format check
	cd $(WORKER) && uv run ruff check . && uv run ruff format --check .

format-worker:   ## auto-format worker code
	cd $(WORKER) && uv run ruff check --fix . && uv run ruff format .

validate-contracts: ## check contracts/ (schemas, OpenAPI, examples)
	cd $(WORKER) && uv run pytest tests/test_contracts.py

test-connector:  ## shared suite + tests for one provider: make test-connector PROVIDER=firms
	cd $(WORKER) && uv run pytest tests/connectors/test_$(PROVIDER).py

record-fixture:  ## record a live fixture: make record-fixture PROVIDER=firms CASE=success ARGS="--area sb_county_bbox"
	cd $(WORKER) && uv run $(ENVFILE) python scripts/record_fixture.py $(PROVIDER) $(CASE) $(ARGS)

derive-fixtures: ## derive malformed/extra_fields (+empty): make derive-fixtures PROVIDER=firms ARGS="--empty-csv"
	cd $(WORKER) && uv run python scripts/derive_fixtures.py $(PROVIDER) $(ARGS)

new-connector:   ## copy a reference: make new-connector NAME=cimis GROUP=weather PATTERN=keyed  (keyed|arcgis|follow_link|stac)
	cd $(WORKER) && uv run python scripts/new_connector.py --name $(NAME) --group $(GROUP) --pattern $(PATTERN)

# --- Docker: identical environment on any machine (needs Docker Desktop) -------------------------
# --env-file: compose substitutes ${VARS} from the repo-root .env (it would otherwise look in infrastructure/)
COMPOSE := docker compose -f infrastructure/docker-compose.yml $(if $(wildcard .env),--env-file .env,)

docker-build:    ## build the worker image
	$(COMPOSE) build worker

docker-test:     ## offline tests inside the container
	$(COMPOSE) run --rm --build worker-test

docker-test-live: ## live provider tests inside the container (keys from .env)
	$(COMPOSE) run --rm --build worker-test -m live -s tests/live

docker-fetch:    ## fetch one provider in the container: make docker-fetch PROVIDER=wfigs_current ARGS="--bbox -124.5,32.5,-114.1,42.0"
	$(COMPOSE) run --rm --build worker fetch $(PROVIDER) $(ARGS)

demo-line-fire:  ## Line Fire burn-severity demo in Docker (no keys) → docs/research/line-fire-2024/output/
	mkdir -p docs/research/line-fire-2024/output && chmod 777 docs/research/line-fire-2024/output
	$(COMPOSE) --profile demo run --rm --build line-fire-demo

# --- Full stack (Milestone 1 demo) --------------------------------------------------------------------
GO_IMAGE := golang:1.23-bookworm
GO_RUN := docker run --rm -v $(CURDIR):/src -v inland-go-mod:/go/pkg/mod -v inland-go-build:/root/.cache/go-build -w /src/apps/api

dev:             ## start everything (postgres, redis, migrations, seed, api, worker, web) and wait for health
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")
	$(COMPOSE) up -d --build --wait postgres redis
	$(COMPOSE) run --rm migrate
	$(MAKE) seed
	$(COMPOSE) up -d --build --wait api worker-jobs worker-activity web
	@echo "\n  web  http://localhost:5173\n  api  http://localhost:8080/health\n"

down:            ## stop the stack (keeps data volumes; add V=1 to delete them)
	$(COMPOSE) down $(if $(V),-v,)

logs:            ## follow api + worker logs
	$(COMPOSE) logs -f api worker-jobs worker-activity

migrate:         ## apply database migrations
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) run --rm migrate

migrate-down:    ## roll back the last migration
	$(COMPOSE) run --rm migrate -path /migrations -database "postgres://inland:inland@postgres:5432/inland?sslmode=disable" down 1

seed:            ## load seed data (idempotent)
	@for f in database/seeds/*.sql; do \
	  echo "seed $$f"; $(COMPOSE) exec -T postgres psql -q -v ON_ERROR_STOP=1 -U inland -d inland -f /seeds/$$(basename $$f); \
	done

test:            ## all unit tests: worker (pytest), api (go test, in Docker), web (vitest)
	$(MAKE) test-worker test-api test-web

STACK_NET := inland-resilience_default
test-api:        ## Go tests in Docker (Go need not be installed); integration tests also run when `make dev` is up
	$(GO_RUN) $$(docker network inspect $(STACK_NET) >/dev/null 2>&1 && echo "--network $(STACK_NET) \
	  -e TEST_DATABASE_URL=postgres://inland:inland@postgres:5432/inland?sslmode=disable -e TEST_REDIS_URL=redis://redis:6379/15") \
	  $(GO_IMAGE) sh -c "go vet ./... && go test -count=1 ./..."

test-web:        ## web unit tests
	cd apps/web && npm ci --no-audit --no-fund >/dev/null && npx tsc --noEmit && npx vitest run

test-integration: ## worker + api integration tests against the running stack (make dev first)
	cd $(WORKER) && TEST_DATABASE_URL="postgres://inland:inland@localhost:55432/inland?sslmode=disable" \
	  TEST_REDIS_URL=redis://localhost:56379/14 uv run pytest tests/jobs/test_integration.py -q
	$(MAKE) test-api

lint:            ## lint everything
	$(MAKE) lint-worker
	$(GO_RUN) $(GO_IMAGE) sh -c 'test -z "$$(gofmt -l .)" && go vet ./...'
	cd apps/web && npx tsc --noEmit

e2e:             ## end-to-end acceptance against the running stack (make dev first)
	./scripts/e2e_demo.sh

e2e-ui:          ## browser end-to-end (Playwright) against the running stack
	cd apps/web && npx playwright test

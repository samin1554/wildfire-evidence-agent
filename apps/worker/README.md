# Worker: data pipeline

Python 3.12 · [uv](https://docs.astral.sh/uv/) · pytest · ruff. The worker is the only app that talks to data providers.

```bash
make worker-install     # once
make test-worker        # all offline tests: no keys, no network
make test-live          # real calls to real providers (keys from the repo's .env)
make lint-worker
```

## Get data in one line

```python
import asyncio
from inland_worker.data import get_evidence

result = asyncio.run(get_evidence("wfigs_current", bbox=(-124.5, 32.5, -114.1, 42.0)))
print(result.origin, result.freshness, len(result.items))
for item in result.items[:3]:
    print(item.properties["incident_name"], item.properties["gis_acres"], item.observed_at)
```

Run it offline on recorded data with `INLAND_DATA_MODE=fixture uv run python your_script.py`.
Every source and its `provider_id`: [docs/data-catalog.md](../../docs/data-catalog.md).

## Ask the agent

```bash
uv run python -m inland_worker ask "How badly did the 2024 Line Fire burn?" \
    --bbox=-117.185,34.092,-116.94,34.218 --date-range 2024-08-01/2024-10-31 --fixture
```
With `OPENROUTER_API_KEY` in `.env` it uses a free model to plan and explain ([ADR-007](../../docs/adr/ADR-007-llm-provider.md)); without it (or with `--no-llm`) it uses rule-based planning and wording. Either way every fact comes from the tools and is cited. In code: `await run_analysis(question, area, date_range, llm=..., data=...)` from `inland_worker.agent`.

## Layout

| Path | What | Owner |
|---|---|---|
| `src/inland_worker/contracts/` | Pydantic mirrors of `/contracts/*.schema.json` | Lead |
| `src/inland_worker/kit/` | Connector kit: config, HTTP client, fixtures, ArcGIS helpers, runner, shared test suite | Lead |
| `src/inland_worker/connectors/fire/{firms,wfigs}.py`, `weather/nws_forecast.py`, `imagery/earth_search_s2.py` | Reference connectors, one per pattern | Lead |
| `src/inland_worker/kit/imagery.py` | Satellite pixel reads for an area (STAC imagery pattern) | Lead |
| `research/` | Runnable research demos (e.g. `line_fire_2024.py`) | Lead / S6 / S8 |
| `src/inland_worker/agent/` | The agent: LangGraph workflow, approved tools, guardrails, LLM client, baseline verification | Lead (verify rules → S8) |
| `src/inland_worker/satellite/` | Satellite science (`burn.py` baseline by the lead) | S6 |
| `src/inland_worker/connectors/**` (others) | Connectors copied from a reference | S4, S5 |
| `src/inland_worker/data/` | `get_evidence()`: cache → live → stale snapshot → missing, plus tracing | Lead |
| `config/providers.yaml` | Every provider's endpoint, auth env var, limits, cache and schedule | Lead (PR review) |
| `tests/fixtures/<provider>/<case>/` | Recorded responses (`success`, `empty`, `malformed`, `extra_fields`) | Connector owner |
| `scripts/` | `new_connector.py`, `record_fixture.py`, `derive_fixtures.py` (use the `make` targets) | Lead |

## Adding a source

```bash
make new-connector NAME=calfire_historical GROUP=fire PATTERN=arcgis   # keyed | arcgis | follow_link | stac
# fill in the provider spec, add the providers.yaml block, then:
make record-fixture PROVIDER=calfire_historical CASE=success ARGS="--area sb_county_bbox"
make derive-fixtures PROVIDER=calfire_historical
make test-connector PROVIDER=calfire_historical
```

Full guide: [docs/connectors/connector-guide.md](../../docs/connectors/connector-guide.md).

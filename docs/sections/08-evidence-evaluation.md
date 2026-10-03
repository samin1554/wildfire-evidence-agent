# Section 8: Evidence verification and evaluation

**Stack:** Python 3.12 · Shapely / GeoPandas · pyproj · pytest
**Pair partner:** the lead (your rules plug into the agent's "Verify evidence" step).
**Read first:** [Start here](../guides/start-here.md) · [Agent workflow diagram](../diagrams/agent-workflow.html) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

> **Already built for you** ([details](../platform-status.md))
>
> - **The evidence format** (`contracts/evidence.schema.json`) and **real recorded evidence** from FIRMS, WFIGS, NWS and Sentinel-2 in `apps/worker/tests/fixtures/`. Read it offline with `get_evidence(...)` in fixture mode.
> - **A first evaluation case:** the [Line Fire demo](../research/line-fire-2024/README.md) compares our burn severity with the official BAER map (54.9% exact, 98.5% within one class); its `results.json` is ready to reuse.
>
> **Your part of Milestone 1:** Not on the critical path. Build S8-1 (confidence labeller) and S8-2 on fixture evidence; the agent will call your rules after Milestone 1.


## 1. Your job in plain English

You make the app **honest**. This is the part that makes this project different from a typical "AI chatbot with a map".

Before the app says anything, your rules check the evidence:
- Are the timestamps sensible? Is anything stale?
- Were there too many clouds for the satellite result to count?
- Do different sources **agree**? A satellite heat detection is only an *unverified detection* on its own. With a second independent source (e.g. burn severity from satellite imagery) it becomes a *corroborated signal*. If it matches an official perimeter, it's *officially reported*.
- If data is missing or contradictory, the answer must be *insufficient evidence*. Never "nothing happened".

You also build the **evaluation harness**: a set of real past fires with known facts that we test the whole system against, so we can measure things like "how often does it make a claim with no source?".

**Analogy:** you're the fact-checker at a newspaper. Reporters (the agent) can write whatever they like, but nothing gets printed until you've checked each claim against at least two sources, and you label anything you couldn't confirm.

![Agent workflow](../diagrams/agent-workflow.svg)

**Done looks like:** a function that takes evidence and returns one of the four confidence labels with reasons; a detection-vs-perimeter comparison; a set of historical test cases with metrics; and a report generator where every claim has a source.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/evidence/**` (verification rules) | `agent/**` (lead: calls your functions) |
| `apps/worker/src/inland_worker/reports/**` | `kit/**`, `data/**` (lead) |
| `apps/worker/eval/**` (historical cases + metrics) | `contracts/**` (lead) |
| `docs/evaluation.md` | connectors, satellite code |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Evidence type** | `satellite_detection`, `satellite_measurement`, `official_perimeter`, `official_hazard_zone`, `weather_observation`, `weather_forecast`, `air_quality_observation`, `deterministic_calculation`, `agent_inference`. |
| **Independent categories** | Evidence from genuinely different sources/methods. Two FIRMS points from the same satellite pass are **not** independent. |
| **Confidence vocabulary** | Unverified detection · Corroborated signal · Officially reported · Insufficient evidence. No percentages in the MVP. |
| **Agent inference** | Something the AI concluded. It **never** counts as corroboration. |
| **Spatial match** | Does a point fall inside (or near) a polygon? Use a buffer distance in metres, in a projected CRS. |
| **Temporal match** | Did two things happen within a sensible time window of each other? |
| **Claim ↔ source mapping** | Every sentence in the result links to the evidence items that support it. |
| **Evaluation metric** | A measurable score, e.g. unsupported-claim rate, or the difference between computed burn area and official perimeter area. |
| **Prompt injection** | Text inside provider data trying to instruct the AI ("ignore previous instructions…"). Your eval cases include these. |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Python, pytest | Core | [Python tutorial](https://docs.python.org/3/tutorial/) · [pytest](https://docs.pytest.org/en/stable/getting-started.html) | Parametrised tests for a function with 4 outcomes. |
| Shapely | Geometry operations | [shapely.readthedocs.io](https://shapely.readthedocs.io/en/stable/manual.html) | Point-in-polygon and `buffer()`. |
| GeoPandas | Tables of geometries | [geopandas.org](https://geopandas.org/en/stable/getting_started/introduction.html) | Load a GeoJSON perimeter and compute its area after `to_crs(...)`. |
| pyproj / CRS | Correct distances/areas | [pyproj docs](https://pyproj4.github.io/pyproj/stable/) | Compare a polygon's area in EPSG:4326 vs a metre-based CRS, and explain the difference. |
| The project spec | The rules you implement | Spec §14–15, §21–22 (ask the lead for the file) | Write the four confidence rules in plain English before any code. |

**Learn it with AI:**
```text
I need to decide whether a satellite fire detection point "matches" an official fire perimeter.
Explain why I must reproject from EPSG:4326 to a metre-based CRS before buffering, which CRS
suits Southern California, and what edge cases (edges, multipolygons, time windows) to test.
```

## 5. Set up your machine

Python 3.12+, [uv](https://docs.astral.sh/uv/), clone the repo, OpenCode. You work entirely on fixtures: no API keys needed.

## 6. Build it step by step

### S8-1 Confidence labeller
- **Goal:** evidence list in → label + human-readable reasons out.
- **Rules (from spec §15):**
  - Only satellite thermal detections → **Unverified detection**.
  - Detection + a compatible second *independent* category (e.g. a dNBR burn signal in the same place/time) → **Corroborated signal**.
  - Matched to an official perimeter or incident → **Officially reported**.
  - Missing, stale, incompatible or contradictory → **Insufficient evidence**.
  - `agent_inference` never counts toward any label.
- **AI prompt:**
  ```text
  Plan a pure function label_confidence(evidence: list[Evidence]) -> ConfidenceResult in
  apps/worker/src/inland_worker/evidence. Encode the four rules from docs/sections/08-evidence-evaluation.md
  as small, separately testable checks. Write parametrised pytest cases first, including
  edge cases: only inferences, stale snapshots, two items from the same source.
  ```
- **Done when:** every rule and edge case has a passing test, and the reasons read well to a non-expert.

### S8-2 Detection ↔ perimeter comparison
- **Goal:** `compare_detection_to_perimeter(detections, perimeters)` → which detections fall inside/near which perimeters, within which time window.
- **Steps:** reproject to a metre-based CRS; buffer points by a configurable distance; check the date window; output a `deterministic_calculation` with units and parameters.
- **Tests:** a point just inside/outside the buffer; multipolygons; no perimeters → an explicit "no official perimeter found" result.

### S8-3 Evaluation case set
- **Goal:** measure the system, not guess.
- **Steps:** pick 3–5 historical San Bernardino fires with the lead; for each, record expected facts (dates, official area) and fixture evidence; write metric functions from spec §22: claims with sources %, results with timestamps and limitations %, computed-vs-official burn area difference, tool-selection accuracy (with the lead).
- **Include adversarial cases:** provider text containing prompt-injection strings; missing satellite data; conflicting sources.

### S8-4 Report generator
- **Goal:** Markdown first (PDF later) following spec §23: short answer → what was observed → what was calculated → what official sources report → agreement/disagreement → uncertainty and limitations → sources.
- **Rules:** every factual sentence links to evidence IDs; inferences are labelled "Inference"; the limitations section is never empty when any evidence carries limitations.

**Common mistakes:** measuring distances in degrees; treating two items from one source as corroboration; letting an inference count; hiding limitations to make the report shorter.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Evidence schema + fixtures | Lead, S4, S5, S6 | Hand-made fixtures shaped like the connector guide example |
| Agent interface for verification | Lead | Pure functions with clear inputs/outputs |

| Others need from you | Who |
|---|---|
| Labels + reasons shown in the UI | S2 |
| Verification + reports inside the agent | Lead |
| Metrics for Milestone 5 | Whole team |

## 8. When you're stuck

Shapely/GeoPandas docs → OpenCode Plan mode (ask for edge cases, not code) → the lead (your pair) for rule interpretation → team chat with the fixture and the expected vs actual result.

## 9. Coming from the lead

- [x] A **baseline** confidence labeller in `apps/worker/src/inland_worker/agent/verify.py` (official perimeter → officially reported; two independent signals → corroborated; one → unverified; none → insufficient; burn signal = ≥10% of the area at moderate/high severity). Your S8-1 moves these rules into `evidence/` with proper tests, and the agent calls yours instead.

- [ ] The verification interface the agent will call (after Milestone 1; build your rules as plain, tested functions over `list[Evidence]` meanwhile)
- [ ] Chosen historical fires and expected facts. The 2024 Line Fire is the first ([research](../research/line-fire-2024/README.md))
- [ ] Buffer distance and time-window defaults
- [ ] How claims are represented in the agent output (for claim ↔ source mapping)

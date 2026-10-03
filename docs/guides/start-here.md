# Start here

Welcome. You're about to help build a real, multi-part software system, probably bigger than anything you've built before. That's fine: the project is set up so you can work on **one piece** and trust that the other pieces will fit, because everyone builds against the same written agreements (contracts) and the same fake data (fixtures).

Read this page first (~15 minutes), then open your section guide.

---

## 1. What we're building, in plain English

People want to ask questions like *"How did the vegetation change around the Line Fire?"* and get an answer they can trust: a map, some numbers, charts, and a clear list of where every fact came from and what we're **not** sure about.

The app is a small research assistant for San Bernardino County. It collects evidence from satellites and government agencies, does the math in ordinary code, and explains the results. It's **not** an emergency or evacuation tool, and it must never pretend to be one.

![Architecture](../diagrams/architecture.svg)

### Follow one question through the system

Think of a restaurant:

| Restaurant | Our system | Who builds it |
|---|---|---|
| The menu and dining room | **Web app**: the map, the question box, the results (React) | S1, S2 |
| The waiter takes the order and gives you a ticket number | **Public API**: checks the request, creates a job, returns a job ID immediately (Go) | S3 |
| The order ticket rail in the kitchen | **Redis Streams**: a queue of jobs waiting to be cooked | S7 (infra), lead (logic) |
| The chefs | **Worker**: fetches data, calculates, and writes up the answer (Python) | S4, S5, S6, S8, lead |
| The suppliers | **Providers**: NASA FIRMS, fire perimeter services, weather, Sentinel-2 satellite imagery | S4, S5, S6 connect to them |
| The pantry and recipe book | **PostGIS database + object storage**: saved jobs, evidence and images | S7 |
| The waiter calling out "your order is almost ready" | **Server-Sent Events (SSE)**: live progress pushed to the browser | S3 + S2 |

Step by step:
1. You draw an area on the map and type a question (S1, S2).
2. The browser sends it to the Go API, which checks it's inside the county, creates a job, puts it on the queue, and answers **straight away** with a job ID (S3).
3. The Python worker picks up the job, fetches data through the connector kit (S4, S5), runs satellite math (S6), checks the evidence (S8), and the agent writes an explanation (lead).
4. As each step finishes, progress flows back to the browser (S3 → S2).
5. The browser shows map layers, evidence cards, charts and limitations (S1, S2).

![Request lifecycle](../diagrams/request-lifecycle.svg)

---

## 2. Who builds what

![Team ownership](../diagrams/team-ownership.svg)

| Section | Your guide |
|---|---|
| S1 Map frontend | [01-map-frontend](../sections/01-map-frontend.md) |
| S2 Analysis UI | [02-analysis-ui](../sections/02-analysis-ui.md) |
| S3 Go API | [03-go-api](../sections/03-go-api.md) |
| S4 Fire data connectors | [04-fire-connectors](../sections/04-fire-connectors.md) |
| S5 Weather and environment connectors | [05-weather-connectors](../sections/05-weather-connectors.md) |
| S6 Satellite analysis | [06-satellite-analysis](../sections/06-satellite-analysis.md) |
| S7 Platform and data infrastructure | [07-platform-data-infra](../sections/07-platform-data-infra.md) |
| S8 Evidence and evaluation | [08-evidence-evaluation](../sections/08-evidence-evaluation.md) |
| Lead: contracts, connector kit, agent | [00-lead](../sections/00-lead.md) |

**Why you won't be blocked:** each section starts on fake data. Frontend work uses a mock API; connector work uses recorded responses. Nobody waits for anybody to "finish first".

---

## 3. How to use your section guide

Every guide has the same nine parts. Work through them in order:

1. **Your job in plain English:** read it until you could explain your piece to a friend.
2. **What you own:** the folders you're allowed to change.
3. **Key ideas:** the vocabulary you'll hear in reviews.
4. **Learn the stack:** week 0. Official docs + AI tutoring + a tiny practice exercise per tool.
5. **Set up your machine**
6. **Build it step by step:** your tickets, each with steps, an AI prompt, tests and a "done" check.
7. **How your work connects:** who you depend on, and who depends on you.
8. **When you're stuck**
9. **Coming from the lead:** details the lead will add as the core pieces land.

Also read:
- **[What's already built](../platform-status.md)**: the lead's data layer, how to use it, and what's expected of you.
- **[Milestone 1](../milestone-1.md)**: the team's current goal and your part in it.
- [Data catalog](../data-catalog.md): every data source, and how to get any of them in one line.
- [Learning with AI](learning-with-ai.md): how to use AI to actually *learn*, not just to paste code.
- [Coding with OpenCode](coding-with-opencode.md): the free coding agent we use, and the safe way to use it.
- [CONTRIBUTING](../../CONTRIBUTING.md): branches, pull requests, reviews.

---

## 4. A normal week

| When | What |
|---|---|
| Start of week | Pick 1–2 tickets from your guide. Say which in the team chat. |
| Daily | Short async update: *did / doing / stuck on*. |
| During the week | Branch → build in small steps → tests → open a PR early (draft PRs are welcome). |
| Mid-week | Pairing session with your pair partner (listed in your guide). |
| End of week | 2-minute demo of what you merged. It doesn't need to be pretty, just real. |

Tickets should take 1–2 days. If one is taking longer, split it and say so. That's a normal part of the job, not a failure.

---

## 5. "Done" means done

A change is finished when **all** of these are true (spec §25):

- It does what the ticket says (the acceptance criteria).
- Tests pass, including the "what if there's no data / the provider fails" cases.
- No secrets (API keys, passwords) anywhere in code, fixtures or logs.
- Data matches the shared contracts in `contracts/`.
- Anything a user sees shows **where it came from and when**, plus its limitations.
- Docs are updated.
- A teammate can run it and see it work.
- It was reviewed and merged.

The PR template has this checklist. Tick it honestly.

---

## 6. API keys: who needs one

Most of you **never need a key**. The repo ships real recorded data for every source, so tests and `INLAND_DATA_MODE=fixture` work offline.

| You want… | You need |
|---|---|
| To build the UI (S1, S2) | Nothing: use `contracts/examples/` and the mock API |
| To run tests or work on a connector | Nothing: recorded fixtures are in `apps/worker/tests/fixtures/` |
| Live WFIGS, CAL FIRE, NWS or county data | Nothing: these providers need no key |
| Live NASA FIRMS data | **Your own** free key from https://firms.modaps.eosdis.nasa.gov/api/map_key/ |
| The agent with a real AI model | **Your own** free OpenRouter key from https://openrouter.ai/keys (`OPENROUTER_API_KEY`); without it the agent still runs with its rule-based planner |
| Live CIMIS data (S5) | **Your own** free CIMIS app key |
| Satellite imagery (S6) | Nothing: Sentinel-2 comes from AWS open data with no account ([ADR-009](../adr/ADR-009-imagery-without-earth-engine.md)) |

How to add a key: copy `.env.example` to `.env` in the repo root and fill in the value, then run `make test-live`. `.env` is git-ignored.

**Never** commit a key, paste one into a chat or AI tool, or share a `.env` file. Each person uses their own key, so if one leaks, only that one is replaced (they're free). The deployed app uses the lead's keys, stored as platform secrets, never in files.

## 7. Three project rules that matter most

1. **Stay in your paths.** If you need a change in someone else's folder, ask them or open a PR and tag them.
2. **Contracts are the truth.** If the API or the evidence format needs to change, that goes through the lead as a `contract-change` PR. Never quietly "fix" a mismatch on your side.
3. **Never overclaim.** A satellite hotspot is *not* a confirmed fire; missing data is *not* proof that nothing happened. The whole product depends on being honest about uncertainty.

# Inland Resilience Agent: documentation

Find what you need by what you're trying to do.

## I'm new here
1. **[Start here](guides/start-here.md)**: what we're building, in plain English, and how the team works.
2. **[What's already built](platform-status.md)**: what the lead has delivered, how to use it, and what's expected of you.
3. **[Milestone 1](milestone-1.md)**: the team's current goal, and who builds which piece.
4. **Your section guide** ([all sections](sections/README.md)): your job, what you own, how to learn the stack, and your tickets.
5. [Learning with AI](guides/learning-with-ai.md) · [Coding with OpenCode](guides/coding-with-opencode.md) · [Contributing](../CONTRIBUTING.md)

## I need data
- **[Data catalog](data-catalog.md)**: every source, its `provider_id`, freshness, owner, and how to get it in one line.
- **[Connector guide](connectors/connector-guide.md)**: how to add a source (copy a reference connector) and how to read data.
- [Provider spec template](connectors/provider-spec-template.md) · [Provider specs](connectors/providers/)

## I need the contracts
The shared formats live in [`contracts/`](../contracts/): the API spec (`openapi.yaml`), the evidence, job and job-event schemas, and real examples in `contracts/examples/`. How they're used: [What's already built § Contracts](platform-status.md#1-contracts-v0-the-shared-language).

## I want to know why something is the way it is
- **[Architecture decisions (ADRs)](adr/README.md)**
- **Deviations from the spec:** satellite imagery uses Earth Search + official BAER/MTBS maps instead of Google Earth Engine ([ADR-009](adr/ADR-009-imagery-without-earth-engine.md)); CAL FIRE historical perimeters use `California_Historic_Fire_Perimeters` because the spec's URL only holds 2025 fires.
- **Research:** [Line Fire 2024 burn-severity proof](research/line-fire-2024/README.md)

Source spec: `Inland_Resilience_Agent_Project_Spec.md` (Sep 23, 2026).

## Diagrams

The `.svg` files render here on GitHub. Open the matching `.html` file in a browser for exact fonts and extra notes.

### Architecture: three apps, one boundary each
![Architecture](diagrams/architecture.svg)

### Request lifecycle: the API answers first, the worker does the work
![Request lifecycle](diagrams/request-lifecycle.svg)

### Agent workflow: fixed tools, evidence before answers
![Agent workflow](diagrams/agent-workflow.svg)

### Database schema
![Database schema](diagrams/database-schema.svg)

### Cache and snapshot tables (ADR-006)
![Cache schema](diagrams/cache-schema.svg)

### Job state machine
![Job state machine](diagrams/job-state-machine.svg)

### Ingestion pipeline: one kit in, one API out
![Ingestion pipeline](diagrams/ingestion-pipeline.svg)

### Team ownership
![Team ownership](diagrams/team-ownership.svg)

# ADR-007: LLM provider for the agent

## Status
Accepted (Sep 24, 2026): **OpenRouter free models**, behind a provider-neutral interface.

## Context
The spec uses LangGraph (§5, §14) but names no model provider. The model only **plans and explains**; code does every calculation (§14). The team is students, so cost matters.

## Decision
- **OpenRouter** (`https://openrouter.ai/api/v1`, OpenAI-compatible) with **free models**. Default list, tried in order through OpenRouter's `models` fallback: `qwen/qwen3.8-27b:free`, `google/gemma-4-31b-it:free`, `nex-agi/nex-n2.5-pro:free` (all free with tool support on Sep 24, 2026). Override with `AGENT_MODELS` in `.env`, because free models rotate.
- Calls go through the **connector kit** like any provider (`providers.yaml` → `openrouter`, `kind: llm`): allowlisted host, key from `OPENROUTER_API_KEY` in `.env`, redaction, bounded retries.
- **Plans are JSON, not native tool calls.** Tool calling is unreliable on free models; a JSON plan is validated against the approved-tool registry and argument models. Anything invalid falls back to a rule-based plan (ADR-010).
- **Two model calls per analysis** (plan + explain), to stay inside free limits.
- Tests use `ScriptedLLM`: no key, no network, no cost.

## Limits and risks
- Free tier: **20 requests/min, 50/day** without purchased credits (1,000/day with ≥ $10 of credits). That's ~25 analyses/day at 2 calls each. Each teammate who runs live uses their own key.
- Free models can change or disappear, and some providers may log prompts. Prompts contain only the user's question, the area/dates and public data summaries: never keys or personal data.
- Output quality varies by model. The validation, citation checks and rule-based fallbacks keep results correct even when the model is weak or unavailable.

## Alternatives considered
Anthropic Claude, OpenAI (paid; stronger tool use), Google Gemini free tier, Groq free tier. Switching is a config change (`OpenRouterLLM` implements the small `LLM` protocol; another client can too).

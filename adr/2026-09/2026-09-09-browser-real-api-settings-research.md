# Browser Real API Settings Research

## Scope

User wants real AI API configuration to be available directly in the web UI, including an explicit choice for whether to use real API instead of demo/fixture behavior.

This research covers the settings page, browser storage, request headers, runtime backend settings, model provider, web search provider, capabilities endpoint, and related tests.

## ADR Lookup

Related records found:

- `adr/2026-08/2026-08-29-choice-agent-v1-borrowed-ideas-todo.md`: requires UI to distinguish rule mode, model mode, demo data, and real data.
- `adr/2026-08/2026-08-29-diet-agent-python-migration-plan.md`: defines `providers/` as the replaceable model/external capability boundary and requires traces not to record secrets.
- `adr/2026-09/2026-09-04-generic-decision-external-benchmark-research.md`: defines real search as source-backed retrieval, not fixture or unconstrained model text.
- `adr/2026-09/2026-09-04-generic-decision-evidence-workbench-plan.md`: implemented `OpenAIWebSearchProvider`, but noted live credentials were not configured or end-to-end verified.
- `adr/2026-09/2026-09-06-evaluation-regression-dataset-research.md`: says live model/search runs should stay separate from stable regression baselines.

Conclusion: this is a focused configuration usability change over existing providers, so a new small research/plan pair is clearer than appending to older large plans.

## Current Behavior

- `src/choice_agent/static/assets/js/api.js` already stores `choiceAgentModelSettings` in `localStorage`.
- The frontend already sends model settings through `X-Choice-Agent-Model-*` headers.
- `src/choice_agent/api/routes.py` already has `runtime_model_from_headers()` and `get_runtime_model()` to create per-request model settings.
- `src/choice_agent/providers/model.py` calls OpenAI-compatible `/chat/completions` when `enable_llm` and `model_api_key` are present.
- `src/choice_agent/providers/search.py` calls OpenAI Responses `/responses` with `web_search` when a search API key is present.
- `src/choice_agent/orchestration/generic.py` constructs `OpenAIWebSearchProvider` from `settings.search_*`.
- `/api/v1/search/capabilities` currently only checks server-side `settings.search_api_key`.
- The home realtime search switch only uses web mode when `webSearchConfigured` is true.

## Gap

The web UI can configure real model calls, but cannot configure real Web Search. Because capabilities do not read browser-provided search settings, the home page still treats realtime search as unavailable unless the server environment has `CHOICE_AGENT_SEARCH_API_KEY`.

## Reusable Pieces

- Existing `Settings` already has all search fields.
- Existing browser settings storage can be extended compatibly.
- Existing runtime header pattern can be reused for search.
- Existing `SearchCapabilitiesResponse` can continue to hide provider details and secrets.

## Risks

- API keys in `localStorage` are suitable only for local/trusted browsers.
- Runtime headers must not be written to Trace, DecisionState, logs, or response bodies.
- Search capability responses must expose only configured/unconfigured state.
- Live search failure should remain explicit instead of silently falling back to fixture.

## Constraints

- Do not add dependencies.
- Do not persist secrets server-side.
- Do not change request bodies or response schemas.
- Preserve fixture behavior when real API is disabled or missing a key.
# Candidate Search Productization Plan

Date: 2026-09-05

## Goal

Make existing Candidate Search a visible product capability for public non-demo use. A user entering a request such as `预算 7000 的轻便通勤电脑` should be able to trigger real candidate search when the backend is configured, see the search process progress, and understand which results came from web search, fixture/demo data, manual input, or local data.

This plan does not add another Candidate Agent. It productizes the existing providers and leaves deeper search quality work for follow-up phases.

## Success Criteria

- Formal Shopping and Travel flows expose a `使用实时信息寻找候选` control.
- Demo examples continue to use deterministic fixture data.
- Non-demo creation can request real search without requiring hidden context edits.
- If web search is unavailable, the UI makes that clear before or during submission without exposing sensitive configuration.
- Users can see staged progress while the request runs.
- Progress counts are truthful: candidates found, excluded by user/manual state, excluded by hard constraints, excluded due to missing required data, and remaining candidates are not conflated.
- Existing synchronous JSON endpoints keep working.
- Existing idempotency, revision conflict, and receipt replay behavior remain intact.
- Evidence/source labels do not overclaim freshness, stock, price accuracy, or multi-source verification.

## Design

### Search Mode Exposure

Add a search capability endpoint:

`GET /api/v1/search/capabilities`

Response shape:

```json
{
  "supportedDomains": ["shopping", "travel"],
  "webSearchConfigured": true,
  "defaultSearchMode": "fixture"
}
```

The endpoint is read-only and must not expose API keys, raw provider names, internal allowlists, account details, or provider error text. `webSearchConfigured` means the service has enough local configuration to attempt web search; it is not a health check.

In the frontend:

- Demo entry points continue sending `searchMode: "fixture"` and `demoMode: true`.
- Formal Shopping and Travel flows show a toggle labeled `使用实时信息寻找候选`.
- When enabled, creation sends `searchMode: "web"`.
- When disabled, creation sends `searchMode: "fixture"` and labels the result as demo/reference data.
- If capabilities report web search unavailable, disable the toggle and show a concise unavailable state.

Do not change the backend global default from `fixture` in this phase. This preserves existing tests, local development, and unnamed clients. The visible product flow opts into web search explicitly.

### Visible Progress

Add streaming POST endpoints beside the existing JSON endpoints:

- `POST /api/v1/decisions/stream`
- `POST /api/v1/decisions/{decision_id}/messages/stream`
- `POST /api/v1/decisions/{decision_id}/commands/stream`

Use newline-delimited JSON events so the frontend can keep the same POST body and headers. Existing JSON endpoints remain unchanged.

Event shape:

```json
{
  "requestId": "string",
  "commandId": "string or null",
  "sequence": 1,
  "type": "progress",
  "stage": "searching_candidates",
  "message": "正在寻找候选",
  "counts": {
    "found": 6,
    "userExcluded": 0,
    "hardConstraintExcluded": 2,
    "missingDataExcluded": 0,
    "remaining": 4
  },
  "sourceMode": "web",
  "warning": null
}
```

Terminal success event:

```json
{
  "requestId": "string",
  "sequence": 8,
  "type": "final",
  "response": {}
}
```

Terminal error event:

```json
{
  "requestId": "string",
  "sequence": 8,
  "type": "error",
  "error": {
    "code": "search_provider_unavailable",
    "message": "实时搜索暂不可用"
  }
}
```

Progress is request telemetry. It must not increment decision revision and should not be persisted into the durable decision state.

Initial event sequence for search-backed creation:

1. `正在理解你的需求`
2. `正在寻找候选`
3. `找到 N 个候选`
4. `正在校验证据来源`
5. `基于硬约束排除 X 个`
6. `正在比较剩余 Y 个`
7. final response

For clarification-only responses, do not invent candidate search progress. For rerank-only commands, show ranking/comparison progress without search events.

### Backend Progress Integration

Introduce a lightweight progress sink passed through orchestration/domain execution. The default sink is a no-op so existing JSON endpoints keep using the same logic.

The streaming adapter should:

- create a bounded queue;
- run the existing orchestration work in a worker with its own SQLAlchemy session;
- emit ordered NDJSON events;
- commit before emitting the final response;
- emit structured errors for validation, revision conflicts, search provider failures, and unexpected failures;
- clean up on client disconnect.

The worker should not reuse FastAPI's request-scoped database session. This avoids cross-thread session bugs.

Provider calls cannot always be interrupted immediately after a disconnect. They remain bounded by the existing provider timeout. Cancellation should stop future stage work and avoid emitting final success after a disconnected request.

### Count Classification

Update ranking or the ranking result metadata so it can distinguish:

- `userExcluded`;
- `hardConstraintExcluded`;
- `missingDataExcluded`;
- `remaining`;
- total candidates considered after merge/deduplication.

The UI copy should use these categories directly. If a candidate is excluded due to missing data required by a hard constraint, show it as missing required data rather than a hard-constraint failure.

### Frontend Streaming Client

Add streaming helpers to `api.js` that:

- call the new streaming endpoints with the same request payloads;
- parse UTF-8 NDJSON chunks;
- handle split lines and final tail data;
- surface malformed events and HTTP errors as terminal stream errors;
- require a `final` event before treating the operation as successful;
- preserve command IDs and retry semantics;
- abort the reader/controller on route changes or user changes.

Update `conversation.js` and `app.js` so the UI can render progress messages while preserving the existing generation, user, and route guards.

If a stream fails before final success, keep the request visible as failed and allow a manual retry. Do not automatically repeat costly web search in the background.

### Source Presentation

Normalize source labels:

- `web`: realtime web search;
- `fixture`: demo/reference data;
- `manual`: user-entered candidate;
- `database`: local database candidate.

For web sources, show concise cautionary copy such as `来源已校验，价格与库存需核实`. Avoid wording that implies all facts are fresh or independently verified.

### Search Quality Follow-Up

Keep deeper quality improvements as later Research/Plan work:

- query planning by domain and constraints;
- multi-source evidence validation and conflict handling;
- freshness and publish-date judgment;
- price/stock recency and stale-data detection;
- error-classified retry/backoff;
- candidate coverage metrics across brand, price band, and use case;
- regression fixtures for search result quality.

## Affected Files

- `src/choice_agent/api/routes.py`: add capability and streaming endpoints while preserving current JSON endpoints.
- `src/choice_agent/api/decision_stream.py`: add streaming adapter, event serialization, and worker/session lifecycle.
- `src/choice_agent/schemas.py`: add capability and progress event schemas.
- `src/choice_agent/agents/base.py`: add optional progress sink to agent context or stage execution input.
- `src/choice_agent/agents/stages.py`: emit stage-level progress at safe boundaries.
- `src/choice_agent/orchestration/generic.py`: pass progress sink through create/message/command flows and preserve idempotency semantics.
- `src/choice_agent/domains/comparison.py`: emit candidate search, evidence validation, and ranking progress; report source mode and candidate counts.
- `src/choice_agent/decision/ranking.py`: expose classified exclusion counts.
- `src/choice_agent/static/assets/js/api.js`: add NDJSON streaming client helpers.
- `src/choice_agent/static/assets/js/app.js`: add non-demo realtime search toggle and wire create flow to streaming.
- `src/choice_agent/static/assets/js/conversation.js`: render progress events and source labels.
- `src/choice_agent/static/assets/css/app.css`: style the toggle and progress indicator using existing UI conventions.
- `tests/test_candidate_search_productization.py`: add backend API, streaming, capability, and count classification tests.
- `tests/test_unified_decision.py`: extend existing provider mode/idempotency coverage if needed.
- `README.md`, `docs/deploy.md`, `.env.example`: document enabling real search.
- `CHANGELOG.md`: record the user-visible product change.

## Compatibility

Existing JSON endpoints remain available and should keep their response shape. Existing clients that omit `searchMode` continue to follow the configured backend default.

New streaming endpoints are additive. If the frontend detects streaming failure or unsupported behavior, it can fall back to existing JSON calls only when doing so will not duplicate a request with a different idempotency key.

The default backend `search_provider` remains `fixture` in this phase.

## Risks And Mitigations

- Streaming plus database transactions can create session lifecycle bugs. Mitigation: worker creates and closes its own session.
- Progress can mislead users if counts are approximate. Mitigation: emit counts only from actual merged/ranked candidate data and classify exclusions explicitly.
- Web search can fail or be unavailable in deployed environments. Mitigation: capability endpoint, clear UI disabled state, and explicit terminal error.
- Streaming disconnects can leave provider calls running until timeout. Mitigation: bounded provider timeout and cancellation before subsequent stages.
- Evidence wording can overstate trust. Mitigation: label source eligibility separately from price/stock freshness.
- `auto` fallback can hide fixture usage. Mitigation: product UI uses explicit `web` when realtime search is toggled on and labels source mode in results.

## Verification Plan

Run:

- `git diff --check`
- `python -m compileall -q src`
- `python -m pytest`
- `node --check src/choice_agent/static/assets/js/api.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- `node --check src/choice_agent/static/assets/js/conversation.js`

Backend behavior to verify:

- capability endpoint when search is configured and unconfigured;
- fixture mode remains deterministic;
- web mode calls the web provider when configured;
- web mode returns structured error when unconfigured;
- auto mode keeps existing fallback semantics;
- progress event order for create/message/command;
- final event emitted only after committed response;
- revision conflict and command idempotency behavior preserved;
- count classification for found, hard-constraint exclusion, missing-data exclusion, user exclusion, and remaining.

Frontend behavior to verify:

- Demo examples continue fixture mode;
- Formal Shopping and Travel can enable realtime search;
- disabled toggle state when backend is unconfigured;
- progress messages render in order;
- stream errors and manual retry state are visible;
- route/user/generation guards prevent stale UI updates;
- source labels distinguish web, fixture, manual, and database;
- mobile and desktop layouts do not overlap.

If no real search key is available locally, use mocked provider tests and explicitly record that live web search was not verified in the final implementation note.

## Todo

- [ ] Add search capability schema and endpoint.
- [ ] Add request-level progress event schemas and no-op progress sink.
- [ ] Add additive NDJSON streaming endpoints with isolated database session lifecycle.
- [ ] Emit progress from orchestration/domain/stage boundaries.
- [ ] Expose classified ranking exclusion counts.
- [ ] Add formal-flow realtime search toggle and capability-driven disabled state.
- [ ] Add frontend streaming client and progress rendering.
- [ ] Normalize source labels and web-source caution copy.
- [ ] Add backend tests for capabilities, provider modes, streaming, idempotency, and count classification.
- [ ] Add frontend syntax checks and manual UI verification.
- [ ] Update README/deploy/env docs and CHANGELOG.
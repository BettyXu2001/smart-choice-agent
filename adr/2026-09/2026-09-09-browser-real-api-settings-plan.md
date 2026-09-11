# Browser Real API Settings Plan

## Goal And Success Criteria

Goal: let users choose from the web UI whether to use real API, and configure both model calls and realtime Web Search without editing `.env`.

Success criteria:

- `#/settings` clearly exposes a real API on/off choice.
- Users can configure model API key, base URL, main model, and light model.
- Users can configure realtime search API key, base URL, and search model.
- Normal and streaming frontend requests send enabled real API settings through headers.
- `/api/v1/search/capabilities` recognizes browser-provided search settings so the home realtime search toggle becomes available.
- Disabled or missing-key states still use demo/fixture behavior.
- Secrets are not returned, persisted server-side, or written into traces.

## Design

Use per-browser runtime configuration.

- Keep local browser storage; do not save secrets in the backend or database.
- Extend the existing `choiceAgentModelSettings` object instead of creating a second settings store.
- Keep existing model headers unchanged.
- Add search headers that mirror the model header pattern.
- Extend backend runtime settings construction so one dependency returns temporary settings plus model provider.
- Make search capabilities use the same runtime settings dependency.

## Headers

Existing model headers remain:

- `X-Choice-Agent-Model-Enabled`
- `X-Choice-Agent-Model-Api-Key`
- `X-Choice-Agent-Model-Base-Url`
- `X-Choice-Agent-Main-Model`
- `X-Choice-Agent-Light-Model`

New search headers:

- `X-Choice-Agent-Search-Enabled`
- `X-Choice-Agent-Search-Api-Key`
- `X-Choice-Agent-Search-Base-Url`
- `X-Choice-Agent-Search-Model`

When search is enabled and has a key, runtime settings should set `search_provider="openai"`, `search_api_key` from the header, and use header base URL/model when provided.

## Affected Files

- `src/choice_agent/api/routes.py`
  - Add runtime search header parsing.
  - Preserve existing `runtime_model_from_headers()` compatibility or update tests with the new signature intentionally.
  - Make `search_capabilities()` use runtime settings.

- `src/choice_agent/static/assets/js/api.js`
  - Extend settings defaults and normalization with search fields.
  - Attach search headers when enabled.
  - Keep old stored settings compatible.

- `src/choice_agent/static/assets/js/app.js`
  - Rename settings UI from browser model config to real API settings.
  - Add real API and realtime search switches.
  - Save/clear/display search fields and status.

- `tests/test_runtime_model_settings.py`
  - Add runtime search header tests.
  - Keep secret non-persistence coverage.

- `tests/test_candidate_search_productization.py`
  - Add capability test for browser search settings.

- `CHANGELOG.md`
  - Record web real API settings and browser search configuration.

## Compatibility

- No request body changes.
- No response schema changes.
- `.env` remains supported for deployments.
- Existing browser model settings remain readable.
- New headers are optional and inert when disabled or missing a key.

## Risks

- Browser `localStorage` is not appropriate for shared devices. The UI must state this plainly.
- Live Web Search can fail due to network, model access, or key permissions. Existing explicit error handling remains preferable to silent fixture fallback after the user asked for real API.
- Search capability responses must not reveal keys, base URLs, or provider internals.

## Verification

- `python -m compileall -q src`
- `python -m pytest tests/test_runtime_model_settings.py tests/test_candidate_search_productization.py`
- `node --check src/choice_agent/static/assets/js/api.js`
- `node --check src/choice_agent/static/assets/js/app.js`
- Local capabilities checks:
  - without headers: `webSearchConfigured:false`, default fixture behavior.
  - with enabled search headers and fake key: `webSearchConfigured:true`, `defaultSearchMode:"web"`.
- `scripts/verify_main_flow.py` still passes.

Live API end-to-end verification will require a real key from the user. Without a key, only wiring and local behavior can be verified.

## Todo

- [x] Extend backend runtime header parsing for search settings.
- [x] Make search capabilities read runtime search settings.
- [x] Extend frontend settings storage and header injection.
- [x] Update settings UI with real API and realtime search controls.
- [x] Add/update tests.
- [x] Update `CHANGELOG.md`.
- [x] Run compile, tests, JS checks, and local capability verification.
# Candidate Search Productization Research

Date: 2026-09-05

## Scope

This research covers the next phase for Candidate Search productization. The goal is to make the existing real search capability visible and usable in the public product flow, while preserving the current Fixture, Manual, and Web Search providers and the existing Search -> Candidate -> Evidence -> Evidence Validation -> Ranking chain.

This is a large change because it touches the main user flow, API behavior, frontend interaction, provider selection, and user-visible progress. Per `AGENTS.md`, implementation must wait until a Plan is reviewed and explicitly approved.

## Related ADR Lookup

Relevant existing records:

- `adr/2026-09/2026-09-04-generic-decision-evidence-workbench-plan.md`: documents the current generic evidence workbench direction, candidate/evidence contracts, and notes that streaming/progress was intentionally deferred.
- `adr/2026-09/2026-09-04-general-conversation-panel-research.md` and `adr/2026-09/2026-09-04-general-conversation-panel-plan.md`: cover field collection, candidate display, references, and conversation panel behavior.
- `adr/2026-09/2026-09-03-conversation-decision-assistance-research.md` and matching plan: cover the original public demo flow, fixture behavior, decision receipts, and basic conversation loop.
- `adr/2026-09/2026-09-04-generic-decision-external-benchmark-research.md`: contains earlier observations about search quality, events, and coverage gaps.

These files are related, but the current request is specifically about productizing the already implemented Candidate Search capability. Updating the older ADRs would mix a new productization phase into completed or broader historical decisions, so this work should use a new Research and Plan pair.

## Core Files And Responsibilities

- `src/choice_agent/providers/search.py`: implements `OpenAIWebSearchProvider`, query construction, source allowlist behavior, structured candidate extraction, retry loop, timeout, and conversion from web results to candidates.
- `src/choice_agent/providers/candidates.py`: defines Fixture, Manual, Composite, and Diet database candidate providers.
- `src/choice_agent/domains/comparison.py`: drives provider selection, candidate search, evidence validation, persistence of search runs/sources/candidate pool, and ranking.
- `src/choice_agent/decision/evidence.py`: validates evidence URLs and citation/source allowlists. It verifies source eligibility, not full factual correctness or freshness.
- `src/choice_agent/decision/ranking.py`: applies user exclusions, hard constraints, missing-data exclusion policy, and scoring.
- `src/choice_agent/agents/stages.py`: coordinates staged execution. Candidate search and ranking are currently grouped under `CandidateAgent`.
- `src/choice_agent/orchestration/generic.py`: creates the web provider, normalizes `searchMode`, executes create/message/command flows, and stores decision state.
- `src/choice_agent/config.py`: defines `search_provider`, `search_api_key`, source allowlists, retry/query limits, and timeouts.
- `src/choice_agent/api/routes.py`: exposes synchronous JSON APIs for decision create/message/command/state.
- `src/choice_agent/schemas.py`: defines request/response schemas.
- `src/choice_agent/static/assets/js/api.js`: wraps frontend API calls and currently reads whole JSON responses.
- `src/choice_agent/static/assets/js/app.js`: owns the main UI flow. Demo creation explicitly passes `searchMode: "fixture"` and `demoMode: true`.
- `src/choice_agent/static/assets/js/conversation.js`: controls conversation state, route checks, retries, decision panel updates, and source display.

## Current Calling Chain

Decision creation and follow-up currently run as synchronous JSON calls:

1. Frontend calls `DecisionApi.startGeneral(...)`, `sendMessage(...)`, or `runCommand(...)`.
2. `api/routes.py` opens a request-scoped database session and calls `GenericDecisionOrchestrator`.
3. `orchestration/generic.py` normalizes request context, creates provider dependencies, and delegates to the selected domain plugin.
4. `domains/comparison.py` selects the candidate provider based on `searchMode`.
5. The domain runs candidate search, validates evidence, persists search metadata/candidate pool, and ranks candidates.
6. The API returns one final JSON response after all work completes.
7. The frontend navigates or rerenders only after the final response arrives.

The chain is complete technically, but the user cannot see the intermediate work. In the public Demo flow, real web search is explicitly bypassed.

## Current Provider Behavior

`searchMode` currently accepts `fixture`, `web`, and `auto`:

- `fixture`: always uses deterministic fixture candidates.
- `web`: requires a configured web provider. If unavailable or failed, it surfaces an error.
- `auto`: uses web search when the provider is configured, and falls back to fixture with a warning on provider failure.

`orchestration/generic.py` defaults missing context from `Settings.search_provider`. The configured default is currently `fixture`, preserving deterministic local/demo behavior.

The Demo entry point in `app.js` explicitly sets `searchMode: "fixture"` and `demoMode: true`, so public examples remain fixture-backed even if web search is configured.

## Current Search Capability

`OpenAIWebSearchProvider` already has several reusable product foundations:

- It sends the user's goal, current collected fields, latest message, criteria, and constraints to web search.
- It supports source allowlists.
- It asks for structured candidate output.
- It carries evidence URLs/citations into candidate attributes.
- It retries the provider call twice in the current implementation.
- It has bounded query count and timeout settings.

The capability is present, but is not exposed as an explicit user choice and does not have user-visible progress.

## Evidence And Ranking Constraints

Evidence validation currently checks that candidate evidence URLs are allowed and attributable. A `verified` evidence entry should be presented as source-eligible, not as proof that every claim is current, independently corroborated, or price/stock accurate.

Ranking currently filters candidates for:

- user exclusions;
- hard constraints;
- missing data when the hard-constraint missing policy is `EXCLUDE`;
- candidate state/eligibility.

Current reason labels can collapse true hard constraint failure and missing required data into similar user-facing wording. A product progress line such as `based on hard constraints excluded 2` should only count actual hard-constraint failures. Missing-data exclusions should be counted separately or described with more careful wording.

## Current UX Gaps

The current public behavior does not make real search a visible product feature:

- Demo examples force fixture mode.
- Formal Shopping/Travel creation does not expose a real-search toggle.
- Missing search configuration is not surfaced before submission.
- The frontend receives only a final response, so it cannot show progress such as understanding requirements, finding candidates, validation, filtering, and ranking.
- Source labels distinguish fixture/manual in some places, but web-backed results need clearer source wording and caution around price/stock freshness.

## API And Runtime Constraints

The current API endpoints are synchronous JSON endpoints. They should remain available for compatibility. Adding progress should avoid breaking existing callers.

Because API routes use scoped SQLAlchemy sessions, long-running streamed work must not reuse a request-scoped session across worker threads. Any worker used for streaming needs its own session lifecycle.

Existing command flows use `commandId` and `expectedRevision` for idempotency and conflict handling. Streaming must preserve those semantics and only emit a final success event after the transaction has committed.

Progress events should not mutate decision revision or persisted decision state. They are request-level UI telemetry, separate from the durable decision state and trace.

## Product Constraints

The requested next phase should productize existing Candidate Search, not add a new Candidate Agent. The useful near-term product work is:

- expose real search to users;
- show a trustworthy process;
- label sources and search mode clearly;
- keep deterministic demo behavior available;
- lay groundwork for later search quality improvements.

Search quality improvements such as query planning, multi-source verification, freshness judgment, retry classification, and coverage measurement should be planned as later work unless they are required to make the current exposed search safe and understandable.

## Open Questions For Plan

- Should the formal non-demo default be explicit `web` or `auto`? `web` makes failures clear; `auto` avoids dead ends but may hide fallback to fixtures unless the UI labels it clearly.
- Should progress be implemented through streaming POST responses, polling persisted events, or a lighter UI-only staged progress model?
- How should counts be computed so the UI can truthfully say found/excluded/remaining without overclaiming hard constraint exclusions?
- How should unavailable search configuration be exposed without leaking keys, provider details, or internal errors?
- How much search quality work belongs in this phase versus a follow-up phase?
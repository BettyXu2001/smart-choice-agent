# User Profile Decision Injection Research

## Demand And Scope

Goal: make the existing User Profile participate when creating a new Decision, without building a full Memory System. The profile must be domain-filtered, treated as soft preference or assumption, preserve `user_profile` source metadata, and never auto-update the long-term profile from Decision edits.

Out of scope: historical learning, Memory Agent, Vector DB, embedding retrieval, and automatic long-term preference updates.

## Related ADR

- `2026-09-05-consumer-navigation-decision-history-plan.md`: introduced `UserProfileRecord`, `UserProfile`, `/api/v1/profile`, and `#/profile`; it explicitly kept profile display-only in the first version.
- `2026-09-04-general-conversation-panel-research.md`: documented the generic Decision create flow and `conversationFields`.
- `2026-09-05-decision-trace-observability-research.md`: documented Trace timeline and snapshot behavior.

## Core Files And Responsibilities

- `src/choice_agent/schemas.py`: defines `UserProfile`, `DecisionState`, `Constraint`, `Assumption`, and field source models.
- `src/choice_agent/repositories/profile_repository.py`: reads and saves one profile per user, returning an empty `UserProfile` when none exists.
- `src/choice_agent/orchestration/generic.py`: creates generic decisions, resolves domains, builds `DecisionState`, runs the unified stage lifecycle, persists responses, and owns idempotency receipts.
- `src/choice_agent/decision/conversation.py`: owns non-diet `conversationFields`, `patch_fields()`, and `sync_dependencies()`; only confirmed fields become hard constraints.
- `src/choice_agent/domains/diet/state.py`: owns diet slot state and `dietFieldState` source/confirmation metadata.
- `src/choice_agent/domains/comparison.py`: common profile for shopping/travel/generic; its understanding stage merges criteria and previously reset assumptions.
- `src/choice_agent/services/trace.py`: builds safe Trace snapshots with a domain-state whitelist.
- `src/choice_agent/static/assets/js/conversation.js`: renders diet/general decision panels and sends confirm/update commands.

## Current Flow

New generic Decision:

Home / API -> `create_decision()` -> `GenericDecisionOrchestrator.create()` -> `DomainRegistry.resolve()` -> construct `DecisionState` -> `_run()` -> `StageRunner.run()` -> profile stages -> persist -> public response.

Existing Profile:

`GET/PUT /api/v1/profile` -> `ProfileRepository` -> `user_profiles.profile_json`. The profile is not used by Decision creation before this change.

## Existing Reusable Mechanisms

- `Constraint.source` and `Assumption.source` can preserve source labels such as `user_profile`.
- `conversationFields` already supports `source`, `confirmed`, and `cleared`, so profile values can be shown as pending and accepted/changed/ignored through existing commands.
- `sync_dependencies()` only turns confirmed fields into hard constraints.
- Ranking hard filtering only evaluates `Constraint.kind == hard`.
- Frontend already has `confirm_fields` and `update_fields` commands for current Decision-only edits.

## Constraints And Risks

- Profile must be applied after domain resolution so domain filtering is real.
- Profile should not override current user input; current turn parsing must remain higher priority.
- Diet slots affect scoring, so profile-sourced diet values must remain unconfirmed and be replaceable by explicit current input.
- `ComparisonProfile.understand()` reset assumptions; it must preserve profile assumptions.
- Trace snapshots only include whitelisted `domain_state` keys, so `profileSuggestions` must be whitelisted.
- Current Decision edits must not call `ProfileRepository.save()`.

## Open Decisions Resolved In Plan

- Add a small local injection helper instead of a Memory System.
- Store profile effects as `Assumption(source="user_profile")`, `domainState.profileSuggestions`, and unconfirmed field state.
- Use existing current-Decision commands for adopt/modify/ignore.
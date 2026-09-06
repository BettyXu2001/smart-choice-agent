# User Profile Decision Injection Plan

## Goal And Success Criteria

- New Decision creation reads the current user's `UserProfile`.
- Only domain-related profile information is injected.
- Profile data remains a soft preference or assumption and does not automatically become a hard constraint.
- Priority is current user input > current Decision state > User Profile > system default.
- Conflicts in the current turn resolve in favor of the current user input.
- `user_profile` source metadata is visible in Decision State, Trace, and frontend UI.
- The frontend minimally shows "来自我的资料" and lets the user adopt, modify, or ignore the value for this Decision.
- Current Decision edits do not update the long-term profile.

## Design

Add `src/choice_agent/decision/profile_injection.py` with a bounded mapping from `UserProfile` to current-Decision suggestions.

Domain mapping:

- `shopping`: use `budget_habit` and `notes` as unconfirmed `priority` plus an assumption.
- `travel`: use `budget_habit`, `preferred_cities`, and `notes` as unconfirmed `priority` plus an assumption.
- `generic`: use `budget_habit` and `notes` as unconfirmed `priority` plus an assumption.
- `diet`: use `diet_preferences` as unconfirmed `taste` plus an assumption; notes remain assumption-only.

The helper writes:

- `decision.assumptions[]` with `source="user_profile"` and confidence below 1.
- `decision.domain_state["profileSuggestions"]` for frontend and Trace.
- Field metadata with `source="user_profile"`, `confirmed=false`, and normal current-Decision clearing behavior.

## Flow Changes

In `GenericDecisionOrchestrator.create()`:

1. Resolve the domain.
2. Build `DecisionState`.
3. Read `ProfileRepository.get(user_id)`.
4. Apply profile suggestions before running the unified lifecycle.
5. Record a `User Profile` Trace node when suggestions exist.

No message or command path reads the long-term profile, so profile effects are a creation-time input only.

## Compatibility

- Empty profile returns no suggestions and leaves old flows unchanged.
- Existing API response schemas remain compatible because fields live in existing `DecisionState.domain_state` and existing assumption/source structures.
- Diet source literal accepts `user_profile` for `dietFieldState` compatibility.
- No database schema change is needed.

## Risks And Edge Cases

- Profile text is coarse. It must not be over-interpreted into hard limits.
- Diet profile preferences can affect soft scoring, but explicit current input replaces profile-sourced unconfirmed values.
- Ignoring a profile field clears only the current Decision field; long-term profile remains unchanged.
- Trace must include `profileSuggestions` but still redact sensitive keys through existing redaction.

## Validation

- Python compile check for `src`.
- JS syntax check for `conversation.js`.
- Unit tests for profile injection, domain filtering, current input override, hard constraint safety, no-profile compatibility, Trace visibility, and no long-term profile update.
- Related regression tests for profile API, generic orchestrator, general conversation, unified decision, diet panel, and trace observability.

## Todo

- [x] New Profile injection helper.
- [x] Generic Decision creation reads and applies the current user's Profile.
- [x] Preserve `user_profile` in Decision State assumptions and suggestions.
- [x] Keep Profile values unconfirmed and non-hard by default.
- [x] Preserve profile assumptions through comparison understanding.
- [x] Ensure current diet input replaces profile-sourced unconfirmed diet fields.
- [x] Add Trace visibility for Profile suggestions.
- [x] Add frontend "来自我的资料" display with adopt / modify / ignore actions.
- [x] Add tests for injection, domain filtering, input override, hard-constraint safety, empty profile compatibility, Trace, and no auto profile update.
- [x] Update CHANGELOG.
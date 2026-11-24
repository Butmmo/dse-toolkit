# Stage 136: Scope missing-source cues to repeated search coverage

## What changed

Herald and Presence source snapshots now retain the query rung or rungs that returned each source. On a later complete check, monitoring compares those prior rungs with the current run's search metrics before interpreting an absent URL. A source is called “not found” only when all recorded rungs that found it ran successfully again. If coverage is missing or cannot be reconstructed from an older snapshot, the action is marked incomplete and the evidence says absence is inconclusive.

New or changed source cues and event cues keep their existing behavior. Partial searches already remain incomplete and do not create absence claims. Legacy source records without a recorded rung are handled conservatively as unknown coverage.

## Interpretation limits

Search engines can change indexing and ranking, so repeating a query rung does not prove that a source or underlying event no longer exists. A covered absence remains a recheck cue, not a deletion or reversal claim. Search coverage metadata stores rung names only, not full query text.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

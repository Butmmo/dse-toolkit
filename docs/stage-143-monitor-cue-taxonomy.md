# Stage 143: Preserve all monitoring cues per row

## What changed

Herald and Presence results now write a JSON `*_change_categories` value alongside the existing primary action and evidence. It records all applicable categories for that row, including source changes, identity subject/strength changes, event cues, filtered prior sources, freshness changes, and covered or incomplete missing-source checks. Partial searches and first-check baselines are explicitly represented too.

Live grid enrichment refreshes this category field on every run. Job output continues to count primary actions and now also reports per-cue totals, noting that one row may contribute to several cue totals. Herald's source-monitoring field result includes the same category value.

## Interpretation limits

Categories describe detected comparison conditions, not verified business facts. They preserve secondary findings that can coexist with the primary action; users should read the linked evidence and source before deciding what to do.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

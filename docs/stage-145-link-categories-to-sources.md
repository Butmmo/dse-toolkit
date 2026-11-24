# Stage 145: Link monitoring categories to their source URLs

## What changed

Herald and Presence monitoring now writes a compact `*_change_sources` JSON list. Each item ties one detected change category to a source URL and its short URL fingerprint. The list covers new or changed sources, identity shifts, event cues, filtered prior results, freshness changes, and missing-source coverage outcomes. It is capped at twelve references per check.

Live Ledger enrichment refreshes this column, Herald's source-monitoring field result includes it, and compact cross-device monitor history retains the references. Oversized histories keep up to six category-to-source references in the latest compact entry.

## Interpretation limits

These references identify sources associated with heuristic monitoring cues; they do not certify a claim. The cap means a category with many affected sources may not list every URL in this compact field. The ordinary source and event columns remain available for broader review.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

# Stage 146: Cite monitoring sources in field results

## What changed

Herald's `signal_source_monitoring` and Presence's new `presence_source_monitoring` field results now include source-reference candidates for the URLs attached to monitoring cue categories. Each reference retains its category and URL fingerprint; current-run sources also carry their source record ID. Herald continues to include uncategorized new/changed source candidates for compatibility.

The Ledger's existing `*_change_sources` JSON values remain the source of category-to-URL links. The field-result records now make those links available through the same evidence-reference interface used by other enriched fields.

## Interpretation limits

These are source references for review cues, not verified claims. A prior source may not have been retained in the current run; in that case the URL is still cited without a current-run record ID. Open and assess the source before acting.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

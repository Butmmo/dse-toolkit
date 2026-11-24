# Stage 144: Persist monitoring cue categories in Ledger history

## What changed

Each Herald or Presence monitor-history entry now stores the compact list of `change_categories` beside the primary review action and evidence. When an oversized history must be compacted to fit the Ledger cell limit, the newest entry retains up to eight categories. This keeps the secondary cue taxonomy available in the row's cross-device audit trail, not only in the latest result column.

The categories are normalized to short strings and capped in count and length to limit history growth. Existing history entries without categories remain readable.

## Interpretation limits

Saved categories are the classifications assigned at that check; they are not independent verification of source claims. Read the linked evidence and current source before acting.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

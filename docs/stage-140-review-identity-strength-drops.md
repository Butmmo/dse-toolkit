# Stage 140: Review declines in source identity strength

## What changed

Herald and Presence Ledger snapshots now retain each source's identity-strength label. On a later complete check, a retained URL that declines from `strong` to `moderate` or a lower known label is flagged for source-identity review, with the old and current labels and source URL. The job summary groups these with other identity-review rows.

The monitor compares categorical labels only. It does not interpret the heuristic numeric identity score as a probability, and an unchanged or improved strength does not create a review action by itself.

## Interpretation limits

Identity strength reflects matching heuristics, which can change when search snippets or available identity evidence change. A decline is a reason to verify the page and entity match; it does not prove that the source is unrelated.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

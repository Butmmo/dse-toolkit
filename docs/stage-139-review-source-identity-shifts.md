# Stage 139: Review source identity shifts

## What changed

Herald and Presence monitoring now compare a retained source's prior identity subject with its current identity subject. If the same URL changes between `company` and `person` on a complete check, the row asks for source-identity review and records the prior/current subject and URL. Grid job summaries count these separately as `identity review` rows.

This keeps company claims and named-person claims distinct when heuristic identity matching changes between runs. Older snapshots that have a `subject` label remain compatible.

## Interpretation limits

Identity subject is a heuristic classification. A change may reflect updated search text, a different page excerpt, or altered matching evidence; it does not establish that the prior match was wrong or that the result concerns a different real-world entity. Open the linked source before using it in a decision or message.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

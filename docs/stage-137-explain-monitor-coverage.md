# Stage 137: Explain search coverage behind monitoring cues

## What changed

When a previously returned URL is missing from a later monitoring check, the row's evidence now lists the prior query rung names and their latest states. A covered recheck can show, for example, `business_profile=miss`; incomplete coverage can show `path_business_signal=not repeated` or `skipped_budget`. Older records without rung metadata explicitly say that no prior rung was recorded.

This makes the Stage 136 distinction actionable: users can see which search lane did or did not run before interpreting the missing source. The existing action remains a cautious recheck or incomplete-search cue.

## Interpretation limits

A successfully repeated search rung returning no URL does not prove that a page or event disappeared. It only documents that this lane did not return the URL in this check. Search ranking and indexing can change.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

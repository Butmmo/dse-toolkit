# Stage 131: Put signal-change review cues on Ledger rows

## What changed

Repeated Herald and Presence checks on existing Ledger grids now write a compact action cue and linked source evidence beside the existing source-diff fields. Herald marks a newly returned or changed path-priority event for human source review; other new or changed evidence is also marked for review. Presence marks new or changed public professional/social results for review. Complete checks where previously seen URLs are not returned say to recheck them and explicitly do not claim the source disappeared.

Partial checks are labeled incomplete and warn users not to treat missing sources as a signal. First checks are called baselines. The action and the evidence links are also retained in each row's compact monitor history, alongside its check date and source snapshot.

The Ledger grid enrichment tool supports recurring Herald and Presence checks through its existing Schedule flow. Its help text now explains that the PC runner needs to be online when the schedule fires. These checks remain review-only: they do not send outreach or post anything.

## Interpretation limits

Search-result changes are cues for a person to verify at the linked source. A search returning a URL does not prove a business event, buying intent, or that an unreturned source ceased to exist. Scheduled work uses the existing PC runner schedule behavior and runs only when that PC and runner are available.

## Validation

Python compilation for `dse/signal_enrichment.py` and `dse/grid_enrich.py`, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` passed. No provider calls were made. No tests were run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout. The local `packs/automation.json` edit was preserved.

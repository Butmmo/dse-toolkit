# Stage 135: Flag aging source evidence during monitoring

## What changed

Herald and Presence monitoring now compares each source's freshness classification across complete checks. When a dated source moves from `recent` to `aging`, or from `aging` to `stale`, the row receives a `RECHECK` cue with the source URL, publication date, and current freshness label. The source snapshot stores the freshness label so comparisons can continue across PCs and from local history.

Freshness deterioration is separate from new source and event changes. A new or changed priority event still receives its source-review cue. Partial checks are not used to infer that evidence aged or disappeared.

## Interpretation limits

Publication dates are extracted from provider hints and visible result text with a heuristic. A source marked `stale` may still describe a continuing situation, and an undated source cannot be assumed fresh or stale. The cue asks the user to recheck the source; it does not claim a signal has ended or trigger outreach.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

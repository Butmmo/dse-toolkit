# Stage 138: Recheck prior event cues that are no longer detected

## What changed

For Herald monitoring, when the same source URL is still returned but a previously recorded signal-event category is no longer detected in its current result text, the Ledger now adds a `RECHECK` action and links the source with the prior cue label. This captures changes within a persistent source even when the URL itself remains present.

The wording describes only what the current search result text did or did not support. It does not claim that a hiring, funding, launch, leadership, or other event ended. New and newly path-priority cues continue to use their existing review actions.

## Interpretation limits

Search snippets can be shortened, reordered, or rewritten by providers. A missing cue may reflect snippet coverage or taxonomy matching, not a real-world reversal. Open the source and verify it before changing a decision or outreach.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

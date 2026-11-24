# Stage 142: Distinguish returned sources from filtered sources

## What changed

Herald and Presence search metrics now record short fingerprints of source URLs returned by each query rung, including results later rejected by identity, role, or score filters and results beyond the retained-signal selection. When an earlier source is absent from the retained signal set but its URL fingerprint appears in current raw results, monitoring removes it from the “not returned” list and requests a separate source-match review. Evidence names the rung or rungs that returned it.

Grid job summaries count source-match reviews separately. Monitoring history stores URL fingerprints alongside shortened display URLs, allowing comparisons to identify long links without retaining an extra full URL copy in the compact snapshot. Metrics do not store raw result URLs.

## Interpretation limits

A raw search result may still be a weak identity match, irrelevant to the selected person or company, or omitted by a result cap. The cue asks a user to inspect the source and applicable filters; it does not upgrade the source to accepted evidence. A URL fingerprint confirms only that the same normalized URL string was in the provider response.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

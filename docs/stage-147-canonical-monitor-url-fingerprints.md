# Stage 147: Canonicalize URLs for monitoring fingerprints

## What changed

Monitoring URL fingerprints now use a canonical URL form: scheme and host are case-normalized, fragments are removed, default ports are omitted, query parameters are sorted, and common tracking parameters (`utm_*`, click IDs, and selected analytics IDs) are removed. Original source URLs remain unchanged in the fields and links users open.

The same fingerprint helper is used for raw search-result coverage, source snapshots, event comparisons, category references, and compact Ledger history. New fingerprints use the `u2:` prefix so the normalized identity format is distinguishable from older exact-string hashes.

## Interpretation limits

Only the fingerprint identity is canonicalized; the source URL displayed to the user is preserved. Parameters not recognized as tracking remain part of source identity. Older snapshots with shortened URLs may need one comparison to establish a canonical baseline; any such source difference remains a review cue and should be checked at the displayed URL.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

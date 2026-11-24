# Stage 132: Continue monitoring from the Ledger snapshot

## What changed

Herald and Presence Ledger-grid runs now use the latest complete source snapshot saved in that row as their comparison baseline. The next scheduled check can therefore run on a different connected PC and still compare with the previous complete check, instead of silently treating that PC's empty local cache as a first check.

Each persisted monitor-history record now includes a compact source fingerprint snapshot: timestamp, source URL, title, publication date, freshness/subject metadata, and a SHA-256 fingerprint of the search snippet. Partial checks are retained for history but never become the comparison baseline. Existing Ledger monitor records without a snippet fingerprint remain usable for URL and title comparison; an unknown legacy snippet does not automatically count as changed.

Local hashed history remains a fallback for CSV enrichment and rows that have no Ledger snapshot. No lead identity is added to the shared snapshot.

## Interpretation limits

Search snapshots are comparisons of public search results, not durable monitoring of the underlying website or social platform. Results can vary by query, provider, and time. Incomplete searches remain inconclusive about missing URLs, and a changed source fingerprint is a cue to review the source.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` passed. No provider calls were made. No tests were run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout. The local `packs/automation.json` edit was preserved.

# Stage 32: Shared Ledger signal-monitor history

## What changed

- Live grid enrichment now creates `herald_monitor_history` and `presence_monitor_history` long-text columns when their corresponding signal lane runs.
- Each Ledger row keeps its latest six compact source snapshots, including check time, comparison status, summary, source URLs, short titles and evidence excerpts. The cell is capped below the grid's 5,000-character value limit.
- History and the current comparison fields refresh on every run even when Replace existing values is off. That setting still protects ordinary populated enrichment cells.
- Presence and Herald comparisons continue to distinguish partial checks. A partial check is visible in the timeline but does not establish a baseline or treat missing links as removed.
- Ledgers now have a Signal history viewer. It lets a user choose a lead and research lane, review snapshots and open evidence URLs. Because snapshots live in the member's Ledger rows, they are shared across the user's signed-in devices rather than residing only on the runner PC.
- No migration was needed: Ledger grid columns and row values already use the existing per-grid schema and authorized row update path. No SQL file was added.

## Limits

This remains monitoring of public search results and their snippets, not direct polling or archival of the source site. Six compact snapshots are retained per row to stay within cell-size limits; the runner's local history retains its existing 180-day window. Not-returned links are review cues, not evidence that content was deleted.

## Validation

Python syntax, toolkit catalog JSON, and both repositories' `git diff --check` were inspected. No live web searches, paid calls, or test suites were run.

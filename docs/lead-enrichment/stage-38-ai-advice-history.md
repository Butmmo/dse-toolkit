# Stage 38: Compare guarded DBI-AI advice across Ledger runs

## What changed

Live Herald grid enrichment now stores up to six local path-advice snapshots on each Ledger row. Consecutive advice is compared by selected path, recommendation, reason, questions, and cited source URLs (not unstable per-run source IDs), then labeled `first_advice`, `changed`, or `unchanged`. When no advice is produced, the run status is recorded with a `no_new_advice_previous_snapshot_retained` marker; this does not imply a prior opinion or source was withdrawn.

The latest advice field is cleared on runs where local advice is disabled, unavailable, invalid, or not source-backed, while its previous snapshots remain in history. The Evidence & decisions bundle includes the latest run status and recent history. Each historical advice snapshot carries source URLs and dates so it remains reviewable even when the current source IDs change. The shared field-result record also represents non-generation status explicitly.

## Guardrails and compatibility

Advice snapshots remain advisory. They never alter deterministic research findings, path outcome, commercial qualification checks, or trigger workflows/outreach. The history is stored in an existing long-text grid cell; no SQL migration is needed. The behavior applies to Herald enrichment on live Ledger grids, where prior row state is available.

## Validation

- Python syntax compilation and catalog JSON parsing.
- Git diff checks.
- Citadel production build after the history UI update.

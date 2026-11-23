# Stage 45: Ledger human fit-review handoff

Citadel's Ledger Evidence & decisions panel now records a human fit judgement and optional note alongside the enriched row. The row keeps a short history with research lane, check time, and profile key so later analysis can compare human judgments by enrichment context. Users can export the review column from the grid.

This is a handoff note only; no toolkit runner code changed in this slice. The existing enrichment evaluation scorer does not yet ingest this app review schema. No Supabase SQL migration is required. No automated tests were run.

# Stage 43: Save live-grid enrichment in recoverable batches

## What changed

- Live-grid enrichment accepts a 1-based `--start-row` and a `--batch-size` from 1 to 50 (default 10).
- It researches and writes one batch at a time. Completed batches are already saved if a later provider call or write fails.
- Progress is reported after each persisted batch. Failures report the number of saved rows and the next row position to resume with.
- The HQ Tools catalog exposes both controls for `dse.grid_enrich`.

## Resume

If the runner reports that it saved `N` rows and stopped, rerun with the same grid, lane and research settings, set **Start at grid row** to the reported row, and set the limit to the remaining rows. The row order is the order returned by the Ledger grid. Existing populated output cells remain protected unless Replace existing values is selected; monitoring summaries are refreshed as before.

This does not yet persist a server-side job record or automatically retry provider failures. No Supabase SQL is required. No automated tests were run.

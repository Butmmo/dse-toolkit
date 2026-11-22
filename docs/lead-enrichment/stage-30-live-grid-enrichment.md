# Stage 30: Enrich live Ledger grid rows

## Delivered

- Added the `dse.grid_enrich` HQ tool and `python dse.py grid enrich <grid>` runner command.
- From an open Ledger grid, the tool receives that grid ID and its Ledger Engine automatically.
- It reads rows already in the grid and runs one of three enrichment lanes: Website (first-party website/contact enrichment), Herald (company and person signal research plus draft fields), or Presence (public professional/social signal research).
- Essential result fields are selected by default; full mode adds available evidence and metadata columns. The runner creates missing columns or reuses matching columns and writes values back to the corresponding existing rows.
- Existing non-empty output values remain untouched unless Replace existing values is selected. Empty results do not erase cells. Values that exceed the grid cell limit are omitted and counted.
- Each run also leaves its source CSV and enrichment summary on the PC.
- The Ledger HQ tool panel refreshes the grid after a successful job.
- Website runs allow up to 500 rows per job; Herald and Presence currently allow up to 50 each, matching their enrichment service limits. The per-grid 60-column ceiling still applies.
- Existing CSV workflows remain available. The change adds live grid enrichment without making a CSV export/import a prerequisite.

## Provider waterfall continuation

This stage also includes the ongoing opt-in field-level provider waterfalls for phone, person identity, and firmographics in website enrichment. They use explicit per-provider response mappings, confidence/identity acceptance checks, caching, budget accounting, dry-run projections, and candidate/audit metadata. No external provider keys or network calls are made by default.

## Persistence and safety

Grid access and writes use the existing `hq_grid_rows`, `hq_grid_add_columns`, and `hq_grid_set_cells` runner RPCs under the connected user. No Supabase SQL migration was added, so no SQL-to-run file is needed.

## Validation

- Python syntax compilation and catalog JSON parsing were run.
- `git diff --check` was run for the toolkit and app.
- No test suite was added or run. A live run against the user's Supabase Ledger requires the updated app catalog and refreshed PC toolkit.

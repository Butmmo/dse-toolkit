# Stage 34: Cross-lane evidence review in Ledgers

## What changed

`dse.grid_enrich` writes a compact `<lane>_evidence_decisions` record for Website enrichment, Herald research, and Presence research whenever it processes live Ledger rows. Website records retain selected field values, source/provider and verification details, candidate alternatives, waterfall metadata, and lead scoring explanation. Presence records retain identity-match cues, heuristic score, publication date/freshness, source links, comparison state, and search-waterfall measurements. Herald retains its decision and citation record.

Records are kept below the Ledger's 5,000-character cell cap and compacted to smaller valid JSON if provider or search metadata is unusually large. The toolkit adds a long-text output column when needed, subject to the existing grid column cap.

## Validation

- Python syntax compilation for `dse/grid_enrich.py`.
- Catalog JSON parsing and diff checks.
- Citadel production build after the UI change.

## Operator note

Users need the updated PC toolkit to generate Website and Presence evidence on future grid runs. Existing Herald evidence remains readable. No Supabase SQL is needed.

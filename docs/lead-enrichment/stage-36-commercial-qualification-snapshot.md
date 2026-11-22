# Stage 36: Evidence-based commercial qualification snapshot

## What changed

Path outcome briefs now summarize evidence already present in the lead row: website activity, populated contact/booking routes, any disclosed scale fields, decision-maker details, Presence identity/freshness counts, and source-backed path signal counts with a latest available publication date. Where `field_results` contain provenance, the brief carries the provider, source URL, verification state and identity cue. Otherwise it labels the fact as a lead-record/enrichment field.

The Ledger presents these under **Observed from existing lead data**, separately from the path's **Commercial fit checks (not yet assessed)**. The observations are not collapsed into a score or a claim of budget, need, or ability to pay. Manual checks still require direct verification.

## Compatibility

The snapshot is embedded in `dse_path_outcome` and the shared field-result record, then included in the compact Herald evidence JSON for Ledger review. It reads fields already carried by the lead row or shared result contract. No Supabase SQL is required.

## Validation

- Python syntax compilation for the updated signal and grid enrichment modules.
- Catalog JSON and Git diff checks.
- Citadel production build after the Ledger UI update.

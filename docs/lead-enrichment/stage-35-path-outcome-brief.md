# Stage 35: Path-specific enrichment tied to DSE outcomes

## What changed

Herald lead signal enrichment now emits a `dse_path_outcome` record for every researched lead. It translates the selected Engine path into a clear business outcome to explore, likely customer and buyer, pain hypothesis, monetization route, proof metrics, explicit commercial viability checks, and a path-specific next human step.

The outcome record cites retained source candidates tagged as priority or supporting for that path. It distinguishes `priority_signal_needs_human_validation` from `insufficient_path_specific_evidence`. It never treats search matches as proof of a pain, buying intent, budget, ability to pay, or a verified business classification. Commercial checks start as `not_assessed` and remain for the user to verify with the prospect.

The record is included in CSV output, shared `field_results`, and live grid output. The Ledger Evidence & decisions panel presents outcome, buyer, hypothesis, monetization, proof, source IDs, and qualification checklist together.

## Covered paths

General research plus SMB Optimisation, Search & AI Visibility, AI Voice Receptionist, AI Automation Engineering, Revenue Recovery, Go-to-Market Engineering, Authority Engine, Broadcast Engine, and The Ascent.

## Validation

- Python syntax compilation for the touched enrichment modules.
- Catalog JSON parsing and diff checks.
- Citadel production build after the UI update.

No Supabase SQL is needed. Existing grids gain the `dse_path_outcome` output column during Herald grid enrichment.

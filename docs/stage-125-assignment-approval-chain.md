# Stage 125: Carry approval provenance through outreach assignment

The outreach assignment step now requires an approved paired CSV and validates its receipt against the local cohort and A/B config fingerprints before assigning one variant per lead. It confirms each row has the same receipt ID, both recorded variants were run under that approval, and the paired source still matches the original hashes.

The receipt ID is recorded in the assigned CSV, assignment audit, and cohort assignment record. Engine import validation now rechecks that receipt and requires every assigned row to carry the same ID. The importer and generated Engine send lists retain this provenance field, so it remains available through the Engine handoff.

Validation performed: Python compilation of `dse/enrichment_eval.py`, `dse/importer.py`, and `dse/engines.py`; CLI help; catalog JSON parsing; and `git diff --check`. No paid-provider requests were made.

The implementation was pushed to codex/hq-runner-id-routing and installed in the active PC runner checkout. The runner restarted and reported 182 tools online. The local packs/automation.json change was preserved.

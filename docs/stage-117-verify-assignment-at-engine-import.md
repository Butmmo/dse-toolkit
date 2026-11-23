# Stage 117: Verify assigned experiment files at the Engine import boundary

## Gap

The assignment tool recorded a cohort-bound audit, but later Engine import and list-building steps did not verify that the assigned CSV still matched that audit. A changed, renamed, or copied assignment file could therefore reach list generation without its original verification.

## Change

- Go-to-Market import now checks every `*-outreach-assigned.csv` against its sidecar audit and local waterfall cohort record.
- It verifies the target Engine, file name and hash, experiment and field, provider pair, variant config fingerprints, stable lead IDs, fixed seed assignment, row counts, and the paired source file's current hash.
- Missing or mismatched assignment evidence blocks import/list generation with a clear recovery instruction.
- HQ Tools' file-check description explains that experiment assignment records are verified locally before import.

## Verification

- Checked Python compilation, catalog JSON, and the import CLI help.
- Pushed to `codex/hq-runner-id-routing` and restarted the PC runner; its startup log reports 181 tools.
- No Engine import, lead assignment, enrichment provider call, or Send Desk run was performed.

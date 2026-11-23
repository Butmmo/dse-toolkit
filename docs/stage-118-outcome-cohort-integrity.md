# Stage 118: Reconcile outcome reports with the verified assignment cohort

## Gap

Send Desk outcome reports already checked the assignment CSV hash and whether expected lead/variant counts reached Send Desk lists. They did not revalidate the assignment CSV's local cohort record, paired-source evidence, or deterministic per-lead seed assignment while scoring.

## Change

- Outcome scoring now runs the same assignment-file verifier used at Engine import before marking an assignment audit as reconciled.
- The check confirms the file still matches the sidecar audit and local cohort manifest, its paired source evidence remains intact, the intended Engine is correct, and each retained lead still matches its stable seed assignment.
- A missing, altered, or inconsistent cohort record yields `cohort_record_mismatch` and suppresses A/B rate comparisons, while descriptive per-variant counts remain available.
- The report includes the cohort reconciliation result and a short recovery reason.

## Verification

- Checked Python compilation, CLI help, and the report code path for JSON-safe output fields.
- No outcome records were changed and no email was sent.

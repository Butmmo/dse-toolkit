# Stage 126: Report approval provenance in Send Desk outcomes

The Send Desk outcome scorer now exposes the assignment approval receipt ID in its audit checks and human-readable Markdown. It compares the assigned CSV and actual Engine Send Desk rows to that same receipt ID. Missing or different approval provenance produces an `approval_receipt_mismatch` audit status, which suppresses the A/B comparison until reconciled.

The assignment audit continues to be verified by the Engine importer, which checks the approval receipt, paired source and cohort. The Send Desk check adds exact receipt-ID reconciliation across the list rows used for outcome measurement, alongside existing CSV hashes, cohort, lead roster, variant counts, and assignment seed checks.

Validation performed: Python compilation of the outcome, importer, and Engine modules; CLI help; catalog JSON parsing; and `git diff --check`. No live provider requests or paid runs were made.

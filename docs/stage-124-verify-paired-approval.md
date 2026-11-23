# Stage 124: Verify approved receipt across paired experiment outputs

Live variant CSV rows now carry the approval receipt ID, and the local cohort record stores it at both experiment and per-variant level. The pair step requires every row in both result files to carry one identical, nonempty receipt ID, and checks that ID against the local receipt file and its content digest.

Before writing a paired CSV, the pair step also verifies the receipt's approved ceiling and per-variant maximums, and reconciles its A/B config hashes, experiment identity, source hash, lead cap, stable cohort hash, and both result-file hashes with the cohort record. A/B files produced under different approvals or altered after completion are rejected without creating a paired output. The paired summary and manifest retain the approval ID for audit continuity into the assignment step.

Validation performed: Python compilation of `dse/enrich.py` and `dse/enrichment_eval.py`, CLI help, catalog JSON parsing, and `git diff --check`. No paid-provider requests were made.

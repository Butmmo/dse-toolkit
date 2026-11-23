# Stage 110: Gate variant comparisons on assignment reconciliation

When an Engine has a generated assignment audit, the Send Desk scorer now withholds A/B rate differences unless the audit is reconciled: the assigned CSV exists and matches its hash, all expected assigned leads have reached Send Desk lists, and observed variant counts and assignment seed agree with the manifest.

Per-variant counts and the assignment audit table remain visible while coverage is incomplete or a mismatch exists. The report states the audit status that suppressed the comparison. Legacy experiments without an assignment manifest retain their existing descriptive comparison rules.

This avoids presenting partial list generation or a modified assignment as a comparable experiment cohort. A verified list cohort still does not prove that messages were sent or delivered; outcome denominators continue to rely on explicit Send Desk taps.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

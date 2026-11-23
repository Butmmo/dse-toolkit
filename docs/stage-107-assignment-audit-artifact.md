# Stage 107: Write a data-minimized assignment audit

Each outreach assignment now writes a companion `*-outreach-assigned-assignment.json` beside its CSV. The audit records the experiment and field, seed, assignment algorithm, source and assigned CSV filenames and SHA-256 hashes, assigned lead count, A/B counts, and optional destination Engine. It contains no lead IDs, contact details, or message text.

HQ Tools lists both the assigned CSV and audit JSON as outputs. Repeating the exact assignment is idempotent. If either output path already contains different content, the command refuses to overwrite it and leaves the existing files untouched.

The hashes let an operator verify which input produced an assigned cohort and whether the staged CSV changed. They do not establish that outreach was sent or that assignment was randomized correctly. The existing Send Desk outcome report remains the place to summarize logged outcomes.

Validation for this slice: catalog generator execution, Python compilation, CLI help, and `git diff --check`; no test suite was run.

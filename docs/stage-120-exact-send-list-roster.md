# Stage 120: Reconcile the exact assigned lead roster

## Gap

Outcome scoring compared expected and observed assignment counts by variant, but equal counts can still conceal substituted lead IDs or a lead placed in the wrong variant.

## Change

- The scorer now reads the verified assigned CSV and compares the exact set of stable lead IDs in A and B against Send Desk list rows.
- Missing and unexpected lead IDs are counted separately for each variant.
- A count-only match with a different roster is now `send_list_assignment_mismatch`, which suppresses A/B comparisons.
- The JSON report and Markdown audit table show whether the exact roster matches and how many IDs are missing or unexpected per variant.

## Verification

- Checked Python compilation, CLI help, catalog JSON and Markdown formatting logic.
- No Send Desk lists, outcomes, assignments or email sends were changed.

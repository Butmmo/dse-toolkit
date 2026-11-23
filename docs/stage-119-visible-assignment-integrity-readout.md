# Stage 119: Show assignment integrity in the outcome brief

## Gap

Stage 118 made outcome scoring revalidate the assignment CSV against the local cohort record. The structured report carried that result, but the Markdown assignment table did not show the cohort-record status or the specific validation error.

## Change

- The human-readable outcome brief now has a cohort-record status column and an integrity-detail column.
- A failed check shows its reason in the table, alongside the overall audit status and assigned CSV hash status.
- HQ Tools describes that comparisons require the assignment, cohort, and paired-source checks to reconcile.

## Verification

- Checked Python compilation, catalog JSON and CLI help.
- Confirmed Markdown table output sanitizes pipe and line-break characters in integrity details.
- No outcome files were generated from user data and no emails were sent.

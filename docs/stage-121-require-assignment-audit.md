# Stage 121: Require an assignment audit for assigned cohorts

## Gap

Outcome scoring discovered invalid assignment audits when it found a sidecar file. If the sidecar was deleted, unreadable or used an unsupported schema, an explicitly assigned Send Desk cohort could have no audit check at all and fall back to its row tags.

## Change

- The scorer now finds explicitly assigned cohorts in Send Desk rows and requires a corresponding readable assignment audit.
- Missing or unreadable audits are reported as `assignment_audit_missing` and suppress A/B comparisons.
- The audit table retains the observed variant counts and gives a clear missing-sidecar reason; expected cohort counts are marked unknown rather than inferred.
- The report interpretation and HQ Tool summary explain that audit presence is required.

## Verification

- Checked Python compilation, CLI help, catalog JSON and Markdown rendering fields.
- Pushed to `codex/hq-runner-id-routing` and restarted the PC runner; its startup log reports 181 tools.
- No user outcome records were changed and no emails were sent.

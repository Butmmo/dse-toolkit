# Stage 102: Audit outreach assignment in experiment outcome reports

The Send Desk outcome scorer now reads the assignment metadata added in Stage 101. It validates that an explicit assignment's experiment ID and A/B variant match the row's experiment tags, reports the assignment mode and seed(s), and fails on conflicting or partial assignment markers.

If a cohort mixes explicitly assigned rows with legacy rows that only carry enrichment variants, or uses multiple/missing seeds, its A/B difference is suppressed. Per-variant metrics remain visible with the mixed-mode warning so the operator can see why the comparison is unavailable. Legacy-only cohorts remain readable and are labeled as not having an enforced single-variant assignment.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> [--experiment-id <id>]
```

This closes the local audit loop between assignment, Engine/Send Desk propagation, and outcome scoring. The scorer still cannot prevent paired source CSVs from being imported directly; app-side enforcement remains a follow-on slice.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

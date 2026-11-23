# Stage 111: Enforce one assignment mode and seed per Engine cohort

Before importing experiment rows into a Go-to-Market Engine, the toolkit now checks the whole incoming cohort and its existing Send Desk lists. For each experiment and field, it blocks:

- mixing explicitly assigned rows with legacy rows that only carry an A/B enrichment tag;
- using more than one assignment seed;
- sending the same stable lead ID in both variants;
- incomplete or conflicting assignment metadata on an existing list row.

This moves the mixed-mode and mixed-seed protection from the outcome report to the Engine import boundary, before another list is created. Existing lists remain intact; the operator gets a reason and must keep the experiment on one consistent assignment workflow.

```powershell
python dse.py daily <engine>
```

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

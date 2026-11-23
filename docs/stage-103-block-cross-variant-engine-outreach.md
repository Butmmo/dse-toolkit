# Stage 103: Block cross-variant experiment leads at the Engine boundary

Go-to-Market Engine imports now validate waterfall experiment rows before company/domain deduplication. If a lead would appear in both A and B for the same experiment and field, list generation stops with a command pointing to `eval-enrichment assign-outreach`. The guard also checks existing Engine send-list and draft CSVs, so a later run cannot quietly place the same lead in the opposite variant. Conflicting or partial assignment markers are rejected.

Keep the paired enrichment quality CSVs outside `engines/<slug>/imports/`. Import only the assigned output produced by:

```powershell
python dse.py eval-enrichment assign-outreach my-lists\paired-enrichment.csv --experiment-id my-waterfall-test --seed 42
```

The source rows are checked before website deduplication, and existing scheduled/draft lists are included in the exposure check. This guard prevents the toolkit's Engine import flow from preparing the same experiment lead in both variants; it does not block a user from manually sending separate files outside the Engine workflow.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

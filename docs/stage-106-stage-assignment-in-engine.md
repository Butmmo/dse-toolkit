# Stage 106: Save assigned leads directly into the destination Engine

The HQ Tools assignment action now requires a destination Engine. After validating the paired A/B source and making the stable one-variant assignment, it checks the Engine's existing send lists and drafts for cross-variant exposure. Only then does it write the assigned CSV directly to `engines/<slug>/imports/`.

That removes the manual download/copy step between assignment and Engine list generation. The paired source remains in `my-lists` for enrichment review and is not copied into the Engine imports folder. The Engine import validator still checks again before building send lists. If a prior list already has an opposite variant for a lead, assignment stops before writing the import CSV.

The CLI remains backward compatible: `--engine` is optional when run directly; without it, the assigned CSV is written next to the source or to the explicit `--out` path. The HQ Tools action supplies the Engine and always stages into its imports.

```powershell
python dse.py eval-enrichment assign-outreach my-lists\paired-enrichment.csv --experiment-id test-2026-11 --seed 42 --engine my-engine
```

Validation for this slice: Python compilation, CLI help, catalog generator execution, catalog structure/size check, and `git diff --check`; no test suite was run.

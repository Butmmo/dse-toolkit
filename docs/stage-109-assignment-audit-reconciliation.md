# Stage 109: Reconcile assignment audits with Send Desk lists

The Engine outcome report now finds Stage 107 assignment manifests in that Engine's `imports` folder. For each matching experiment it confirms that the assigned CSV exists inside the Engine and matches its recorded SHA-256, then compares expected per-variant assignment counts and seed with unique assigned leads present in Send Desk lists.

The report status distinguishes a verified assignment represented in lists, lists that are still incomplete, a missing assigned CSV, a changed CSV hash, and mismatched list variant counts/seed. JSON includes only aggregate counts, filenames, and hashes; the Markdown brief adds a compact audit table. If no manifest exists (for example, for legacy assignments), the outcome report remains available without this reconciliation section.

This proves that the staged artifact matches its audit and that expected assigned leads reached local Engine lists. It does not prove a message was sent or delivered; the existing Send Desk taps remain the source for those outcomes.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> [--experiment-id <id>]
```

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

# Stage 101: Assign each outreach lead to one experiment variant

Enrichment quality experiments can run both provider orders on the same lead for paired review. Outreach must not send both variants to that lead. This slice adds a separate deterministic assignment step for a combined A/B enriched CSV:

```powershell
python dse.py eval-enrichment assign-outreach my-lists\paired-enrichment.csv --experiment-id my-waterfall-test --seed 42
```

The command requires exactly one A row and one B row per stable experiment lead ID, and exactly one experiment field. It fails without writing an assignment file if rows are unpaired, duplicated, or missing IDs. It selects one row per lead using SHA-256 parity over experiment ID, seed, and stable lead ID. Re-running with the same inputs and seed preserves each lead's variant. Small samples can produce an uneven split; the report prints counts for A and B.

The output is a separate `*-outreach-assigned.csv` containing only selected rows, with assignment experiment ID, variant, and seed columns. Those columns are preserved through the Engine importer, generated first-touch lists, and follow-ups. Use this assigned file as the only source for outreach to these experiment leads. Keep the two original enrichment outputs for paired quality review; do not import both into an Engine for sending.

This is deterministic split assignment, not proof of randomization quality or causal inference. It does not itself send messages or prevent a user from bypassing the assigned file and importing the paired originals. The next product slice should surface and enforce this flow in Citadel/Engine UI.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

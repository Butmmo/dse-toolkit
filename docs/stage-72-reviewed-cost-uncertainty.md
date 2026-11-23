# Stage 72: Reviewed cost basis and lead-cluster uncertainty

## What changed

The enrichment evaluation report now calculates provider cost per human-reviewed correct result from one consistent reviewed cohort. Its spend numerator includes estimated provider costs only for rows with an explicit `yes` or `no` value-correctness label. Its denominator remains the explicitly `yes`-labeled reviewed rows that had a priced provider attempt in that currency. Unreviewed rows no longer inflate the numerator while being absent from the denominator.

The report also includes a reproducible percentile bootstrap interval. It resamples lead clusters with replacement, keeping all reviewed field rows for a lead together. Each currency reports the point estimate, reviewed denominator, distinct leads, requested and valid replicates, and 95% interval bounds. The default is 500 replicates and seed 42; use `--cost-bootstrap-reps 0` to disable interval generation, or set `--cost-bootstrap-seed` to reproduce a different run.

## Scope and interpretation

This interval describes sampling variation in the reviewed cohort. It cannot repair selection bias, an unrepresentative review sample, missing provider prices, or incorrect cost configuration. Provider cost values are configured estimates, not invoices. Unknown-price attempts remain counted separately, and currencies are never combined.

## How to use

```powershell
python dse.py eval-enrichment score review.csv --cost-bootstrap-reps 500 --cost-bootstrap-seed 42
```

The JSON report adds `provider_cost_per_reviewed_correct_uncertainty_by_currency` to each cohort’s metrics and corrects `provider_attempt_estimate_per_human_reviewed_correct_result_by_currency` to use reviewed rows for both spend and outcome counts.

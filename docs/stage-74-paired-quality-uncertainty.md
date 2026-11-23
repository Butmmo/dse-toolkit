# Stage 74: Uncertainty for paired source quality differences

## What changed

Each paired source comparison now includes a lead-pair percentile bootstrap interval for the A-minus-B reviewed yes-rate difference. This appears for all four reviewed dimensions (`value_correct`, `identity_correct`, `evidence_adequate`, and `freshness_acceptable`). Only leads with one result per source and explicit yes/no labels from both sources enter that dimension’s interval. Both outcomes for a lead are resampled together, preserving the paired design.

The default is 500 replicates with seed 42. Use `--paired-bootstrap-reps 0` to disable these intervals or `--paired-bootstrap-seed` to choose another reproducible seed. These settings are independent of the reviewed cost interval options.

## Interpretation and limits

The interval describes sampling variation among the matched, reviewed leads. It cannot correct selection bias, insufficient or nonrepresentative reviews, provider pricing errors, or differences between this cohort and future leads. It is descriptive evidence, not a significance test or proof that a source is generally superior. The existing minimum-labeled flag remains a caution threshold, not a guarantee of statistical power.

The interval is emitted as `dimensions.<dimension>.paired_rate_difference_a_minus_b_cluster_bootstrap_95` within each `paired_source_comparisons` entry.

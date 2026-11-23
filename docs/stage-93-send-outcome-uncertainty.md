# Stage 93: Put sample uncertainty beside Send Desk rates

The experiment outcome report now adds a 95% Wilson interval for each variant's reply, booked-call, and win rates. Each variant also carries a `low_sample_caution` flag when fewer than 30 unique leads were explicitly marked sent. The threshold is a caution flag, not a claim of statistical power.

Run the same command as Stage 92:

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> [--experiment-id <id>]
```

This makes small denominators and rate uncertainty visible in the output before anyone compares variants. Intervals are descriptive binomial intervals; they do not adjust for biased assignment, lead mix, cross-variant exposure, delivery, attribution windows, or other sources of uncertainty. The report still makes no automatic winner or causal claim.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

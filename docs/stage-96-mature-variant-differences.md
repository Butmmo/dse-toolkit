# Stage 96: Compare variants inside the same mature window

The Send Desk experiment report now calculates A-minus-B reply, booked-call, and win-rate differences for the fixed observation window from Stage 95. It reports each variant's mature sent-lead denominator and how many stable lead IDs were sent in both variants during that mature cohort. The Markdown brief surfaces the differences in percentage points beside the cohort results.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> --maturity-days 14
```

The comparison uses per-variant mature outcome rates; it does not claim a paired treatment effect, causal lift, or statistical significance. Shared leads remain an explicit contamination caution. This keeps the comparison aligned to one observation window while retaining the existing all-time comparison and variant-level intervals.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

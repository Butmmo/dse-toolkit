# Stage 95: Compare outcomes after a consistent observation window

The Send Desk experiment report now includes a fixed-window outcome view alongside all-time logged totals. By default it uses 14 days after each lead's first confirmed send. A lead enters the fixed-window denominator only after that full window elapsed as of the report date; reply, booked-call, and win events count only when logged within the window. Leads with no usable send date are reported separately rather than silently treated as mature.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine>
python dse.py eval-enrichment score-send-outcomes <engine> --maturity-days 21
```

The JSON and Markdown outputs include mature sent counts, leads still awaiting maturity, missing send dates, and fixed-window outcome rates per mature sent lead. This reduces the timing mismatch between old and recently sent cohorts. It does not equalize assignment, lead mix, deliverability, or follow-up execution, and it does not establish causation. Choose a window that fits the actual outreach cadence before comparing experiments.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

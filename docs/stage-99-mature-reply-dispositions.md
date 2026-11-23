# Stage 99: Align reply categories with the mature outcome window

The experiment brief now reports reply disposition categories twice when data permits: all-time logged categories and categories observed inside the fixed maturity window for leads whose full window has elapsed. Mature-window categories are unique lead counts per category, with categories allowed to overlap if a lead had more than one categorized reply in the window. Out-of-office responses remain excluded.

This makes category comparisons consistent with the fixed-window reply, booking, and win rates and avoids treating recent cohorts as though they had complete reply histories. The report uses the Reply Desk's existing logged category values and does not reinterpret reply text.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> --maturity-days 14
```

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

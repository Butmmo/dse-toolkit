# Stage 92: Score experiment variants against Send Desk outcomes

This slice connects waterfall experiment provenance to explicit Send Desk dispositions. Run:

```powershell
python dse.py eval-enrichment score-send-outcomes <engine>
python dse.py eval-enrichment score-send-outcomes <engine> --experiment-id <id>
```

The command joins tagged first-touch and follow-up list rows to `data/log.csv` using the established source-list and row ID keys. It groups records by experiment, field, variant, and stable experiment lead ID, so multiple touches of one lead count once. The JSON report contains assigned and sent unique-lead counts, replies, booked calls, wins and losses, plus outcome rates per sent lead. By default it writes to `engines/<engine>/data/waterfall-send-outcomes.json`; a filtered run gets a filename containing the experiment ID. `--out` selects another path.

The report also detects stable lead IDs present in both A and B. Such overlap may mean a business received both variants, so the comparison is explicitly descriptive and carries an overlap caution. No causal winner, statistical significance, random assignment, delivery, or provider quality claim is inferred. Only dispositions that were explicitly logged are counted; unmarked rows remain assigned but unsent.

Validation for this slice: Python compilation and `git diff --check`; no test suite was run.

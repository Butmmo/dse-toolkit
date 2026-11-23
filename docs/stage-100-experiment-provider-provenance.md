# Stage 100: Show which provider setup each outcome variant used

The experiment outcome report now includes the recorded provider order and config SHA-256 fingerprint for each experiment, field, and variant. The Markdown brief displays provider order and shortened fingerprints next to that variant. It marks configuration metadata as incomplete when any tagged row in the cohort lacks either value, and inconsistent when recorded values vary within that cohort.

This closes a reporting gap: a reader can identify the setup behind A and B without searching source CSVs or trusting variant labels alone. The report only repeats metadata already carried by the tagged rows; it does not re-run providers or validate that provider behavior matched the configuration.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine> [--experiment-id <id>]
```

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

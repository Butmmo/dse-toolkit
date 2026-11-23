# Stage 77: Markdown benchmark decision brief

The enrichment benchmark scorer can now write a concise Markdown companion to its JSON report. It summarizes each paired source comparison with the evidence status, matched reviewed count, value-correctness difference and interval, lead result availability, any opposing review-dimension signals, and priced-subset cost notes.

Request the brief with `--markdown-out`:

```powershell
python dse.py eval-enrichment score my-lists\reviewed-benchmark.csv --markdown-out my-lists\reviewed-benchmark-brief.md
```

The JSON report remains the machine-readable source of detail. The brief is a convenience summary: it does not choose a provider, and all observations remain descriptive of the reviewed cohort. It labels the difference as A minus B, notes that intervals spanning zero do not show a clear direction, and cautions that priced cost comparisons use a subset and configured estimates rather than invoices.

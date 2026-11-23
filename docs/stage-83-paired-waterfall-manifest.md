# Stage 83: Paired waterfall experiment manifest

The evaluator now has a `plan-waterfall-experiment` action that selects a deterministic subset of leads with exactly one explicitly reviewed result from each named configured provider for a chosen field and exact Engine path/profile/lane cohort. Its CSV lists each lead once with both provider orders, the paired historical review labels, the seed, a plan ID, and the input CSV SHA-256 digest. Company and website identifiers are included only when present in the local review CSV.

Example:

```powershell
python dse.py eval-enrichment plan-waterfall-experiment my-lists\reviewed-benchmark.csv `
  --field best_email --provider-a provider_one --provider-b provider_two `
  --engine-path "AI Engineer" --enrichment-profile default --research-lane herald `
  --leads 50 --seed 42 --out my-lists\waterfall-order-manifest.csv
```

The manifest is a manual-run aid. It does not modify waterfall configurations, run providers, or send outreach. Execute both variants against isolated copies of the same selected leads, hold stop rules, acceptance settings and spend cap constant, approve any paid calls first, and keep outreach disabled until outputs are reviewed. Repeatedly using the same reviewed leads is not an independent population sample; treat this as a controlled cohort comparison, not a guarantee of general performance.

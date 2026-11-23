# Stage 84: Waterfall order experiment config drafts

The enrichment CLI can now create two local waterfall JSON drafts from an existing config using `--build-waterfall-experiment`. Choose a source with `--waterfall-config`, a field with `--experiment-field`, and two provider names already present in that field with `--experiment-provider-a` and `--experiment-provider-b`. The tool copies the source config twice and swaps only those providers' positions, leaving the original file untouched. Draft filenames are unique and existing files are never overwritten.

Example:

```powershell
python dse.py enrich --build-waterfall-experiment --waterfall-config enrich-waterfalls\my-waterfall.json `
  --experiment-field email --experiment-provider-a provider_one --experiment-provider-b provider_two
```

The selected providers must already be configured in the requested field. Adapter mappings are checked locally without requiring API keys or making requests. Review both drafts and use the existing readiness and spend-preview steps before a paid run. Keep the approved lead sample, stop rule, confidence thresholds, call budget, and currency fixed. Creating drafts does not execute the experiment or approve spend.

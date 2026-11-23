# Stage 67: Read-only provider spend preview

## What changed

Added `dse.enrich_spend_preview` to HQ Tools and `python dse.py enrich --spend-preview`. The preview uses only the selected local provider or waterfall configuration, its configured per-provider price and call caps, and a requested lead count. It reports a conservative known-price estimate, currency, possible calls by field, unpriced provider names, and whether the live run requires numeric spend approval or unknown-price acknowledgment.

The preview does not open a CSV, read lead data, visit a website, make a provider request, or write a file. API keys are not returned. This lets a user inspect the estimated ceiling before invoking enrichment, then reuse the same configuration and call limits in a live run with `--max-provider-spend`.

## How to use

In HQ Tools, select **Lead enrichment: preview provider spend**, choose the local waterfall JSON (or a single configured provider), and enter the lead count. On the PC, the equivalent is:

```powershell
python dse.py enrich --spend-preview --waterfall-config enrich-waterfalls\my-waterfall.json --max 100
```

The output is compact JSON for visibility and workflow use. It is a local estimate, not an invoice. If a provider has no configured price, the preview identifies it and excludes unknown charges from the numeric estimate. The subsequent live run still requires the Stage 66 acknowledgment flag for those providers.

## Scope and safeguards

- Preview uses adapter settings already installed on this PC and does not fetch current vendor pricing.
- The conservative maximum assumes the most expensive configured rung could be attempted for each eligible call.
- A missing or invalid local provider adapter is reported as a configuration problem, not silently treated as free.
- The grid website lane already maps its dry-run toggle into the enrichment runner; no change was needed there.
- No live enrichment or provider request was made during this stage.

## Verification performed

Python syntax, catalog JSON parsing, and `git diff --check` are the planned local checks. No test suite or live provider call was run.

# Stage 70: Provider attempt cost attribution

## What changed

Website enrichment now attaches a per-field provider-waterfall cost breakdown to `dbi.field-result.v1` metadata. Each provider rung records actual request attempts for that lead, its locally configured per-call estimate and currency, and estimated charge when known. Cache hits and runs with no request carry no call charge. Failed requests are counted as attempts when the provider layer reached the request, even if the provider returned an error.

When a provider supplies the selected email, phone, person identity, or firmographic result and its cost is known, the shared field-result `cost` object now includes the estimated amount, currency, call quantity, and `estimated: true`. The metadata also preserves the entire per-rung waterfall cost breakdown, including rejected/failing rungs and unpriced attempts. Provider names on selected email results and candidates now identify the actual rung rather than the whole configured chain.

The benchmark review-sheet preparation carries the per-rung breakdown forward. Evaluation reports now separate accepted-result declared cost from total provider-attempt estimates, show cost estimates per system-accepted result, and count attempts with unknown prices. These are estimates based on the local adapter configuration; they are not vendor invoices and do not establish human-verified correctness.

Repeated same-domain rows within one CSV run reuse the first row's enrichment. Cost and call metrics are attributed once to the first row; duplicate rows record that the result and cost were shared, preventing benchmark totals from charging the same provider attempt repeatedly.

## Use

After enriching a CSV, create a review sheet and score it as before:

```powershell
python dse.py eval-enrichment prepare my-lists\enriched-list.csv
python dse.py eval-enrichment score my-lists\enriched-list-enrichment-review.csv
```

Inspect `provider_attempt_cost_estimate_by_provider`, `provider_attempt_cost_estimate_by_currency`, `provider_attempt_estimate_per_accepted_result_by_currency`, and `provider_attempts_with_unknown_price` in the evaluation JSON. Prefer the `by_field_and_source` provider groups for provider comparisons; waterfall attempt costs can be present even when the final accepted value came from another source. These attempt totals include failed/rejected calls represented in each field's waterfall record. Compare only similar fields, lead cohorts and provider configurations.

## Limits

- Estimates require `cost_per_call` and `cost_currency` to be maintained accurately in the local provider adapter.
- Providers priced by credit bundles, tiers, outcome, monthly minimum, or variable retries may not match this estimate.
- Unknown-price call costs remain unknown; they are not treated as zero.
- “Accepted result” is the toolkit's configured acceptance outcome. It is not human verification. Human review labels remain the basis for correctness analysis.
- The separate local usage journal remains provider-call metadata without lead identity; no identity was added to that journal.

## Verification

Python syntax compilation, catalog JSON parsing (catalog unchanged but still parseable), and `git diff --check` are used. No automated test suite, lead enrichment, or paid provider request was run.

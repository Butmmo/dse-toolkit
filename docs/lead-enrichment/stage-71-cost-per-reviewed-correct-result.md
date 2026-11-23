# Stage 71: Spend per human-reviewed correct result

## What changed

The enrichment evaluation report now calculates **provider waterfall attempt spend per human-reviewed correct field result**, by currency, in addition to its existing configured spend-per-system-accepted-result measure. It uses only rows explicitly labeled yes for `value_correct` (or `adjudicated_value_correct` when that column exists) and only where the row records at least one provider attempt in that currency. It reports the denominator for each currency, the number of human-correct reviewed rows with attempts, and unknown-price attempt counts separately.

The calculation uses Stage 70's per-row waterfall attempt records. Costs of rejected or failed calls are included when configured, because those calls may still be billable. If a waterfall includes unknown-priced attempts, those calls are counted as unknown and are not treated as free.

## How to use

Prepare and label a field-result review sheet, adjudicate the value-correctness labels, then score it:

```powershell
python dse.py eval-enrichment prepare my-lists\enriched-list.csv
python dse.py eval-enrichment score my-lists\enriched-list-enrichment-review.csv
```

Inspect `provider_attempt_estimate_per_human_reviewed_correct_result_by_currency` and `provider_attempt_cost_human_correct_denominator_by_currency`, alongside `provider_attempt_cost_estimate_by_provider`, unknown-price attempts, review labels, and confidence counts. Use the field/source/path/profile cohort views to compare similar lead mixes.

## Interpretation and limits

- “Human-reviewed correct” means an explicit yes label in the selected adjudication column; blank and unknown labels do not count.
- The metric is waterfall spend associated with reviewed outputs. It is not a randomized estimate of an individual provider's causal contribution.
- Amounts use local `cost_per_call` estimates, not invoices. Credit bundles, monthly minimums, retries and variable billing may differ.
- Results can be misleading with small or nonrepresentative samples. Review denominators and Wilson intervals before making changes.
- Unknown-price attempts are reported separately; they are not silently included as zero.
- A favorable cost ratio does not establish general accuracy, deliverability or commercial conversion.

## Verification

Python syntax compilation and `git diff --check` are used. No automated tests, benchmark data uploads, or paid provider calls were run.

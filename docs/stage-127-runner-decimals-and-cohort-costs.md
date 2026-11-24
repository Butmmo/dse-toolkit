# Stage 127: Decimal runner fields and cohort-bound spend reporting

## Grid enrichment error from the provided screenshot

The PC runner rejected `minimum_identity_score: unknown field type float`. The grid HQ Tool catalog declares this and several other decimal controls as `float`, while `bridge/runner.py` accepted `bool`, `int`, `choice`, `date`, `url`, `text`, and `file` only. As a result, the request failed during runner-side form validation before `dse.py grid enrich` started. The paired waterfall preflight also declares its spend ceiling as `number`, which had the same unsupported-type problem.

The runner now accepts both `float` and `number`, parses them as finite decimals, applies configured minimum/maximum bounds, and rejects NaN and infinity. This fixes the identity-score error while retaining fractional thresholds and spend limits across existing HQ Tools forms.

## Waterfall experiment cohort and cost reporting

Live A/B enrichment outputs now contain exactly the rows in the receipt-approved bounded cohort. Previously, rows beyond `--max` could remain in the output files even though the approval receipt covered only the first capped rows; pairing then compared an over-cap output against a capped manifest and rejected it.

Send Desk outcome JSON and Markdown now include receipt-bound provider attempt cost summaries by variant. The scorer validates each A/B result CSV hash, approval and config IDs, row count, stable cohort fingerprint, and row metadata before summing recorded API attempts and declared configured prices. It reports unknown-price calls, the approved per-variant maximum, combined observed estimated cost, and an integrity status. The report explicitly describes these as configured-price estimates, not invoices, and explains that A/B enrichment ran on the full cohort while outreach results reflect one assigned variant per lead; it does not mislabel the figures as cost per win.

Validation performed: Python compilation of the runner and enrichment modules; CLI help; catalog JSON parsing; and `git diff --check`. No paid-provider requests were made.

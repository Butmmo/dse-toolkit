# Stage 39: Human-reviewed enrichment evaluation harness

## What changed

Added a local CLI harness to turn an enriched CSV's `field_results` contract into a human-review worksheet and score the completed labels by field. The sheet carries the result value, acceptance status, source URL, identity cues, freshness, verification metadata, declared cost and selected lead context, followed by explicit review columns for:

- value correctness;
- identity correctness;
- evidence adequacy;
- freshness acceptability.

The scorer reports accepted-result coverage, labeled yes rates with Wilson 95% intervals, review response counts, and declared costs. Prepared sheets retain Engine path, enrichment profile and research lane when available. Stages 53–60 add stratified sampling, review calibration, source breakdowns, uncertainty flags, and paired source comparisons across four quality dimensions.

## Use

From the toolkit folder:

```powershell
python dse.py eval-enrichment prepare my-lists\enriched.csv
```

Review the generated `*-enrichment-review.csv`. For the four review columns, enter `yes`, `no`, or `unknown`; reserve blank for not reviewed. Add a short reason in `review_note` when useful. Keep the generated `evaluation_id` and `field` intact. See [Stage 54](stage-54-benchmark-review-rubric.md) for definitions and adjudication guidance.

Then score the reviewed sheet:

```powershell
python dse.py eval-enrichment score my-lists\enriched-enrichment-review.csv
```

The JSON report is written beside the reviewed sheet. `--out` can select a different output path in either command.

## Interpretation and limits

- Coverage means the share of result records whose status is `accepted`; it does not mean those records are true.
- Human label rates only describe rows a reviewer labeled. They are not a representative accuracy claim unless the sample was selected and reviewed appropriately.
- Cost is summed only when the field result declares a numeric amount and currency. An estimate is not a provider invoice; unknown amounts stay unknown.
- Freshness acceptability is a reviewer judgment. The harness records and reports the observed `freshness_status` separately; it does not impose one universal age threshold across fast-changing and stable fields.
- The evaluator does not call providers, search the web, modify source data, infer private traits, or write findings back to a Ledger.

Start with a small stratified, manually reviewed set for two or three paths and include accepted, rejected, not-found and ambiguous identity cases. Store real review sheets locally with appropriate access control; do not commit lead data or personal contact information to Git. Expand only after agreeing on field-specific definitions of “correct,” “adequate evidence,” and “fresh enough.”

## Files

- `dse/enrichment_eval.py`: prepare and score logic.
- `dse.py eval-enrichment`: CLI entry point.

No Supabase SQL is needed. No automated test suite was added or run in this slice.

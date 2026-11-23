# Stage 59: Compare sources on the same lead and field

## What changed

The evaluation JSON now includes `paired_source_comparisons`. It compares each field/source pair only inside the same Engine path, enrichment profile, and research lane, then matches results by `source_row` (the sampled lead). It reports each source's result coverage over that cohort, shared cases, matched adjudicated yes/no labels, value-correct wins, ties, paired rate difference, and unknown/unlabeled or duplicate-result exclusions. `minimum_labeled_met` uses the same `--min-labeled` setting as the Wilson interval flags.

Paired rows make source comparisons less sensitive to different leads being enriched by different providers. Keeping path, profile, and lane separate also avoids mixing distinct research strategies. The comparison uses only `value_correct` adjudication. Two sources both labeled yes or both labeled no count as ties. Unknown/missing labels and cases with multiple result rows from a source for the same lead/field/cohort are excluded from the matched quality rate and counted separately.

Stage 60 expands the paired comparison to identity correctness, evidence adequacy, and freshness as separate dimensions.

## Use

Use the normal reviewed scoring command after adjudication:

```powershell
python dse.py eval-enrichment score my-lists\reviewed-benchmark.csv --min-labeled 20
```

Inspect `paired_source_comparisons` in the JSON report. Confirm both sources have usable result coverage, read the shared and matched denominators, and inspect the exclusions before interpreting win counts or the paired rate difference. Use `by_field_and_source` for the full per-source metrics and cost details.

## Limits

These are descriptive comparisons, not a randomized provider trial or a general ranking. Matched cases can still have selection bias; returned results can differ in evidence availability and cost; small samples are noisy. A source's `name` can be an evidence source rather than a provider. The paired rate difference describes only adjudicated value correctness, not identity, evidence adequacy, freshness, business fit, reply rate, revenue, or causal impact. Use the confidence intervals and minimum-count flags as context, not promotion rules.

No SQL migration is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: same-lead/source comparison metrics.
- `docs/lead-enrichment/stage-57-field-source-comparison.md`: per-source cohort report.

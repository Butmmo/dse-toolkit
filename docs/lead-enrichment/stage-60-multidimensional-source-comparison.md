# Stage 60: Compare source quality across review dimensions

## What changed

`paired_source_comparisons` now includes a `dimensions` object for each matched field/source/cohort pair. It separately compares adjudicated:

- `value_correct`
- `identity_correct`
- `evidence_adequate`
- `freshness_acceptable`

Each dimension has its own matched denominator, source A/B wins, ties, yes rates, paired rate difference, unknown/unlabeled and duplicate exclusions, and minimum-count flag. A reviewer can judge one dimension while marking another unknown without discarding the usable labels. Existing top-level value-correctness metrics remain as compatibility aliases.

## Use

Score a paired review file after both reviewers have independently labeled and a reviewer has filled the adjudicated columns:

```powershell
python dse.py eval-enrichment score my-lists\reviewed-benchmark.csv --min-labeled 20
```

In each `paired_source_comparisons` entry, inspect `dimensions.value_correct`, `dimensions.identity_correct`, `dimensions.evidence_adequate`, and `dimensions.freshness_acceptable`. Compare their individual denominators and exclusions; do not assume all four dimensions have equal review coverage.

## Limits

The comparisons remain descriptive. Value-correctness rates do not establish identity, and evidence or freshness agreement does not guarantee business usefulness. Matched source cases are not randomized experiments, and separate dimensions can have very different unknown rates. Use path/profile/lane cohorts, the source coverage counts, Wilson intervals in the single-source summaries, and the manual evidence before changing a waterfall.

No SQL migration is needed. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: paired source metrics for all four reviewed dimensions.
- `docs/lead-enrichment/stage-59-paired-source-comparison.md`: matched comparison design and limits.

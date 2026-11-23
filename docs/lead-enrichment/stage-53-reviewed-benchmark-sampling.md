# Stage 53: Prepare a stratified enrichment benchmark

## What changed

`prepare` now carries Engine path, enrichment profile and research lane into the local field-review worksheet and `score` reports metrics by path/profile/lane as well as by field. The new `sample-ledger` command chooses a reproducible sample of whole leads stratified by Engine path and profile. It keeps every available field-result row for each selected lead, preventing highly enriched leads from counting as multiple sampled leads. Review labels are cleared in the sample; source/context columns and evaluation IDs are retained.

## Use

Export a Ledger grid with `field_results` visible, then prepare the field-review worksheet:

```powershell
python dse.py eval-enrichment prepare my-lists\ledger-export.csv
```

Select up to 40 leads (default), keeping all field results per lead:

```powershell
python dse.py eval-enrichment sample-ledger my-lists\ledger-export-enrichment-review.csv --leads 40 --seed 42
```

The command defaults to stratifying by `engine_path,enrichment_profile`; `--stratify` accepts other prepared-sheet columns. If the requested size is smaller than the number of strata, the command stops and asks for a larger sample or fewer strata. Use the same seed and same input to reproduce selection.

Review the four fields (`value_correct`, `identity_correct`, `evidence_adequate`, `freshness_acceptable`) with `yes`, `no`, or `unknown`. “Unknown” means the evidence is insufficient to judge; “no” means evidence supports a failed claim. Leave blank only when the reviewer has not reviewed the row. For freshness, judge against the field's expected update rhythm, not one universal age threshold. Use `review_note` for a concise reason and keep `evaluation_id`, `source_row`, and `field` intact. The scorer excludes unknown from yes/no rates and reports unknown, blank, and invalid labels separately. Then score:

```powershell
python dse.py eval-enrichment score my-lists\ledger-export-enrichment-review-benchmark-sample.csv
```

## Interpretation and limits

This is a practical first audit sample, not a statistically representative gold set. A random seed makes selection reproducible, not unbiased. Verify claims against source pages and appropriate first-party evidence; candidate snippets alone may be inadequate. Reviewers should agree on field-specific definitions and independently adjudicate disagreements before using metrics to change a waterfall. Do not commit real lead data or benchmark sheets to Git. The sampling and scoring commands run locally and do not send data to an AI or provider. No SQL migration is needed.

No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: cohort-aware worksheet metadata, lead-level sampling and cohort score summaries.
- `dse.py eval-enrichment`: CLI entry point.
- `docs/lead-enrichment/stage-54-benchmark-review-rubric.md`: shared label definitions and adjudication guidance.

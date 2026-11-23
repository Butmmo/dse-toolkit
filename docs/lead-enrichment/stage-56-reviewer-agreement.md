# Stage 56: Measure reviewer agreement

## What changed

`pair-reviewers` makes a paired review sheet from a prepared or sampled evaluation worksheet. It adds independent `reviewer_a_*` and `reviewer_b_*` labels, notes for each reviewer, and `adjudicated_*` fields with an adjudication note. It clears the existing single-review labels to avoid accidental reuse.

When scoring a paired sheet, the evaluator prefers adjudicated labels for the benchmark rates, reports reviewer response states separately, and calculates per-dimension observed agreement and Cohen’s kappa for rows where both reviewers supplied a recognized yes/no/unknown label. It also includes a confusion matrix and the number of excluded missing or invalid pairs.

## Use

Start with the reproducible sample from Stage 53 and create the independent review template:

```powershell
python dse.py eval-enrichment pair-reviewers my-lists\ledger-export-enrichment-review-benchmark-sample.csv
```

Give identical copies to the reviewers, or split responsibility so each reviewer cannot see the other's entries. Merge their labels by `evaluation_id` only after both finish. Resolve disagreements into `adjudicated_value_correct`, `adjudicated_identity_correct`, `adjudicated_evidence_adequate`, and `adjudicated_freshness_acceptable`; note why in `adjudication_note`. Do not change `evaluation_id`, `source_row`, or `field`.

Score the merged, adjudicated file:

```powershell
python dse.py eval-enrichment score my-lists\ledger-export-enrichment-review-benchmark-sample-paired-review.csv
```

The JSON report's `reviewer_agreement` entries show comparable row count, exclusions, observed agreement, expected agreement, Cohen’s kappa, and the yes/no/unknown confusion matrix. Benchmark yes rates use adjudicated labels and exclude unknown. If no adjudicated labels are entered, the benchmark rates remain unlabelled rather than treating either reviewer as truth.

## Limits

Agreement does not establish correctness. Reviewers can agree and both be wrong; inspect source evidence and adjudicate against the rubric. Cohen’s kappa can be unstable with small samples or highly imbalanced labels. Always report its denominator and the confusion matrix, and use it as a calibration aid rather than a waterfall promotion threshold. No lead data should be committed to Git. No SQL migration is needed.

No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: paired review preparation, adjudicated scoring, and agreement statistics.
- `docs/lead-enrichment/stage-54-benchmark-review-rubric.md`: label definitions and adjudication guidance.

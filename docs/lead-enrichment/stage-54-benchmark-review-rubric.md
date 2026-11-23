# Stage 54: Calibrate benchmark review labels

## Purpose

This rubric makes manual enrichment reviews more consistent before scores are used to change providers or waterfall order. Apply labels per field result, not once per lead.

## Labels

Use `yes`, `no`, or `unknown` for each review dimension. Use blank only when the reviewer has not reviewed the row. The scorer reports all five states (`yes`, `no`, `unknown`, `blank`, `invalid`); only yes/no labels contribute to the yes rate.

### `value_correct`

- **Yes:** the returned value agrees with a source that directly supports this field for the target entity.
- **No:** the value conflicts with reliable evidence, is materially malformed, or is clearly assigned to the wrong field.
- **Unknown:** available sources do not confirm or contradict the value.
- Example: a company phone listed on the company’s current contact page supports yes; a number appearing only in an unrelated directory with no matching entity evidence is unknown.

### `identity_correct`

- **Yes:** the source belongs to the intended person or business, with enough matching identifiers to distinguish similarly named entities.
- **No:** evidence identifies a different person or business, or a material identity mismatch is visible.
- **Unknown:** source identity cannot be established from the available identifiers.
- Example: a profile matching the decision maker’s name, current employer, and role supports yes; name-only similarity is unknown, not a pass.

### `evidence_adequate`

- **Yes:** the cited source is accessible and directly supports the claim; record the source URL and relevant context in `review_note` when useful.
- **No:** the cited source is missing, inaccessible, unrelated, stale for a time-sensitive claim, or does not support the returned value.
- **Unknown:** source evidence was not retained or cannot currently be inspected.
- Search snippets are discovery hints. For consequential claims, inspect the underlying page or first-party source.

### `freshness_acceptable`

- **Yes:** evidence is recent enough for the natural update cycle of this field and the intended use.
- **No:** evidence is demonstrably too old for a volatile field or conflicts with newer reliable evidence.
- **Unknown:** there is no usable publication/observation date or no basis to judge the field’s expected update rhythm.
- Do not apply one age cutoff to every field. A legal entity name changes less often than a job title, hiring signal, or social post.

## Reviewer calibration and adjudication

Stage 56 adds a `pair-reviewers` command that creates separate reviewer columns and adjudication columns. Two reviewers should label independently without seeing each other’s labels. Compare disagreements by dimension and field, then record the resolved label in `adjudicated_*` and the reason in `adjudication_note`. If evidence does not resolve a disagreement, retain `unknown`; do not force a yes/no. The evaluation report includes raw agreement and Cohen’s kappa where paired labels exist. These statistics are descriptive, especially for small samples; they do not replace evidence review.

Add field-specific clarifications here before reviewing the remaining sample. Re-review changed labels after a rubric change, and preserve the sample seed and source export for reproducibility.

Treat the benchmark as directional while counts are small. Report the labeled denominator and unknown share alongside each rate. Do not infer provider superiority from a handful of fields or from cohorts with materially different lead mixes.

## Files

- `dse/enrichment_eval.py`: reports response-state counts and excludes `unknown` from yes/no rates.
- `docs/lead-enrichment/stage-53-reviewed-benchmark-sampling.md`: sampling and review workflow.

# Stage 75: Paired agreement and result availability

## What changed

Paired source comparisons now make two useful context measures explicit:

- `lead_result_availability` partitions the cohort leads into both sources returned a result, only source A, only source B, or neither. It also reports each share of the cohort.
- Each reviewed dimension reports `reviewed_agreement_rate` and `reviewed_disagreement_rate` among the matched leads where both sources have explicit yes/no labels. The existing win, tie, and per-source rates remain available.

## Interpretation and limits

Result availability counts a source result row, not whether the result was accepted, useful, or correct. Agreement and disagreement rates apply only to paired, explicitly reviewed labels. A tie means both labels were the same; it does not independently establish factual truth. Use these measures alongside coverage, reviewed quality, and provider-attempt cost rather than as a standalone provider ranking.

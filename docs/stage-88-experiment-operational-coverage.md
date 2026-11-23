# Stage 88: Operational coverage in waterfall experiments

Completed A/B experiment comparisons now report output status counts for each variant on the same leads with exactly one output row per variant. They include accepted-result coverage for A and B, the paired acceptance difference, acceptance wins/ties, and a reproducible lead-pair bootstrap interval. The Markdown decision brief summarizes accepted coverage alongside reviewed quality and cost.

Coverage is the share of paired outputs with status `accepted`; it is not human-verified correctness. Other statuses remain visible in the per-variant counts. Duplicate outputs and leads missing either variant are excluded from the paired operational comparison and remain visible in the existing duplicate and availability counts. Use coverage together with human review, evidence quality, freshness, and cost; none of these summaries selects a provider automatically.

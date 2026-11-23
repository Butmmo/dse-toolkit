# Stage 86: Score completed waterfall experiments

Experiment-tagged enrichment rows now preserve a stable `waterfall_experiment_lead_id` into the prepared review sheet. The scorer groups tagged rows by experiment, field, Engine path, profile, lane, lead ID, and A/B variant, then compares explicitly yes/no reviewed labels for the same leads. It reports variant output coverage, paired quality rates and differences for all review dimensions, exclusions for duplicate or incomplete pairs, config hashes, and reproducible lead-pair bootstrap intervals.

The JSON report adds `waterfall_experiment_comparisons`; the optional Markdown brief includes a completed-experiment summary. Prepare both variant outputs as review sheets, combine them for human review, then run `eval-enrichment score`. The stable lead ID is taken from `waterfall_experiment_lead_id`, `source_row`, `lead_id`, or `id`, with an input-row fallback when the same manifest is used for both variants.

This is a paired descriptive benchmark, not a randomized population trial or automatic provider-selection feature. Review output coverage; use identical leads, controls, budgets, and acceptance rules; keep outreach disabled until both variants have been adjudicated.

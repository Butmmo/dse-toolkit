# Stage 79: Uncertainty for paired provider cost differences

Each paired source and currency comparison now includes a percentile bootstrap interval for the mean estimated cost difference (source A minus source B). The bootstrap resamples the same matched lead cost pairs used for the point estimate, with replacement. The interval uses the existing `--paired-bootstrap-reps` and `--paired-bootstrap-seed` options and is also summarized in the optional Markdown decision brief.

Only leads with exactly one result for each source, explicit yes/no value-correctness reviews for both results, and known priced provider attempts from both sources in the currency are included. Currencies remain separate. A positive difference means source A has higher estimated cost in this cohort; a negative difference means source B has higher estimated cost. An interval spanning zero does not show a clear cost direction.

These are configured cost estimates, not invoices. The interval describes variation among the priced matched leads; it cannot correct selection bias, missing prices, or differences in cost configuration. It is descriptive and is not a provider-selection rule.

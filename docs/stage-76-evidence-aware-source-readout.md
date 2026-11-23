# Stage 76: Evidence-aware paired source readout

## What changed

Paired source comparisons now include a concise `decision_readout` with a low-sample caution status, the direction supported by the paired value-correctness interval, and other reviewed dimensions whose point estimates move in the opposite direction. It explicitly records that the report does not select a provider automatically.

For each currency, paired provider-cost comparisons now also report each source’s value-correctness rate on the same priced matched subset. A short descriptive note states whether the lower-estimated-cost source had no lower reviewed correctness or had lower reviewed correctness on that subset. Equal or unavailable cost direction is reported as unclear.

## Interpretation and limits

These readouts summarize this benchmark cohort only. The minimum label threshold is a caution flag. Interval direction is descriptive sampling evidence and does not establish a provider’s general superiority. The priced subset may differ from the full matched cohort. Costs are configured estimates, not invoices. The readout is meant to help users inspect trade-offs, not to replace business judgment or automate provider selection.

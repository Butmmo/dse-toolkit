# Stage 89: Combined experiment decision readout

Each completed waterfall experiment comparison now has an `experiment_readout` that summarizes reviewed-correctness interval direction, accepted-coverage interval direction, lower-estimated-cost variant by currency, and any visible trade-offs. It applies the configured minimum-reviewed caution threshold and reports a low-sample status when the paired value-correct review count is below it. The Markdown brief includes the same summary.

The readout keeps quality, coverage, and cost as separate signals; it does not form a weighted score or select a variant. Trade-offs are explicit when quality direction conflicts with accepted coverage or a paired cost direction. A missing or zero-spanning interval yields no clear direction. Estimates and interval results describe this reviewed cohort only; they are not proof of general provider performance or invoices.

# Stage 80: Paired cost input quality

Paired source cost comparisons now accept an attempt estimate only when its provider metadata records at least one call, a currency, and a finite nonnegative estimate. Missing currency or estimate is counted as an unknown-price call. Non-numeric, non-finite, or negative estimates are counted as invalid-price calls and excluded. These values are never silently converted to zero.

Each paired source comparison reports these exclusions in `paired_cost_input_quality`, scoped to leads that returned exactly one result per source and have explicit yes/no value-correctness reviews for both results. Currency-level cost entries also include the same exclusion counts for context. If either source lacks known prices in a currency, that lead does not enter that currency’s paired cost means or bootstrap interval.

This validates the shape and basic plausibility of estimates, not the accuracy of provider pricing. Valid values remain configured estimates, not invoices.

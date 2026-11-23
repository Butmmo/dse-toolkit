# Stage 73: Paired source cost comparisons

## What changed

Paired source comparisons now include estimated provider-attempt cost by currency for leads where both sources returned exactly one result, both results have an explicit yes/no `value_correct` review, and both have priced attempts in that currency. For each source pair, the report gives the matched lead count, mean estimated cost per matched lead for each source, and the A-minus-B difference.

This complements the existing paired quality outcomes: it helps identify cases where one source appears less costly on the same reviewed lead set, while keeping the quality comparison and cost comparison on comparable observations.

## Interpretation and limits

Costs are configured estimates, not invoices, and include failed attempts where recorded in the source metadata. Currency groups are kept separate. Leads missing either source’s price are omitted from that currency’s paired cost comparison. The report does not infer that a cheaper source is better, nor does it prove quality or business outcomes. Review selection, provider pricing configuration, and duplicate-domain shared-cost attribution affect results.

The new output is `paired_provider_attempt_cost_by_currency` on each item in `paired_source_comparisons`.

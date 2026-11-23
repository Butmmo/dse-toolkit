# Stage 87: Waterfall experiment cost efficiency

Completed A/B waterfall comparisons now include provider-attempt cost summaries by currency on the same reviewed leads where both variants have valid priced attempts. For each currency the report gives mean estimated spend per paired lead, the A-minus-B lead-pair bootstrap interval, and estimated cost per explicitly reviewed-correct result for each variant with its denominator. Unknown-price and invalid-price calls are counted separately and excluded rather than treated as zero.

The Markdown decision brief also shows paired spend and cost-per-reviewed-correct figures. These remain configured estimates, not invoices. Cost-per-correct denominators count only explicitly yes-labeled results with known priced attempts in the paired currency. Small or selected reviewed samples can produce unstable or biased results; intervals describe sampling variation only and do not establish provider superiority.

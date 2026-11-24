# Stage 128: Attribute enrichment estimates to assigned outreach

## What changed

Send Desk outcome reports now distinguish two different amounts:

- Full A+B provider attempt estimates, where both variants enriched the full approved cohort.
- Assigned outreach estimates, where each variant's recorded provider charges are attributed once to each normalized company domain in that variant's verified assigned-lead CSV.

After the assignment CSV and its sidecar, source cohort, receipt, and Send Desk roster have passed the existing integrity audit, the report shows the attributable estimate and estimated enrichment cost per logged sent, replied, booked, and won unique lead. It includes assigned domain coverage, domains with recorded attempts, unpriced calls, and full-run calls that lacked a company domain.

Domain aggregation avoids charging the same cached company-level provider call once for every repeated lead at that company. Private per-domain working data is removed before the report JSON is written; no raw domain-level cost map is exposed in the Engine report.

## Interpretation limits

These are configured-price estimates, not vendor invoices. Per-outcome values divide known assigned-domain enrichment cost by the explicit logged unique-lead outcome count. They do not measure profit, ROI, or total customer acquisition cost, and they omit unpriced provider calls and non-enrichment costs. The complete A+B amount remains visible separately so it is not mistaken for the cost of only the leads assigned to one variant. No cost-per-outcome attribution is emitted for an assignment cohort that fails its audit.

## Validation

Python compilation and `git diff --check` passed. No provider calls were made. No tests were run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout. The existing local `packs/automation.json` change was preserved.

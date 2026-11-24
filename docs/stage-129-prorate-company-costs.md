# Stage 129: Prorate company-level enrichment cost

## What changed

Stage 128 attributed the entire cost recorded for a company domain to a variant whenever that domain appeared in that variant's assigned lead file. If a company's contacts were split between A and B, that could make both variants appear to bear the full company cost.

Assigned cost now allocates each verified variant-run domain amount by the share of source leads for that domain assigned to that variant. Example: if a domain has four source leads and one was assigned to A, A receives one quarter of that domain's recorded A-run cost. The remaining portion stays with the experiment-run cost rather than being duplicated into A's assigned lead cost. The same calculation is performed independently for B.

The outcome report records the assigned and source lead counts in cost-bearing domains and their aggregate share. Full-run call counts, unknown-price calls, and domainless call counts remain contextual, explicitly unprorated figures; the cost estimate excludes unknown-price and domainless amounts. Assignment and provider-cost integrity checks still gate these calculations.

## Interpretation limits

This is a proportional allocation model for shared company-level enrichment costs, not provider billing data at contact granularity. Provider call and unknown-price counts are shown as full-run context and are not fractionally apportioned. Per-outcome amounts remain configured-price estimates, not invoices, profit, ROI, or total acquisition cost.

## Validation

Python compilation, CLI help with UTF-8 console mode, and `git diff --check` passed. No provider calls were made. No tests were run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout. The local `packs/automation.json` edit was preserved.

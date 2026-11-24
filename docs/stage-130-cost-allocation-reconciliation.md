# Stage 130: Reconcile experiment spend with assigned outreach

## What changed

When both A/B provider-cost audits and both assigned lead rosters verify, the Send Desk outcome report now reconciles:

- Known-price estimated cost of the full A+B enrichment runs.
- Cost allocated to the verified leads assigned to A and B, using Stage 129's per-domain lead-share proration.
- The remaining known-price run estimate that was not allocated to assigned outreach.

This reconciliation is limited to provider costs with a recorded currency and company domain. It explicitly reports that unknown-price calls and domainless costs are excluded. If either integrity audit does not pass, the reconciliation says it is unavailable and gives no calculated remainder.

The Markdown brief presents this summary beside the approval receipt and the variant outcome metrics. The JSON records the full, allocated, and remaining amounts by currency, plus its audit status and exclusions.

## Interpretation limits

The remainder is an unallocated known-price experiment-run estimate, not automatically waste or overhead. It can include the portion of full-cohort provider spend not assigned to outreach under the proportional model. All values are local configured-price estimates, not invoices, profit, ROI, or total acquisition cost.

## Validation

Python compilation, CLI help with UTF-8 console mode, and `git diff --check` passed. No provider calls were made. No tests were run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout. The local `packs/automation.json` edit was preserved.

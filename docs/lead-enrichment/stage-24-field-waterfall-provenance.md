# Stage 24: Per-field enrichment waterfall audit

## What changed

The lead enrichment CSV now includes an `enrichment_audit` JSON column. For each generated contact or business field, it records whether a value was selected, its source and evidence URL when captured, and whether the evidence remains unverified. Email entries also show the input, website, optional provider and guess rungs considered, including a rejected input email when its domain does not match the business website. Guessed email patterns remain explicitly unverified and are never treated as selected email results.

The audit lists the actual waterfall steps run for that website and records optional provider API-call and cache-hit counts for the website result. The summary still reports run totals. Duplicate input rows for the same domain share one website result and its lookup counts. Provider configurations do not declare reliable monetary prices, so the audit leaves currency cost unknown instead of inventing a cost. Website page provenance is now captured for phone, contact form, booking, social profile, technology and description findings.

The HQ tool catalog description now advertises the audit and lookup counts so users know what the CSV contains.

## Boundaries

This stage instruments the existing website-first flow and its optional configured email provider. It does not add new third-party providers, assert email deliverability, or turn search/social hints into verified facts. Provider cache hits are reported separately from actual API calls.

## Verification

Run Python compilation for the touched Python files, parse the generated catalog JSON, and inspect the diff. No live enrichment, paid provider request, database change, or automated test suite is run as part of this stage.

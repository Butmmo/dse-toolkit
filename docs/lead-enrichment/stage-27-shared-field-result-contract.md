# Stage 27: Shared field-result contract

## What changed

The toolkit now emits a common `dbi.field-result.v1` envelope for website enrichment, Herald signal research and Presence results. Each result can carry a field/value, status, source and URL, observed and publication times, freshness, identity subject/match/strength/score, verification state/method, cost units and quantity, a reason for a miss, alternative candidates, and metadata.

The Python builder lives in `dse/field_results.py`; the language-neutral JSON Schema is `dse/field-result.schema.json`. Existing CSV columns and the legacy website `enrichment_audit` remain for compatibility. The new `field_results` JSON column combines website, Herald and Presence lanes; a rerun refreshes its own lane while preserving findings from the other lanes. The Engine CSV importer and generated Send Desk list now carry the field results forward.

Website checks distinguish first-party page evidence, user-supplied values and configured providers. Email deliverability is not claimed as verified. Herald and Presence search snippets are `candidate` results with `unverified_search_snippet` status; dates and identity cues retain their existing heuristic limitations. Unknown provider pricing remains unknown. Local website checks and DuckDuckGo result lookups report zero external provider fee; this does not estimate PC electricity or user time. Brave monetary cost is left unknown.

## Boundaries

This is the data contract and output wiring, not a dynamic provider waterfall, native Ledger cell viewer, or calibrated confidence model. Existing CSV fields remain intact; `field_results` is additive. No third-party provider is added or called by this change.

## Verification

Compile the changed Python modules, parse the catalog and JSON Schema, and inspect the diff. No live web searches, paid calls, or automated tests are run in this slice.

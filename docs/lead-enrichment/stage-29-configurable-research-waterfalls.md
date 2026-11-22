# Stage 29: Configurable and measurable research waterfalls

## What changed

Herald and Presence public-search research now use an observable query-waterfall record. Existing prioritized query sequences remain in their established order, while users can set a per-lead search-query budget and minimum identity-match score. A zero budget is a safe way to produce a no-search run. Defaults preserve prior search behavior: Herald allows 12 queries per lead and Presence allows its three current queries; the default score threshold is zero, with the existing identity matching rules still in force.

Each query rung records whether it ran or was skipped by the budget, search calls, results returned, unique results retained, duplicates, identity rejections, role rejections where relevant, score rejections, and errors. Summary totals are saved in `herald_search_waterfall` or `presence_search_waterfall` CSV fields. The same record is attached to the relevant `company_signal_evidence`, `person_signal_evidence`, `presence_company_signal`, or `presence_person_signal` shared field-result metadata.

HQ Tools now exposes these controls for both Herald research and Presence social research. A score is an identity-match heuristic, not a probability or confirmation of account ownership. A search result remains a candidate requiring source review.

## Safety and history behavior

A Presence run that skips a query because of its budget is marked as a partial comparison. It does not save that incomplete pass as a complete history snapshot, and it does not treat previously seen links as confirmed disappearances. Search errors continue to produce partial comparisons as before.

The budget counts search requests initiated by the toolkit, not results, provider credits, or money. DuckDuckGo remains the default. Brave requests use the user's local key and its own allowance; this stage reports query counts without inventing a monetary estimate.

## Scope

This extends configuration and measurement from email waterfalls to public company/person and Presence signal searches. It does not yet add vendor waterfalls or provider selection for phone, person identity, or company firmographics. Those fields need concrete adapters and field-specific verification rules before provider switching can be safely automated.

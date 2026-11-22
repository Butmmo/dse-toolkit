# Stage 31: Herald source-backed monitoring

## What changed

- Herald research now stores a local 180-day source snapshot keyed by a SHA-256 hash of stable business, website, contact, and email identifiers. The local history does not store clear lead names or emails.
- Snapshots retain each source URL, subject, title, snippet fingerprint, publication date, and signal category. The original CSV still carries full source URLs, titles, snippets, identity cues, and observed time for review.
- Repeated complete searches compare source links and records, producing `herald_comparison_status`, `herald_change_summary`, `herald_new_source_urls`, `herald_changed_source_urls`, `herald_not_returned_urls`, and `herald_previous_checked_at`.
- A source record is marked changed when its title, snippet fingerprint, or publication date differs. A missing result is called “not returned,” not deleted.
- Search errors or budget-skipped queries mark a run partial. Partial runs do not replace the complete baseline or treat absent links as not returned. The first complete check establishes a baseline.
- The shared `field_results` contract now includes `signal_source_monitoring`, and live Ledger grid enrichment exposes the monitoring summary and URL fields as reusable Herald columns.
- Presence keeps its existing equivalent source comparison flow.

## Limits

This monitors changes visible through the public-search result records; it does not poll or archive the source websites or social platforms directly. Search index variation can change a snippet or omit a link, so these are review alerts, not proof that a post or business changed. Publication dates remain heuristic. No sensitive personal traits are inferred.

## Validation

Python syntax compilation, catalog JSON parsing, and `git diff --check` passed. No live searches, tests, or paid provider calls were run. No Supabase SQL is required.

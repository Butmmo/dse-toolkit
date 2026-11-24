# Stage 150: Link monitor cues to source records

The normalized Herald and Presence monitoring review now enriches each source reference with the retained signal's `record_id`, when that source URL was retained in the current run. Each reference carries its cue category, canonical URL fingerprint, source URL, and stable record ID, so review interfaces can connect a monitoring cue to the corresponding field-result evidence record.

If a URL is referenced by a cue but no retained signal record matches it, `record_id` is an empty string; the cue remains visible and still requires a user to open and verify the URL. Existing field-result candidates and lane-specific payload keys remain unchanged.

Validation: Python syntax compilation, toolkit CLI help, catalog JSON parsing, and `git diff --check`. No tests were run.

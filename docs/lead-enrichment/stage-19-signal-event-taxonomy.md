# Stage 19: signal-event taxonomy and role guidance

## What changed

Lead enrichment now classifies matching phrases in company and person search snippets, and in the lead CSV's separate person/company signal fields. Categories cover hiring, funding, expansion, product launches, leadership changes, technology/security, revenue growth, operations, compliance, customer trust, and franchise growth.

Each event includes the subject, matched cue patterns, suggested role families, and available source ID, host, URL, publication date, and freshness. CSV-supplied signals are marked `lead_csv_input`; search evidence retains its source metadata. The output is stored in `herald_signal_events` and carried through the importer into Engine rows for downstream tools.

Role inference also uses the event taxonomy, so signal-based searches can include plausible role families beyond the earlier keyword checks. An explicit user-selected role remains authoritative.

## Interpretation limits

These are phrase matches and targeting suggestions, not verified events, company classifications, confirmed people, or calibrated confidence scores. Search snippets can be incomplete or stale. Review the linked source before using a cue in outreach. The taxonomy does not independently browse social networks or add a search provider.

## Checks

Python syntax compilation and `git diff --check` passed. No full test suite was run. No Supabase SQL is required.

# Stage 10: identity review summary

## What changed

Each processed lead now receives a `herald_identity_summary` CSV field with separate company and person sections. Each section reports the number of matched sources, counts by identity strength, the best heuristic match score, and the match types. The enrichment Markdown run report also counts leads with at least one strong identity match.

The summary is carried through the engine importer and into Send Desk's generated rows so a reviewer can inspect match quality alongside the source evidence and drafted outreach.

## Interpretation

This is an at-a-glance review aid, not an identity verification or probability. A missing or zero count means the current search did not retain a source that met the matching threshold. Review source links and snippets before relying on any claim or contacting a person.

No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: per-lead summary and run-report count.
- `dse/importer.py`: preserve the summary on import.
- `dse/engines.py`: pass the summary to Send Desk output.

# Stage 15: evidence freshness

## What changed

Herald now looks for explicit ISO/month-name dates and clearly relative dates (such as “3 weeks ago”) in public result titles and snippets. Each source records the extracted date, date precision, matched date text, age in days, and a freshness label (`recent`, `aging`, `stale`, `future_dated`, or `undated`). Retrieval time remains separate and is never treated as the publication date.

Dated evidence contributes up to 10% of a decision-maker candidate's heuristic review ordering. Undated sources do not receive a freshness bonus or penalty. The run report counts dated sources and sources marked stale. AI drafting receives the freshness metadata and is instructed not to describe old or undated evidence as recent; the outreach evidence ledger also includes freshness details.

## Date and score bands

- Recent: up to 90 days; freshness score 1.00.
- Aging: 91 to 365 days; score 0.55.
- Stale: over 365 days; score 0.15.
- Future-dated: score 0.00.
- Undated: freshness is unknown and omitted from candidate score weighting.

## Limits

Date extraction is heuristic and uses only explicit or relative text in returned snippets/titles. A date can refer to an event or page update rather than the exact claim; the original source should be opened before relying on it. Search time is not publication time. No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: date extraction, freshness metadata, and run counts.
- `dse/classification.py`: freshness-aware candidate ordering.

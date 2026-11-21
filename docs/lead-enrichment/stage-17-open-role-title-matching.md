# Stage 17: open-ended role title matching

## What changed

Custom decision-maker roles now match normalized title variants instead of requiring the exact phrase supplied by the user. The matcher treats common C-suite expansions as their acronyms and normalizes senior/executive vice president titles and filler words such as “of” and “the.” For example, a custom target of “VP of Sales” can match “Vice President Sales,” and “Director of Engineering” can match “Engineering Director.”

The same matcher is used for role evidence assessments and candidate role labels, so ranking and role review agree. Users can target uncommon roles in the free-text field without adding every title to the fixed role picker.

## Limits

This uses conservative token containment, not a complete ontology. It can miss unusual abbreviations and may match a role phrase in a snippet that is not the page subject; source review is still required. The aliases do not verify a current position. No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/classification.py`: common title normalization and custom role matching.

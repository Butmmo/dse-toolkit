# Stage 25: Presence signal identity and freshness

## What changed

Presence social-search results now carry separate company/person subject labels, matched company/contact terms, source host and platform cue, plus a heuristic identity match score and strength. Scores are explicitly labeled as heuristics, not probabilities. Personal profile results are kept distinct from business profile/post results.

The existing publication-date parser now runs for Presence snippets too. Where a date is found, the result includes publication date, precision, evidence phrase, age, freshness status and score. Search retrieval time remains separately recorded; retrieval time is not treated as publication time. The run summary reports dated and stale result counts. The tool catalog advertises these fields.

## Boundaries

Presence still searches public professional/business results only and drafts or sends no outreach. Search snippets are not verified social profiles, customer sentiment or reputation. Undated results remain undated; no recency is inferred from when the search ran. Matching scores are review cues, not identity proof.

## Verification

Compile the changed Python files, regenerate and parse the toolkit catalog, and inspect the diff. No live search is made and no tests are run in this slice.

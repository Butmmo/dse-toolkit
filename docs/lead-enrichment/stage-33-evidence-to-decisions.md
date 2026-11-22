# Stage 33: Connect evidence to Ledger decisions

## What changed

- Herald live-grid enrichment now writes a compact `herald_evidence_decisions` long-text record on each processed row. It contains the run time/status, company profile cues, role assessments, legal-form mentions, signal events, ranked person candidates, local AI evidence review, outreach draft citations, and matching source records.
- Decision records include source IDs that map directly to their source title, short evidence excerpt, URL, company/person identity match, and freshness metadata. Outreach drafts retain their cited source IDs.
- The Ledger grid includes an **Evidence & decisions** viewer. A user chooses a row, reviews the judgments and their source ID links, then opens the supporting sources from within the viewer.
- Heuristic assessments and candidate scores are clearly described as review aids, not verified classifications, legal facts, or probabilities. CSV-supplied signal cues are labeled as supplied context without a public source ID.
- The compact evidence record is kept under the 5,000-character Ledger cell limit. If needed it progressively reduces excerpts and secondary details while retaining core decisions and source links.
- Existing company/person signals, roles, candidate rankings, current/previous position relevance, and outreach evidence all remain connected to their source IDs.

## Persistence

The review record lives on the Ledger row, which uses the existing authenticated row update flow. No SQL migration is needed. No SQL file was added.

## Validation

Python syntax compilation, catalog JSON parsing, the app production build, and `git diff --check` are used for this slice. No test suite, live search, or paid provider call is run.

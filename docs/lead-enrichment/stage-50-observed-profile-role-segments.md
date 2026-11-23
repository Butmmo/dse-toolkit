# Stage 50: Segment fit reviews by observed research cues

## What changed

When a human fit review is saved, Citadel now snapshots the structured cues currently shown in the research bundle: business-profile assessments, role evidence, legal-form mentions, person-role candidate titles, and Presence signal categories. The local `score-ledger` command reports fit counts and rates by each observed cue within its research lane and shows coverage and the configured sample-size caution flag.

These are captured as candidate research observations, not verified classifications. The snapshot stores labels and assessment/status only; it does not copy person names, source URLs, or snippets. Stage 51 adds descriptive comparison with the current Send Desk status. Multiple cues from one row can appear in multiple segments, so the segment counts overlap and should not be summed as unique leads.

## Use

Export the grid with `enrichment_review` visible and run:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv --min-decided 10
```

See `observed_context_segments.review_coverage_by_dimension` and `observed_context_segments.by_lane_dimension_and_value` in the JSON report. Target intent remains separate under `target_context_segments`.

## Interpretation and limits

Returned profile, role and legal-form cues can be heuristic or incomplete; Presence categories describe returned public-search signals. They are not proof of company status or person identity. The rates describe only the reviewed sample and do not prove accuracy, causation, conversion, or ability to pay. Earlier reviews cannot reconstruct cues that were not saved at the time. No database migration is needed.

No automated tests were added or run.

## Files

- Citadel Ledger Evidence & decisions panel: append the cue snapshot to fit-review history.
- `dse/enrichment_eval.py`: group reviews by saved observed cues.

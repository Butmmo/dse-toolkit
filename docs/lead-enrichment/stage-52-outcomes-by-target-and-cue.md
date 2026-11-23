# Stage 52: Compare Desk states by target and research cue

## What changed

`score-ledger` now includes current Send Desk status and date-relative-to-review counts for each requested-target segment and each observed-research-cue segment, still separated by Herald, Website and Presence lane. This connects the questions “what did we ask to find?” and “what did research return?” with the current recorded Desk state.

## Use

Export `enrichment_review`, `Desk status` and (for timing) `Desk last update`, then run:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv
```

Read `send_desk_outcomes.by_requested_target_segments` and `send_desk_outcomes.by_observed_research_cue_segments` in the report. These mirror the target and observed segment keys in their corresponding top-level sections.

## Interpretation and limits

Desk values are current/latest row states, not a full event stream. The counts do not calculate funnel or conversion rates and do not establish that a target or research cue caused an outcome. A row with multiple cues appears in multiple segments, so groups overlap. Target fields are requested intent; observed cues remain unverified research. Small samples are descriptive only. No SQL migration is needed.

No automated tests were added or run.

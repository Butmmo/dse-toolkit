# Stage 51: Relate fit reviews to Send Desk outcomes

## What changed

`score-ledger` now reads the current `Desk status` value from an exported Ledger grid and summarizes status counts by the latest fit judgement, research lane and enrichment profile. It recognizes `sent`, `skipped`, `replied`, `booked`, `won`, and `lost`; empty or `to do` statuses are `not_recorded`. If the export includes `Desk last update`, the report also compares its date with the review timestamp: `after_review`, `before_review`, `same_day_order_unknown`, or `unknown`. If the export does not include Desk columns, the report marks them unavailable.

## Use

Make `enrichment_review`, `Desk status`, and `Desk last update` visible and export the Ledger grid:

```powershell
python dse.py eval-enrichment score-ledger my-lists\ledger-export.csv
```

Read `send_desk_outcomes.by_judgment_lane_and_profile` for profile groups, `by_requested_target_segments` for user-requested targeting intent, and `by_observed_research_cue_segments` for returned research cues. Each segment reports current status counts and update timing relative to the review. No person names, reply text, or monetary values are included in these aggregates.

## Interpretation and limits

The grid holds the current/latest Desk status, not a complete event history. Counts therefore do not form a campaign funnel or establish reply rates, conversion rates, time-to-outcome, revenue, or causal impact from enrichment. Same-day ordering is unavailable because Desk stores a date rather than a time for the grid update. Status differences are descriptive associations for the exported rows. Keep Herald, Website and Presence review lanes separate. No Supabase SQL is required.

Stage 52 adds Desk-status groupings to each target and observed-cue segment. The segment groups overlap when a lead has more than one cue. No automated tests were added or run.

## Files

- `dse/enrichment_eval.py`: current Desk status grouping in `score-ledger`.

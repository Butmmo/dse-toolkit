# Stage 22: Engine-path guided signal enrichment

## What changed

- Added one concise research profile for each of the nine active Engine paths: what the path sells, likely buyer roles, evidence/search direction, proof metrics, and monetization model.
- Lead signal enrichment now reads the selected Engine path, guides search queries and role candidates toward it, and retains the path focus in the CSV so Ledger imports and Engine lists can carry it forward.
- Each classified signal event records whether it is priority, supporting, or general for the selected path. The local AI draft receives path guidance but is explicitly told not to assume pain, budget, or business classification from it.
- Unlinked runs can select a path in HQ Tools/CLI; General remains available. A mismatched explicit path and Engine path is rejected with a clear error.
- Added a concise path-by-path guide to the app taxonomy docs, covering the recommended HQ Tools, DBI-AI, Presence, Ledger/grid, Herald, workflow, schedule, and automation sequence.
- Moved Learn to the first group after Dashboard on both desktop and mobile.

## Files

- `dse/path_signals.py`: path profile definitions.
- `dse/signal_enrichment.py`: path-aware query, role, AI guidance and event fit.
- `dse.py`, `bridge/add_enrich_tools.py`, `catalog.json`: CLI and HQ Tools controls.
- `dse/importer.py`, `dse/engines.py`: preserve path metadata through imports and Engine lists.
- App repository `src/lib/nav-groups.ts`: Learn order.
- App repository `docs/path-specific-lead-signal-taxonomy.md`: concise path tool sequence.

## Verification

Python syntax compilation and Git whitespace checks are the planned checks. No SQL migration is needed. No runner installation or deployment is part of this stage.

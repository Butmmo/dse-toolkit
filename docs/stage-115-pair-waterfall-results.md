# Stage 115: Pair verified A/B waterfall outputs

## Gap

After the two variant runs, the assignment tool required one manually combined CSV. Manual merging could introduce missing rows, duplicate leads, swapped labels, or a file from another experiment.

## Change

- Variant cohort records now include a SHA-256 fingerprint of each result CSV.
- Added a local `pair-variants` command and the **Waterfall experiments: pair verified A/B results** HQ Tool.
- The pairer verifies the recorded A and B file paths and hashes, the experiment ID, field, provider pair, source cohort fingerprint, ordered lead IDs, and unique one-row-per-lead structure.
- It creates one paired CSV and records its path and hash in the local cohort manifest. Existing conflicting paired outputs are never overwritten.
- The paired lead CSV and cohort record are marked PC-local outputs; neither is uploaded by the runner.

## Workflow after this stage

Run the A and B configs on the same CSV and cap, pair the verified outputs in HQ Tools, then use **Assign outreach variants** to select one variant per lead and stage the assigned file for an Engine. Pairing does not select a variant or send outreach.

## Verification

- Checked the Python modules, CLI mapping, and catalog entry for syntax and argument consistency.
- Pushed to `codex/hq-runner-id-routing` and restarted the PC runner; its startup log reports 181 tools.
- No live lead enrichment, paid calls, Engine writes, or paired-file uploads were performed.

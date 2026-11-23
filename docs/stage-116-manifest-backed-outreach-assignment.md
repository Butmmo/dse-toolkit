# Stage 116: Bind outreach assignment to the verified paired cohort

## Gap

The assignment tool accepted any CSV with A/B experiment columns. That left a route around the prior verification step: a hand-edited or unrelated combined CSV could be assigned even though the pairer had already recorded the verified paired file.

## Change

- Assignment now requires the exact local paired CSV recorded for the chosen experiment and verifies its SHA-256 hash.
- It checks the cohort manifest, experiment field, provider pair, exact ordered lead cohort, both variants' config fingerprints, and one A and one B row per lead before assignment.
- The first assignment binds the experiment to one seed, output name, and Engine. Later attempts with a different seed, Engine, or output name are blocked.
- The local cohort record and assignment audit now link the paired source hash to the assigned output hash.
- HQ Tools only offers paired-result files for assignment. Assigned CSVs and audit files are marked PC-local, so the runner does not attach lead rows to the job result or transfer them over the network. If an Engine is chosen, the assigned file is saved in that PC's local Engine imports folder.

## Workflow after this stage

Run both variants on the same CSV and cap, pair the verified outputs, assign one variant per lead with a fixed seed and target Engine, then inspect it with `python dse.py import <engine>` before the local Engine workflow uses it. Assignment does not send messages.

## Verification

- Checked Python compilation, CLI help, and catalog JSON/argument mapping.
- Pushed to `codex/hq-runner-id-routing` and restarted the PC runner; its startup log reports 181 tools.
- No lead assignment or Engine write was run during this change.

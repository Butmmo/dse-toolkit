# Stage 114: Keep provider experiment runs paired and separate

## Gap

The two experiment configs could be selected in the existing enrichment tool, but running both on the same source list produced the same output filename. The second run could overwrite the first. The optional Engine import path could also place an unassigned A/B variant directly into an Engine before the cohort was assigned.

## Change

- Experiment runs now include the experiment ID and variant in their CSV and report names.
- Before provider calls, the toolkit checks that the run's output files do not already exist.
- Duplicate stable lead IDs in the bounded cohort are rejected before provider calls. The first completed variant records a data-minimized cohort manifest: source CSV hash, ordered sample fingerprint, sample cap, row count, experiment field, and provider pair. The other variant must match that exact input and cap.
- A variant already recorded for that experiment cannot be silently rerun over its existing result.
- Dry runs use separate `-dry-run` output names and do not claim a variant in the cohort manifest.
- The run report points to the shared cohort manifest so the user can verify both variants used the same sample.
- Experiment variant runs cannot write to an Engine. Both results must be prepared before the assignment workflow chooses one variant per lead.
- The HQ Tools description explains that the same source CSV and lead cap must be used for both variants, and each paid run needs its own approved spend ceiling.

## Verification

- Checked the changed Python and catalog structure for syntax consistency.
- Confirmed the output preflight and cohort-match checks run before enrichment provider calls.
- No provider requests or Engine imports were made during this change.

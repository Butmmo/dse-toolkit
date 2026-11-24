# Stage 141: Fingerprint monitoring search coverage

## What changed

Signal search metrics and Ledger monitoring snapshots now store a short SHA-256 fingerprint for each query rung's normalized query text. The query itself is not copied into monitoring history. When deciding whether a missing source received a covered recheck, monitoring now requires the same rung and query fingerprint to have completed successfully. If the rung name is unchanged but its query changed, evidence says the prior coverage was not repeated and treats absence as inconclusive.

Older snapshots without fingerprints continue to use the Stage 136 rung-name coverage rule. Source-comparison field results now describe this coverage limitation.

## Interpretation limits

A matching query fingerprint proves only that the same normalized search text was sent through that rung and completed. Search providers may still change their index or results. A missing URL remains a recheck cue, not proof of disappearance or reversal. Fingerprints are for coverage comparison, not user or lead identity.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

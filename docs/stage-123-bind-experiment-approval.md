# Stage 123: Bind waterfall experiment runs to preflight approval

A ready paired preflight now writes a local, never-overwritten approval receipt under `my-lists/`. It binds the experiment ID and field, both config hashes, source CSV hash, stable bounded-cohort hash and cap, the combined approved ceiling, per-variant conservative maximums, currency, and any unknown-price acknowledgment. A receipt is created only when both configs have keys and valid mappings, known-cost estimate is within the combined ceiling, and unknown prices are explicitly acknowledged when present.

Live enrichment using an A/B experiment config now requires that receipt. Before provider calls, the run checks the exact source/cohort/cap and variant config hash, validates the receipt digest, recomputes the current variant spend estimate from provider prices and call caps, confirms the combined ceiling covers both variant estimates, and applies the receipt's per-variant spend maximum. A changed list, cap, config, pricing, or call cap requires a fresh preflight. Non-experiment enrichments remain unchanged; dry-run variants do not require the receipt.

HQ Tools exposes the receipt picker on the existing enrichment tool and keeps the receipt local. The preflight tool reports the receipt path and exposes it as a local output for selection in the next run.

Validation performed: Python compilation of `dse.py`, `dse/enrich.py`, and `dse/waterfall.py`; CLI help; catalog JSON parsing; and `git diff --check`. No live provider requests or paid runs were made.

The implementation was pushed to codex/hq-runner-id-routing and installed in the active PC runner checkout. The runner restarted and reported 182 tools online. The existing local packs/automation.json change was preserved.

# Stage 64: Brave spend approval and toolkit update confirmation

## What changed

Brave Search Signals now require both a user-declared rate per 1,000 requests and an explicit maximum spend approval whenever a run may send requests. CSV Signals and live Ledger-grid enrichment calculate a conservative request ceiling, estimate spend before searching, and reject the run if the estimate exceeds the approved maximum. The live-grid tool exposes the approval field and carries it through every saved batch. Usage remains journaled locally. This is an estimate gate; it cannot enforce the provider's actual billing or account-level cap.

HQ Tools now keeps the toolkit update status visible while making its instructions collapsible. The hide choice is saved per PC and target GitHub revision; a new revision gets a fresh prompt. Missing revision reports are described as unconfirmed status rather than as proof that an update is needed. The steps require checking the current branch and stopping if a branch switch or fast-forward pull fails. They also require comparing `git rev-parse HEAD` with the target before installing dependencies or restarting.

## Finding from the supplied PC screenshots

The update did not reach the toolkit source checkout. Inspection of the supplied PC folder confirms it remains on branch `codex/lead-signals-pc-install` at `077955c`, while `origin/main` is `bc44172`; `bridge/runner.py` still reports version `1.2`. `git switch main` was refused because the working tree had local modifications. The subsequent `git pull --ff-only origin main` fetched `main` but failed because the checked-out branch could not fast-forward to it. Installing `requirements.txt` succeeded, and the scheduled-task restart command was issued afterward, but neither action updates source files. Therefore the prior code remained in use, and the app correctly could not confirm the new revision. Preserve the local toolkit edits and reconcile them before switching/pulling; do not discard or overwrite them.

## Files

- `dse/signal_enrichment.py`, `dse.py`: CSV Signal spend approval and preflight estimate.
- `dse/grid_enrich.py`: same approval across a live grid run and its batches.
- `bridge/add_enrich_tools.py`, `bridge/add_grid_enrich_tool.py`, `bridge/catalog.json`: HQ Tools fields, arguments and cost guidance.
- `README.md`: updated usage instructions.
- DBI Citadel `src/routes/_authenticated/hq-tools.tsx`: persistent status, hide/show control, safer steps, and commit comparison.

## Verification and limits

Reviewed the bridge catalog and runner revision-reporting code. No live Brave searches, provider charges, GitHub writes, PC runner installation, automated tests, or Supabase changes were made in this stage. The update status on the user's PC must be confirmed after local changes are safely reconciled, `main` is actually updated to the shown SHA, and the restarted runner publishes its catalog.

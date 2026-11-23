# Stage 65: Safe toolkit update preflight

## What changed

The PC System Check now inspects the current Git branch and working tree before describing toolkit update status. Modified, staged, and untracked paths are counted. For a non-main branch, it compares the branch's commits with the locally fetched `origin/main` reference and reports how many commits are unique on each side. If the checkout is dirty or is on a branch that needs reconciliation, the check gives a specific stop-and-preserve instruction; it never recommends a blind branch switch, pull, reset, or clean.

A clean checkout on `main` continues through the public GitHub comparison and can receive the fast-forward update command. The check remains read-only: it does not fetch, pull, stash, merge, reset, or alter files.

## Why this was needed

The toolkit folder on the PC is on `codex/lead-signals-pc-install`, with two branch-only commits and a dirty working tree containing modified and untracked enrichment/tool files. Its last-fetched `origin/main` is 79 commits ahead. `git switch main` was blocked by local edits, and the following pull failed while still on the feature branch. Generic update guidance did not clearly diagnose the branch and worktree combination.

## Files

- `dse/doctor.py`: safe branch/worktree preflight and reconciliation guidance.
- `README.md`: explains that only a clean `main` checkout receives the fast-forward update steps.

## Verification and limits

No automated tests were added or run. `git diff --check` passed before installation. The preflight was backported into the older PC `dse/doctor.py` without replacing its other System Check features. Before editing, the original `dse/doctor.py` and `README.md` were copied to the Codex workspace backup folder `work/pc-runner-backups/2026-11-23-stage-65`. The stage note was copied into the PC toolkit. Running `python dse.py doctor --offline` on the PC exited successfully and reported branch `codex/lead-signals-pc-install`, 14 modified/staged/untracked paths, 79 commits in last-fetched `origin/main` absent from this checkout, and 2 unique branch commits. It also confirmed the existing runner was online with 171 tools. The command did not run database probes; no branch switch, pull, merge, stash, task restart, or automated test was performed.

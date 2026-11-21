# Toolkit update notice for existing PC users

**Date:** 21 November 2026  
**Status:** Implemented on the DSE Toolkit feature branch; not installed on the PC runner.

## What changes

The DSE System Check compares the local Git checkout with the latest public `main` commit in `Butmmo/dse-toolkit`. The GitHub result is cached on the PC for one hour. While the runner is connected, the existing Setup checklist can show the update notice on the user's Citadel Dashboard; the user can also run `python dse.py doctor` locally.

If GitHub has a newer commit, the checklist gives the local toolkit folder and a safe PowerShell sequence:

1. Inspect local changes with `git status --short`.
2. Update with `git pull --ff-only origin main`.
3. Confirm the runner connection with `python bridge/runner.py check`.
4. In Citadel HQ Tools, run **Restart the HQ runner**. After reconnecting, the runner publishes its refreshed catalog so the user's tools include the newly installed toolkit tools.

The checker never pulls or edits files automatically. A fast-forward-only pull refuses to overwrite divergent local work; users are instructed to stop and get help if it refuses. A failed or unavailable GitHub check is reported as unknown, never as up to date.

## Boundaries

This checks the public repository's `main` commit. It does not notify a clone whose origin is another repository, and it does not compare local branches to feature branches. User data remains in the existing ignored engine, list, and local-data folders. No Supabase SQL is added because this reuses the existing Setup checklist channel.

No tests were run. `git diff --check` is the hygiene check. This update-notice code has not yet been installed on the PC runner.

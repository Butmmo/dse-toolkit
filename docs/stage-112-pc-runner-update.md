# Stage 112: Install the current toolkit on the PC runner

**Date:** 2026-11-23  
**Source revision:** `548a2dc71e6f34b345368ae7949b1d7667e7a99c` (`Enforce consistent experiment assignment in Engines`)

## What changed

- Installed the pushed toolkit revision in a separate desktop checkout so existing local edits and user data were left intact.
- Copied the runner's local configuration and PC-owned data into the new checkout. The original checkout remains available as a recovery copy.
- Updated the Windows `DSE Toolkit runner` scheduled task to start the new checkout.
- Confirmed the runner started as `dse-office-pc-toolkit` and reported 179 tools.
- Confirmed the required Python packages were already installed.

## Verification

- Scheduled task state: **Running**.
- Runner log: startup completed and periodic helpers were registered.
- Catalog loaded: **179 tools**.
- Existing checkout and its uncommitted changes were preserved.

## Recovery

The prior checkout remains at `Desktop/DFamocious-HQ/dse-toolkit`. If the updated runner needs to be rolled back, point the `DSE Toolkit runner` scheduled task back to that checkout's `bridge/start-runner.ps1` and start the task.

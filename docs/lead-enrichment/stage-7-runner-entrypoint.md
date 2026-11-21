# Runner repair: resolve the DSE Toolkit entrypoint

**Date:** 21 November 2026  
**Status:** Installed locally and validated with the mailbox test on 21 November 2026.

## Cause

The base HQ runner's catalog refers to the shared DSE CLI as `dse.py`, but the checked-out toolkit is in the sibling `dse-toolkit` folder. The HQ runner resolves scripts relative to the HQ root, so it rejected Herald jobs with `script missing: dse.py` before starting Python.

## Repair

Added a root `DFamocious-HQ/dse.py` compatibility launcher on this PC. It delegates command execution to `dse-toolkit/dse.py`, and exposes the nested DSE package for the runner's local helper imports without executing the CLI during import. The tracked shared runner source also has a confined fallback for `dse-toolkit/dse.py` when the root-level script is absent. Both paths remain within the HQ root.

## Verification and limits

The launcher displayed the DSE CLI help. The HQ runner's documented dry invocation built `dse.py herald test <mailbox>` without a script-missing refusal, and the optional DSE package catalog helpers loaded without the previous import warning. The requested Gmail test was then rerun through the launcher and returned READY: Google sign-in succeeded and the mailbox can send. It did not send an email or read a message. In this OAuth mode, replies are read in Gmail itself; IMAP reading requires an app password saved on this PC.

No Supabase SQL is needed. No test suite was run. The root launcher is PC-local; the shared fallback is source-controlled in the DSE Toolkit feature branch.

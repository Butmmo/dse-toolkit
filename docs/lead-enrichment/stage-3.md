# Lead enrichment, Stage 3: reviewed Presence-to-Ledger handoff

**Date:** 21 November 2026  
**Status:** DSE shelf output updated locally; app handoff is in the matching Citadel branch and neither change is deployed.

## DSE Toolkit change

The Presence social-signals runner now writes a v2 shelf JSON alongside its CSV and Markdown summary. It groups each business with its stable row reference, business name, website, city, contact name/title/email, result status and up to eight public signals with source URLs. The CSV remains available for download and manual import.

The grouped file lets Citadel offer a reviewed, lead-by-lead transfer into a Ledger while keeping evidence attached to the business it describes. The older flat v1 shelf is still accepted by Citadel for existing output files.

## Handoff behavior

In Citadel Presence > Research, a user selects leads, picks an Engine, and then chooses or creates a Ledger for that Engine and a grid. Each imported row retains its business/contact fields, Presence findings, source URLs, checked date and status. Re-importing the same research item into that grid skips rows already transferred. This action does not draft or send Herald email.

No SQL migration is required for Stage 3. DSE Toolkit's change is in `dse/signal_enrichment.py`; the UI and import are documented in Citadel's `docs/lead-enrichment/stage-3.md`.

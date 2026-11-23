# Stage 113: Expose provider comparison drafts in HQ Tools

## Gap

The toolkit already had a local command that creates two waterfall configs for comparing provider order, but the command was not available in the HQ Tools catalog. Users therefore had no guided way to start a provider comparison from the app.

## Change

Added **Lead enrichment: draft a two-provider comparison** to the local HQ Tools catalog. It lets the user select a saved waterfall, a supported field, and two providers already configured for that field. The existing builder creates two never-overwrite drafts, swaps only those providers' positions, and records a shared experiment ID and source-config hash.

The tool is local-only. It does not read lead rows or call enrichment providers. Its instructions point users to review and preview both configs and use the same bounded lead cohort for each variant.

## How this advances the experiment path

This makes the first controlled configuration step discoverable in HQ Tools. The existing assignment tool can then keep each lead in only one outreach variant, while Engine and Send Desk checks preserve cohort consistency and report observed outcomes.

## Verification

- Parsed `bridge/catalog.json` as JSON and confirmed the new tool entry and argument mapping.
- Confirmed the tool points to the existing `dse.py enrich --build-waterfall-experiment` command.
- Pushed the update to `codex/hq-runner-id-routing` and restarted the PC runner; its startup log reports 180 tools.
- No live enrichment or paid provider calls were made.

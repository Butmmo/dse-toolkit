# Stage 41: Apply path profiles to enrichment runs

## What changed

The optional `--enrichment-profile` selection is now accepted by Herald and Presence CSV research and by live Ledger-grid enrichment. HQ Tools exposes the selector for those research tools, including the in-grid `dse.grid_enrich` tool.

When selected, the profile:

- chooses the path focus and rejects a profile that conflicts with the selected path or linked Engine;
- supplies the first recommended business segment when the user has not selected one;
- caps Herald/Presence queries to the profile's per-lead limits (a lower user-set query budget remains in force);
- adds the path's public business signal search to Presence while retaining a named-contact query within the configured query budget;
- labels each dated result as within/outside the profile freshness window, or undated, without deleting it;
- writes the profile version, path, lane, applied query cap, freshness window and provider-call cap into the CSV and/or Ledger row.

For Website enrichment on a grid, the selected profile's provider-call cap is passed into the existing provider waterfall. The default profile cap is zero, so provider calls remain off unless a later profile version is configured and supported.

## In-grid toolbox

An open Ledger grid now has a searchable **Tools** shelf with tabs for **For you, Sources, Enrich, Signals, Transform, and Exports**. It offers the current grid enrichment lanes as focused entries and opens their familiar HQ Tools form in the shelf. Results still write through the authenticated PC runner into the same grid. The grid now includes **Export CSV**; it exports the currently shown rows and visible columns after search and filters.

## Use

From a CSV research command:

```powershell
python dse.py signals leads.csv --engine my-engine --enrichment-profile automation
python dse.py presence-signals leads.csv --engine my-engine --enrichment-profile automation
```

From an open grid, open **Tools → Signals** or **Tools → Enrich**, select the same profile in the run form, and review the limits before running. A path mismatch is rejected rather than silently mixing Engine methodologies.

## Limits

- This applies the built-in version 1.0.0 profiles. User-edited exported profile files are not loaded into execution yet.
- Expected coverage remains unmeasured. Profile freshness labels are advisory and never suppress a source result.
- Provider spend is bounded here by the supported provider-call cap, not by invoice reconciliation or a guaranteed monetary conversion.
- The new tools shelf groups the available in-grid tools; Source/Transform entries only appear when the connected toolkit catalog offers them. Export is handled locally by the grid and does not go through the PC runner.
- No SQL migration is needed. No automated test suite was added or run in this slice.

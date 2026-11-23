# Stage 63: Brave cost controls for live Ledger grid enrichment

## What changed

Live Ledger grid enrichment now accepts the same optional `brave_cost_per_1000` input as the CSV-based Herald Signals tool. When the user selects the Herald lane and Brave, the runner announces a conservative total request and spend ceiling before searching. The final grid-run response reports Brave requests used and the estimate at the user's declared rate.

The `DSE_BRAVE_SEARCH_QUERY_LIMIT` cap is now shared across all batches in one live grid run. The grid runner calculates a total run ceiling from the selected rows, per-row search budget, and the PC's configured Brave cap. Before each saved batch, it gives the remaining cap to the Signals runner; when the cap has been used, later batches receive a zero search budget. The original environment setting is restored after each batch. Requests made in each batch continue to append to the same local usage journal, grouped under the Herald Signals lane.

The HQ Tools `dse.grid_enrich` form now exposes the optional user-declared USD rate per 1,000 requests. It is relevant only when the Herald lane and Brave Search are selected. It estimates cost; it does not make a provider call, fetch plan prices, or change provider billing.

## Behavior and safety

- Brave remains opt-in and requires the PC-local `BRAVE_SEARCH_API_KEY`.
- The cap applies to actual Brave HTTP attempts across grid batches, including failed attempts; skipped queries after the cap do not create usage events.
- A blank rate leaves costs unknown while request counting and the configured cap still apply.
- The displayed ceiling is an upper bound. Search may use fewer queries; the vendor's account limits and billing rules take precedence.
- The request counter and user-declared rate apply to the Herald search lane. Website and Presence lanes do not use Brave in this tool.
- If usage journaling fails, the completion response reports an accounting warning.

## How to use

In HQ Tools, run **Ledgers: enrich grid rows live**, select the **Herald** lane, choose **Brave API**, and optionally enter the plan's current price per 1,000 requests in the estimate field. The runner prints the request and cost ceiling before work begins and the used-call estimate at completion. Set the rate to blank when unknown; do not substitute a guess.

CLI users can pass `--brave-cost-per-1000 RATE` to `python dse.py grid enrich ...`; the runner's CLI cap and rate options remain local to this PC.

## Files

- `dse/grid_enrich.py`: run-wide cap across saved batches, rate validation, and final cost summary.
- `dse/signal_enrichment.py`: optional suppression of repeated per-batch ceiling messages and zero-cap enforcement.
- `bridge/catalog.json` and `bridge/add_grid_enrich_tool.py`: live-grid form input.
- `README.md`: usage guidance.

No SQL is required. No live Brave requests or automated tests were run during this stage.

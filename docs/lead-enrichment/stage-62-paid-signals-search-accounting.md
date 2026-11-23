# Stage 62: Paid Signals search usage and run estimates

## What changed

Brave Search API requests made by the Herald Signals search path now use Stage 61's local provider-usage journal. Each request outcome is recorded with provider `brave_search`, lane `herald_signals`, outcome, optional HTTP status, request count, and cost basis. Search text, lead identity, URLs, and credentials are not written to the journal. Successful calls, HTTP failures, network failures, and unreadable responses are accounted as attempts; an attempt's actual billability is still controlled by the vendor's terms.

`dse.enrich_signals` accepts an optional user-declared `--brave-cost-per-1000` rate in USD. It does not query the provider for its plan price and does not change account billing. If supplied, each request gets a proportional estimate in the journal, and the per-lead search-waterfall metadata includes the declared estimate. If omitted, the cost remains unknown.

Before a Brave run, the tool prints the upper request limit and estimated spend ceiling to stderr. The cap is the lower of the configured per-lead search budget across the selected row count and `DSE_BRAVE_SEARCH_QUERY_LIMIT` (default 150, maximum 1,000). The run summary reports calls used and the estimated cost at the rate supplied. Each later use of `python dse.py enrich --usage` includes those calls in its provider totals.

The HQ Tools Signals tool exposes the optional per-1,000 request rate. DuckDuckGo remains the default; the input is only relevant to a Brave run. Grid executions that invoke the same Brave search adapter are journaled too, but currently have no rate input and therefore remain cost-unknown in the journal.

Stage 63 adds the same rate input to live Ledger grid enrichment and enforces a single request ceiling across its saved batches.

## Cost controls and limits

- Brave remains opt-in and continues to require the user's PC-local `BRAVE_SEARCH_API_KEY`.
- Adding the rate input or leaving it blank does not itself make a request. A Brave request happens only when the user selects Brave and the PC has its API key configured.
- A declared rate is user input, not a live quote, invoice total, or DBI-set price.
- The spend ceiling is conservative and uses request caps; the actual query set may use fewer calls.
- Provider account limits, credits, pricing rules, taxes, and failed-request billing can differ from this estimate.
- Presence uses DuckDuckGo in its current implementation, so it has no paid Brave requests to add here.
- No DBI wallet, provider resale, or payment collection was added.

## Files

- `dse/signal_enrichment.py`: Brave request journal entries, run ceiling, and search-waterfall cost metadata.
- `dse/enrichment_usage.py`: shared local usage journal and report.
- `dse.py`: optional declared rate argument.
- `bridge/catalog.json` and `bridge/add_enrich_tools.py`: HQ Tools input definition.
- `README.md`: user guidance and cost-estimate distinction.

No live Brave calls or automated tests were run in this stage.

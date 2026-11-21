# Stage 18: optional Brave Search provider

## What changed

The Herald lead-signals tool now offers DuckDuckGo (default) and Brave Search API as public-web search providers. Every result records the provider. Brave results supply titles, URLs, descriptions, and page-age hints where available, which flow into the existing freshness metadata.

Brave is strictly opt-in through the tool's `search_provider` field. The key is read from the PC-local `BRAVE_SEARCH_API_KEY` environment variable and is never put in the catalog, CSV, logs, or query URL. A run is capped at 150 Brave requests by default; `DSE_BRAVE_SEARCH_QUERY_LIMIT` can lower or raise that cap (maximum 1,000). A provider error is shown without exposing the key.

## PC setup

1. Create a Brave Search API account and API key.
2. In PowerShell, set the key on the PC: `setx BRAVE_SEARCH_API_KEY "your-key"`.
3. Optionally set a request cap: `setx DSE_BRAVE_SEARCH_QUERY_LIMIT "50"`.
4. Restart the HQ runner so it receives the new Windows user environment.
5. Run **Lead signals: research and draft outreach** and select **Brave Search API**.

Brave's published Search plan currently costs $5 per 1,000 requests and includes $5 in monthly credits; prepaid billing/account requirements apply. At that published rate, the default 150-query cap is about $0.75 maximum per run before credits. Check the provider's current terms before enabling it. DuckDuckGo remains the default and requires no key.

## Why this is not Google Custom Search

Google's official Custom Search JSON API documentation says the API is closed to new customers and scheduled to discontinue on January 1, 2027. The implementation therefore adds a maintained alternative search index rather than tying new users to that retiring API. [Google API status and end date](https://developers.google.com/custom-search/v1/overview).

Brave uses `https://api.search.brave.com/res/v1/web/search` and the `X-Subscription-Token` header. See [Brave Web Search API documentation](https://api-dashboard.search.brave.com/documentation/services/web-search) and [current plans](https://brave.com/search/api/).

## Limits

Brave results are a second web index, not Google results and not verified claims. Provider coverage and snippets vary. The query cap prevents an unbounded run, but a selected Brave search can use the user's configured API allowance. No key was configured or used during this development slice. No Supabase SQL is required. No tests were run.

## Files

- `dse/signal_enrichment.py`: optional provider adapter, safe errors, result provenance, and request cap.
- `dse.py`: CLI provider choice.
- `bridge/add_enrich_tools.py` and `bridge/catalog.json`: HQ Tools selector.

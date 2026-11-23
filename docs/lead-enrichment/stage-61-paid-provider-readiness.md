# Stage 61: Paid-provider readiness and local usage accounting

## What changed

Added a provider catalog at `dse/enrichment_provider_catalog.json`. It describes the current optional Hunter adapter, the existing Brave Signals search option, prospective paid providers, and providers that are retired or restricted for prospecting. Each entry points to official pricing, API and policy pages. The catalog distinguishes integration status from provider availability: a candidate is not a working adapter, and a provider's listing does not turn it on.

Added `python dse.py enrich --catalog` and the HQ Tools catalog reader. This is a local, read-only catalog lookup; it does not make provider requests or enable a paid source.

Added a local usage journal at `data/enrichment-provider-usage.jsonl` for requests made through the optional enrichment-provider adapter layer. Each event records provider, field, timestamp, outcome and HTTP status, plus an optional estimate from the configured `cost_per_call`. It deliberately excludes lead names, domains, request URLs and keys. Failed requests are recorded as attempts because some vendors can charge for unsuccessful calls; the journal does not assume whether an individual provider billed them. Stage 62 extends this journal to Brave Signals calls.

Added `python dse.py enrich --usage [--usage-days N]` and the HQ Tools usage reader. The report separates calls with a configured estimate from those with unknown cost and identifies outcomes. It explicitly states that provider-configured estimates do not represent vendor invoices.

## Business and safety boundary

The implementation continues the bring-your-own-key model. It does not add a DBI-funded provider account, customer wallet, credits sale, payment transaction, or charge. It does not execute any paid API call during setup. The local journal is a measurement instrument for adapter calls, not an accounting ledger or a substitute for provider billing records.

The catalog uses status labels to prevent misleading integration claims:

- `ready_byok`: an optional adapter exists.
- `existing_search_adapter`: the provider is already selectable in the signal-search path.
- `candidate`: access is publicly available, but a Citadel adapter and cost/terms review are still required.
- `closed_to_new_customers`, `retired`, and `restricted_for_prospecting`: do not plan a new prospecting integration through that route.

## Known limits and next work

This stage journals configured enrichment-adapter requests for email, phone, person identity and firmographics. The Signals and Presence search implementations are separate and are not yet included in the local usage journal. Vendor-native credit deductions, invoice reconciliation, retries charged differently from calls, bundled plan minimums, FX and DBI resale rights remain unresolved. Catalog prices are linked rather than copied so operators check the vendor's current terms before enabling an integration.

Next: extend usage events to paid Signals search and any subsequent provider adapter; add an explicit per-run estimate/approval gate for providers whose price basis can be represented safely; compare reviewed benchmark outcomes against measured cost per useful result. Only after usage and customer demand are measured should a DBI-managed credits model be designed.

## How to use

```powershell
python dse.py enrich --catalog
python dse.py enrich --usage
python dse.py enrich --usage --usage-days 90
```

The two read-only readers are available in HQ Tools through the toolkit bridge catalog as `dse.enrich_catalog` and `dse.enrich_usage`.

## Validation note

No live provider requests were made and no tests were run during this stage. Matching HQ Tools definitions were added to `bridge/catalog.json` and `bridge/add_enrich_tools.py`. The generator also contains older enrichment-tool definitions that have drifted from the live catalog; reconcile that pre-existing drift before regenerating the full catalog, or it can remove newer tool fields.

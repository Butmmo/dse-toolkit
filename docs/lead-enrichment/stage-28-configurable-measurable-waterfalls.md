# Stage 28: Configurable and measurable email waterfalls

## What changed

Lead email enrichment can now use an ordered waterfall config (`dbi.waterfall-config.v1`) instead of only a single optional provider. The JSON file selects provider order, a minimum provider confidence, an acceptance stop rule, and a maximum number of provider API calls. The single `--provider` mode remains available for compatibility; it cannot be combined with `--waterfall-config`.

A sample config is at `enrich-waterfalls/email.example.json`. Configure an actual adapter locally in `enrich-providers/` and its API key as a Windows user environment variable. Provider order is explicit and capped at 12 unique providers. The configured call cap is global across the ordered rungs; `--budget` can lower or override it for a run.

Each candidate is audited as accepted or rejected. A provider email is accepted only when its domain matches the lead's normalized domain, and—when configured—the provider confidence meets the minimum threshold. The stop rule can stop on any accepted email, a personal email, or a personal email attached to a named person. Existing first-party site findings are considered for the stop rule before provider calls.

## Measurement and safety

The summary report and CSV include per-rung attempts, API calls, cache hits, candidates returned, accepted and rejected candidates, errors, and projected calls in dry-run mode. API calls here mean calls attempted by this client and are not proof of provider billing. Monetary estimates are shown only when the provider adapter explicitly declares `cost_per_call` and a three-letter `cost_currency`; otherwise the report says the price is unknown.

`--dry-run` performs the normal first-party website scan and checks the local provider cache, but does not make optional provider HTTP requests or require provider keys. It reports a maximum projection bounded by the configured global call cap. Actual runs still require keys for every configured provider.

HQ Tools exposes the optional waterfall JSON, per-run cap, and dry-run control. With no provider selected, enrichment remains first-party and free. Provider adapters must already exist and their response mapping must be configured; this stage does not add new commercial providers.

## Limits and follow-up

This first configurable waterfall targets email only. It does not yet offer configurable waterfalls for person identity, phone, company firmographics, social signals, or arbitrary field types. Cost estimates are simple configured per-call projections, not provider invoices; cache, provider-specific credit bundles, failed-call billing, taxes, and volume tiers may differ. Validate the output and source evidence before outreach.

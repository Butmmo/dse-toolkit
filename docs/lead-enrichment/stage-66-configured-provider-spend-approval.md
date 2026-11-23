# Stage 66: Configured provider spend approval

## What changed

Configured email, phone, person-identity, and firmographic waterfalls now calculate a conservative maximum estimate before enrichment begins. The estimate assumes every possible provider attempt reaches the highest-priced rung in that field's chain. It uses the configured call cap and selected row count, so it can overestimate actual use; cache hits and early stopping may lower the eventual usage.

Live CSV enrichment and live Ledger-grid website enrichment require `--max-provider-spend` whenever configured provider calls may run. The estimate must fit within that user-approved numeric ceiling. If any configured provider has no declared per-call price, the user must also pass `--allow-unknown-provider-cost` after reviewing the provider's pricing. The numeric ceiling covers known-price estimates only; it cannot cap a vendor charge whose price is unknown.

One shared runtime guard is used across the configured field waterfalls within a CSV run. Ledger-grid enrichment calculates the same estimate for each saved batch before starting, checks the combined estimate against the user's ceiling before any batch runs, and gives each batch its own runtime ceiling. Known-price estimates in incompatible currencies are rejected until the user separates the configurations.

Cached provider answers do not consume the monetary ceiling. Each uncached paid attempt reserves its configured estimate before the HTTP request, including attempts that later fail. The existing call-count cap remains in force. Dry runs make no provider requests and can display estimates without approving a spend.

## How to use

For a CSV or one-site enrichment, configure prices in the provider adapters or waterfall JSON, set a provider-call cap, and supply `--max-provider-spend <amount>`. If any provider is unpriced, also supply `--allow-unknown-provider-cost` only after checking that provider's pricing. HQ Tools exposes corresponding controls for CSV enrichment and the Ledger grid website-enrichment lane.

## Limits and safety

- These values are local estimates from user-maintained provider configuration, not vendor quotes, invoices, or billing data.
- The estimate is intentionally conservative and may be higher than actual consumption.
- An unknown-price provider can still charge an unknown amount after the user explicitly acknowledges that uncertainty; the toolkit cannot numerically bound that provider's charge.
- This gate covers configured provider waterfalls, not the separate Brave search approval controls.
- No live provider calls were made while implementing this stage.

## Verification performed

Reviewed the modified CLI, provider budget, CSV runner, live grid batch flow, HQ tool generator definitions, and catalog entries. Validation is limited to syntax/catalog/diff checks; no test suite or live provider request was run.

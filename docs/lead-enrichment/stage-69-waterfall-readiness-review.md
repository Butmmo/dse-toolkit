# Stage 69: Waterfall readiness review

## What changed

Added **Lead enrichment: review a provider waterfall** to HQ Tools and `python dse.py enrich --review-waterfall-config`. The review loads a saved local waterfall, validates each provider adapter and its email or field response mapping, checks whether the required local API key is present (without returning it), and summarizes the per-field call caps, configured prices/currencies, conservative estimate, and required spend approvals for a chosen lead count.

The review is local and read-only. It does not open lead data, contact providers, change the waterfall file, or expose API key values. Invalid config or adapter mappings produce a clear failure instead of a false readiness result.

## Suggested workflow

1. Build a config with the Stage 68 waterfall builder.
2. Review it here to catch missing keys, mappings, and pricing declarations.
3. Preview its estimated spend with the Stage 67 preview.
4. Run enrichment only after setting any missing keys and supplying the Stage 66 approvals.

## Scope and limits

- “Key configured” means the expected environment variable is populated on this PC; it does not prove that the provider accepts the key.
- Configured prices are user-maintained estimates. The review does not fetch current vendor prices or inspect account balances.
- A provider without a price is identified separately and still needs explicit unknown-price acknowledgment for a live run.
- A provider authentication test is not performed because even a test endpoint may consume credits or have provider-specific side effects.

## Verification performed

Python syntax, catalog JSON parsing, and `git diff --check` are the planned local checks. No test suite or provider request was run.

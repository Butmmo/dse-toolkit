# Stage 68: Local waterfall builder

## What changed

Added a new HQ Tools action, **Lead enrichment: build a provider waterfall**, and the matching command `python dse.py enrich --build-waterfall-config`. It accepts a unique config name; ordered comma-separated local adapter names per field (email, phone, person identity, and firmographics); a call cap for each field; email stop policy; and confidence/identity thresholds.

Before writing anything, the builder checks that the selected adapters exist, their local JSON is valid, their email or field-specific response mappings exist, and their configured price metadata is valid. It saves a complete `dbi.waterfall-config.v1` JSON under `enrich-waterfalls/`. API keys are read only from environment variables when relevant and are never copied into the config. Existing config files are never overwritten; choose a new name to create another version.

## Suggested sequence

1. Add or configure each provider adapter on the PC, keeping API keys in Windows user environment variables.
2. Use the builder to choose provider order, call caps, and acceptance thresholds.
3. Run **Preview provider spend** against the saved config and intended row count.
4. In the live enrichment action, select that same config and approve the previewed ceiling. Unknown-priced providers still require the explicit Stage 66 acknowledgment.

## Scope and safeguards

- Provider names are adapter identifiers configured locally, not vendor credentials.
- The tool does not call a provider, access leads, or edit an existing config.
- Each field may contain up to 12 unique adapters in order.
- Existing provider-specific cost entries remain user-maintained estimates. The builder surfaces missing prices rather than inventing them.
- A provider without the required response mapping is rejected for that field.

## Verification performed

Python syntax, catalog JSON parsing, and `git diff --check` are the planned local checks. No test suite or paid provider request was run.

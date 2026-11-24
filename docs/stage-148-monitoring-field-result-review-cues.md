# Stage 148: Monitoring review cues in field results

Herald and Presence source-monitoring outputs now include their persisted primary action and concise evidence text in the shared `field_results` contract. Users and downstream review surfaces can inspect the monitoring decision and why it was suggested without depending on separate CSV columns.

The evidence text is capped at 1,800 characters and may include source URLs, freshness changes, identity changes, event cues, or coverage caveats. Existing source candidates and category references remain available alongside the values.

These are heuristic review cues. They do not verify a source, prove a business event, or trigger outreach or other actions. A missing search result remains inconclusive when query coverage is partial.

Validation: Python syntax compilation, toolkit CLI help, catalog JSON parsing, and `git diff --check`. No tests were run.

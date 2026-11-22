# Stage 42: Clarify executable enrichment profiles

## What changed

- Path profile output now reports `executable_defaults` instead of incorrectly describing profiles as preview-only.
- The profile payload explains that supported CSV and live-grid runners apply selected defaults.
- CLI profile output separates enforceable settings from caveats: expected coverage is unmeasured, and a spend limit is advisory unless the configured provider waterfall enforces it.
- The in-grid Enrich and Signals tabs now explain what a path profile guides and remind users to review source evidence.

## Limits

This is a wording and contract correction; it does not add provider support, guarantee coverage, or make an advisory spend ceiling enforceable. Stage 41 implementation notes describe the existing supported runner behavior. No Supabase SQL is required. No automated tests were run.

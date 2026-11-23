# Stage 122: Waterfall experiment preflight

Added a read-only HQ Tool and CLI preflight before running a paired provider-order experiment.

The preflight requires the matching A and B drafts created by the experiment builder. It checks their experiment ID, field, provider pair, source-config fingerprint, and that their only config difference is the selected provider-order swap. It reads the first requested number of source CSV rows to derive the same stable lead IDs used by enrichment runs, rejects duplicate IDs, and reports a SHA-256 fingerprint of the source file and bounded cohort.

It reviews both drafts for local key presence, adapter mappings, provider caps, prices, and currencies. It adds the conservative maximum estimates for A and B, compares that combined amount with a single user-entered ceiling, and requires explicit acknowledgement when any provider price is unknown. The result states whether the pair is ready; it makes no network/provider requests, writes no files, and returns no lead row values or API key values.

Validation performed: Python compilation of `dse.py` and `dse/waterfall.py`, `dse.py enrich --help`, and JSON parsing of `bridge/catalog.json`. No provider calls were made.

The implementation was pushed to codex/hq-runner-id-routing and installed in the active PC runner checkout. The runner restarted and reported 182 tools online. The user's local packs/automation.json change in that checkout was preserved.

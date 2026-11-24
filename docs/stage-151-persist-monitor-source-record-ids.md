# Stage 151: Persist monitoring source record IDs

Compact Ledger monitor-history cue references now carry the retained source signal's record ID when the current run retained that exact URL. The ID is copied into the category-linked source reference, alongside its category, URL and URL fingerprint, so the app can render the source cue and evidence record together after sync.

Unmatched source URLs keep an empty `record_id`; they are still shown as source links and are not discarded. This is a compact row-history change and does not add source snippets or lead contact data.

Validation: Python syntax compilation, toolkit CLI help, catalog JSON parsing, and `git diff --check`. No tests were run.

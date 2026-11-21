# Lead enrichment, Stage 1: sourced public signals

**Date:** 21 November 2026  
**Status:** Implemented on the working branch; not yet installed on the live PC runner or deployed in Citadel.

## What this stage adds

The new `dse.enrich_signals` HQ Tools entry runs `python dse.py signals <lead.csv>`. It researches up to 50 rows per run using a small set of public web searches for the business, its products or services, news, and public search results for indexed social pages.

Each result is saved with an evidence ID, title, excerpt, query, source URL, provider, matched company-name terms, and UTC retrieval time. These are search-result clues, not verified facts. The tool does not sign in to social networks, scrape private profiles, or send messages.

When local Ollama is available and `--no-ai` is not selected, the tool asks a model on the user's PC to draft one subject and one short email body from the evidence. It prefers the user's configured local model, then an installed Qwen model, then the existing local-model fallback. The CSV records the model and evidence IDs used. If there is no evidence or the model does not return evidence IDs, the draft remains blank. Drafts are never sent.

## Output fields

- `research_findings`: readable titles and snippets with evidence IDs.
- `research_sources`: JSON array with URLs, search queries, match terms, retrieval time and provider for each result.
- `research_searched_at` and `research_status`: freshness and whether a draft is available for review.
- `outreach_subject`, `outreach_body`, `outreach_evidence`, `outreach_model`: optional local-AI draft and its traceability.

Original lead columns are retained. The run also saves a CSV and a short Markdown run summary under `my-lists/`. The Markdown warns that search-result claims need human source review.

## Where the results can be used

- **Ledgers:** add the researched CSV as a lead grid; findings and source JSON remain ordinary columns beside the lead data.
- **Engine / Send Desk:** choose an engine in the HQ Tools form to also save the CSV to that engine's imports. The importer now carries the research and outreach fields through. For email-channel rows, the Send Desk draft uses the AI body and includes `Subject: ...` at the top for copying. Other channels keep their existing engine wording.
- **Herald:** import the CSV as a lead list. Its existing extra-column merge tags can use `{{outreach_subject}}`, `{{outreach_body}}`, `{{research_findings}}`, and `{{research_sources}}`. Review these fields and the message preview before starting a campaign.
- **HQ Tools:** the result CSV and its Markdown summary are attached to the completed job as output files.

## Search provider choice

This stage uses DuckDuckGo's public HTML search results for broad web discovery and indexed social-page snippets. It does not claim that a snippet proves a current fact. Google Places remains the separate existing source for place/business facts where a user's configured Places key is available.

The Google Custom Search JSON API is not a sound foundation for a new general-search feature: Google's official page says it is closed to new customers and existing customers must transition before 1 January 2027. See [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview) and [Google Places Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search). A future stage can add a supported, user-configured search provider adapter without changing this output format.

## Limits and next stage

This first slice does not crawl or authenticate to LinkedIn, Instagram, Facebook, X, or TikTok. Search engines may return stale, mismatched, or unavailable results; users should open the source URL before putting any claim into outreach. A local model can still write an unsuitable draft, so sending remains a human decision.

Next stages should add provider adapters for stronger search and public-source retrieval, source freshness/relevance controls, richer social-post evidence where the platform makes it available under its developer terms, and a Herald review flow that can select per-lead generated fields without manually inserting merge tags.

## Ledger import and Engine-bound schedules

The scheduled-result Ledger dialog could show an Engine picker, yet the final import RPC could still reject that same CSV as unlinked. The dialog sent the selected Engine, but the database's scheduled-job check depended on the schedule status's rolling job history. This stage adds an Engine field to schedule records and copies it into each queued job as reserved `engine_ref` metadata. The PC runner ignores that metadata when constructing tool arguments, while Ledger import uses it to validate the destination Engine.

Lead/list-producing schedules now require an Engine when saved. The schedules page also shows the linked Engine, and **Run now** carries it to the job. The existing Add CSV to Ledger dialog continues to support choosing an Engine after a legacy schedule run that has no stored Engine link.

The app and migration changes are in the Citadel branch. The error shown in the screenshot ("This CSV is not linked to an engine. Run Lead enrichment again and choose its engine first") comes from an older deployed import function: that wording is not in the current migration, which allows legacy scheduled results to choose an Engine during import. In Supabase, run the updated `20261231130000_hq_csv_ledgers.sql` first if it has not been applied with its scheduled-result support, then run `20261231180000_engine_linked_schedules.sql`. New schedules will keep their Engine attached to future jobs. If an old job still fails after the updated import function is installed, download its CSV and upload it manually to the chosen Engine's Ledger as a temporary route.

## Planned lane separation for the next stage

The next planned design separates two kinds of Send Desk context:

- **Herald-facing outreach intelligence:** HQ Tools, DBI-AI, Ledgers and Herald coordinate through Ledger workflows and automations. This lane covers company/contact fit, business signals, and reviewable outreach drafts.
- **Presence-facing social reputation intelligence:** HQ Tools, DBI-AI and Presence coordinate through Presence functions and Presence-native tools. This lane covers public social profiles, posts and reputation signals.

Both lanes can refer to one lead, but findings should be source-linked and stored/displayed separately. Presence observations should not silently become claims in a Herald email. A later implementation should add explicit, reviewable handoffs between the lanes rather than mixing their evidence by default.

## Changed code in this stage

- Added `dse/signal_enrichment.py` for public search, evidence capture, optional local Ollama drafting, and CSV/Markdown outputs.
- Added the `signals` CLI command in `dse.py`.
- Added `dse.enrich_signals` to the generated runner catalog.
- Preserved the new fields when importing leads into an engine and used the local email draft in the engine's Send Desk CSV.
- Added Engine-bound schedule fields, job metadata propagation, and scheduling UI/SQL paths for future lead/list results.
- Recorded the planned Herald-facing versus Presence-facing Send Desk split above for the next stage.

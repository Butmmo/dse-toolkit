# Lead enrichment, Stage 2: separate Herald and Presence lanes

**Date:** 21 November 2026  
**Status:** Implemented on the existing DSE Toolkit and Citadel branches; not yet installed on the live PC runner or deployed.

## What changed

Stage 1's `dse.enrich_signals` now searches for company, product/service and news evidence for the Herald-facing lane. It writes explicit `herald_*` columns, keeps the earlier `research_*` column names as compatibility aliases, and may draft an email subject/body with local Ollama. Social-platform searches are no longer mixed into that evidence set.

A separate `dse.presence_signals` HQ Tools entry and `python dse.py presence-signals leads.csv` command searches public indexed business profiles/posts, plus a supplied contact's professional profile when the result also matches the business. It writes `presence_signals`, `presence_sources`, `presence_checked_at` and `presence_status` separately. It does not create an outreach draft or send anything. Results are public search snippets, not verified identities or reputation scores; users should open the source and decide what is relevant. The tool excludes private content and does not infer sensitive personal traits.

The Presence tool also writes a structured `*-shelf.json` file. Citadel's Presence > Research lists that file among its HQ Tools results and lets the user add it to the Presence research shelf. It is labeled **Public social signals** and remains separate from Herald's outreach fields. Saved facts retain source URLs and can be selected as context for a Presence content draft after human review.

Send Desk rows now carry two separate, expandable evidence sections: **Herald-facing · business and outreach** and **Presence-facing · public social signals**. Herald's section can show the business findings, email subject, evidence IDs and source links. Presence's section shows public profile/post snippets and source links. Old rows and engines without these fields show a clear empty-state message. The PC sync caps the displayed evidence per row to keep the upload small.

## Where the data goes

- **Herald-facing:** business/news evidence and optional email drafts stay in `herald_*` (and legacy `research_*`) fields, Engine imports and the existing Send Desk email output.
- **Presence-facing:** public professional/business social evidence stays in `presence_*` fields and can be explicitly added to Presence > Research from the attached JSON output.
- Both are carried through Engine CSV imports, but Presence evidence does not automatically become Herald message context and Herald email drafts do not automatically enter Presence research.

## Limits and next steps

Search engines may return stale, unrelated or wrongly attributed pages. This slice does not log into social networks, scrape private content, calculate a person's character/reputation score, or verify account ownership. Better platform-specific evidence should use approved public APIs or user-provided links and record source/time and matching confidence. A later slice can add an explicit reviewed handoff from Presence findings to Ledger/Herald workflows when the user chooses it.

## Changed code

- Split business/news search and social search into separate DSE commands and runner catalog tools.
- Added Presence-specific CSV evidence and shelf JSON output.
- Added parsing and a labeled import route in Citadel Presence > Research.
- Preserved Herald and Presence evidence fields in Engine import and Send Desk outputs.
- Added separate JSON context columns and labeled panels to Send Desk. Apply `20261231200000_send_desk_research_lanes.sql` in Supabase; a runnable copy is in the Citadel repo's `sql-to-run` folder.

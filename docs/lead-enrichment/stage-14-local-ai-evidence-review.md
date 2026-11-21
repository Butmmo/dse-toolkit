# Stage 14: local AI evidence review

## What changed

When an approved local Ollama model is available for lead enrichment, the existing per-lead model call now returns both the outreach draft and a structured research review. The review keeps company and named-person summaries separate, allows only the supplied role targets, lists unresolved questions, and links summaries and role observations to source IDs.

Before writing the review to CSV, the toolkit validates IDs against the returned source list. Company summaries can cite only company-matched sources; person summaries can cite only matched person sources; role observations must cite evidence IDs already attached to that deterministic role assessment. If no valid sources support a summary, that section is blank. Review fields are carried through the engine importer and Send Desk.

If a draft is not returned but a valid AI review is, the lead status reports that an evidence review is ready rather than claiming an email draft exists. This is local model advice, not verification, sending, or automated approval.

## Limits

Local model output may still be mistaken. Review summaries, questions, and citations against the source links before relying on them. The review only runs when the user has enabled AI drafting and a local model is available; no cloud model is called.

No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: local review prompt, source-ID validation, and output fields.
- `dse/importer.py`: preserve review fields on import.
- `dse/engines.py`: pass the review to Send Desk output.

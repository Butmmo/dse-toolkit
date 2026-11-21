# Stage 13: source-linked outreach evidence ledger

## What changed

Local AI outreach drafting now receives the separate company and person signal context, the ranked people candidates, and identity details for each public source. The prompt distinguishes identity-matched personal evidence from company role discovery, treats input signals as search context rather than proof, and prefers supported current positions over previous roles.

Drafted rows now include `outreach_evidence_detail`: a compact JSON record for every source ID the model cited, including the source subject, type, identity match and strength, score, title, URL, and retrieval time. `outreach_personalization_basis` provides a short human-readable summary. Existing `outreach_evidence` remains the comma-separated source-ID field for compatibility. The importer and Send Desk output preserve the new fields.

## Limits

The evidence ledger records which sources the model says it used; it does not prove that every sentence in the draft is supported. Review the linked source and draft before use. Drafting remains local through Ollama and does not send email.

No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: prompt inputs and source-linked draft evidence.
- `dse/importer.py`: preserve ledger fields on import.
- `dse/engines.py`: pass them into Send Desk output.

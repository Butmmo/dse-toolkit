# Stage 37: Guarded local DBI-AI path advice

## What changed

Herald's existing local Ollama review call now also receives the deterministic path outcome, observed facts, qualification checks, and retained search evidence. It may return a separate `dse_path_ai_advice` record with a suggested human validation step and neutral questions. Every advice and question citation is filtered against source IDs classified as priority/supporting for the selected path; records without valid path sources are discarded.

Advice remains separate from the deterministic path outcome and existing research fields. It cannot set qualification, infer need/budget/ability to pay, alter findings, launch workflows, or send outreach. The shared field-result contract labels it local-model advice and requires human review. The Ledger evidence panel shows the local model, advice, source IDs, questions, and guardrail text.

Local advice uses the already enabled local AI review/draft call; `Only collect signals/evidence` disables it. No cloud model is called. The advice is created only when a local Ollama model is available and path-fit source evidence exists.

## Validation

- Python syntax compilation and catalog JSON parsing.
- Git diff checks.
- Citadel production build after the UI update.

No Supabase SQL is needed. Update the PC toolkit and rerun Herald enrichment to generate advice for existing rows.

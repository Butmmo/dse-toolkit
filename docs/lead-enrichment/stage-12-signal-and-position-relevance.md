# Stage 12: separate signal and position relevance

## What changed

Signal-based role targeting now reads the decision maker's personal lead signal and the company's lead signal independently. It merges the plausible role targets while preserving each role's origin (`person_signal`, `company_signal`, or explicit/default selection). Herald runs separate company role-discovery searches for those two signal streams when both are present.

Candidate review ordering now records overlap with the supplied current position, previous position, and the corresponding personal or company lead signal. Current position and current signal have greater influence than prior position. Each candidate includes matched terms and the signal subject used for comparison. Company-matched role-discovery results now remain in company-source fields, while named-person-matched results remain in person-source fields.

## Limits

Position and signal overlap are text matching cues. Their weighted candidate score is an ordering aid, not a probability or a claim that the person currently holds a role. Search result text may omit context; reviewers should confirm the current role and company at the linked source.

No Supabase SQL is required. No tests were run for this slice.

## Files

- `dse/signal_enrichment.py`: separate person/company signal searches, role provenance, and subject-specific source fields.
- `dse/classification.py`: position/signal overlap and relevance details in candidate ordering.

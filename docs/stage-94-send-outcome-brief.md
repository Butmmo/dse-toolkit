# Stage 94: Human-readable Send Desk experiment brief

`eval-enrichment score-send-outcomes` now writes both the detailed JSON report and a Markdown brief by default. The brief puts assigned leads, sent leads, replies, booked calls and wins beside their observed rates and 95% Wilson intervals. It labels cohorts below 30 sent leads and calls out leads shared between variants, then repeats the limits on interpretation in plain language.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine>
python dse.py eval-enrichment score-send-outcomes <engine> --experiment-id <id> --markdown-out my-lists\experiment-outcomes.md
```

The Markdown path defaults to the JSON output path with a `.md` extension. `--markdown-out` overrides it. The JSON schema remains the machine-readable source; no automatic selection or causal claim is introduced.

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

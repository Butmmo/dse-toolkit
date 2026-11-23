# Stage 97: Show experiment send execution coverage

The per-variant Send Desk report now separates assigned leads into:

- **Sent:** at least one tagged row has an explicit sent or outcome tap (an outcome tap proves it was sent).
- **Skipped:** explicitly skipped and never sent on any tagged touch.
- **Unmarked:** neither sent nor explicitly skipped.

The JSON includes send coverage, skip, and unmarked rates per assigned lead. The Markdown comparison table surfaces the counts and send coverage. This helps explain whether low reply or win counts reflect outreach results or incomplete execution/logging. A lead marked sent on any touch is not counted as skipped even if another touch was skipped.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine>
```

This remains based on explicit local Send Desk taps and does not verify actual mailbox delivery. Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

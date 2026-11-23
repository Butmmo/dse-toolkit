# Stage 98: Show logged reply dispositions by experiment variant

The outcome report now summarizes existing Send Desk reply categories for each experiment field and variant. It counts unique lead IDs per category, includes only explicitly logged non-out-of-office replies, and writes the category counts into JSON and the Markdown brief. A lead can have different logged replies on separate touches, so category groups are intentionally nonexclusive and their counts may exceed the unique-reply-lead total.

This reuses existing Reply Desk labels; it does not reclassify reply text, inspect message content, or send data to an AI service. Out-of-office auto-replies remain excluded from reply categories and reply outcomes.

```powershell
python dse.py eval-enrichment score-send-outcomes <engine>
```

Validation for this slice: Python compilation, CLI help, and `git diff --check`; no test suite was run.

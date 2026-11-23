# Stage 91: Keep waterfall experiment tags on follow-ups

Follow-up list generation now copies the waterfall experiment ID, A/B variant, field, provider pair, stable lead ID, and config SHA-256 from the originating first-touch row. This keeps variant attribution attached to later touches in the Send Desk lists. The existing tap log remains keyed by source-list name and row ID, so a disposition can be joined to the tagged list row without changing log status behavior or migrating old logs.

Non-experiment follow-up rows retain their prior columns. The metadata is for analysis only and does not change due dates, sequence selection, channel choice, or message text.

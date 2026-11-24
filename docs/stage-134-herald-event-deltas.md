# Stage 134: Detect Herald event changes within unchanged sources

## What changed

Herald's Ledger monitoring now compares the event categories and path-fit labels from the newest complete Ledger snapshot with the current complete check. It can surface a new event cue or an existing cue newly classified as priority for the selected business path, even when the source URL and page title are unchanged. Each cue retains its source URL and event label in the row's review evidence.

Event summaries are stored compactly with the shared Ledger history so another PC can continue the comparison. Older snapshots that do not contain event categories continue to work: they are used as source baselines, and event-category comparison begins once a new event-aware snapshot is saved. Partial searches do not become baselines.

## Interpretation limits

These categories are generated from public search evidence and are heuristic. A new cue or priority classification is a prompt for a person to inspect the linked source, not proof that an event occurred or that a business is qualified. The feature does not send email or create outreach. Event disappearance alone is not treated as proof that an event reversed.

## Validation

Python compilation, CLI help with UTF-8 console mode, catalog JSON parsing, and `git diff --check` are required before release. No provider calls are made. No tests are run.

The change is committed and pushed to `codex/hq-runner-id-routing`, then installed in the active PC runner checkout.

# Stage 149: Normalize monitoring review cues

Herald and Presence monitoring field results now expose a shared `review` object with the suggested action, explanatory evidence, change categories, and structured source references. Consumers can render one consistent review panel for either lane instead of parsing lane-specific JSON strings and arrays.

The existing top-level fields remain available for compatibility. Malformed category/source JSON safely becomes an empty list. Only structured source objects are included in the normalized source list.

These remain heuristic review cues that need human confirmation; the shared shape does not change their confidence or trigger outreach.

Validation: Python syntax compilation, toolkit CLI help, catalog JSON parsing, and `git diff --check`. No tests were run.

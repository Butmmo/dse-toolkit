# Stage 105: Review waterfall outcomes in HQ Tools

The PC runner catalog now exposes **Waterfall experiments: score Send Desk outcomes**. Choose an Engine, optionally filter to an experiment ID, and set a fixed observation window. The connected PC reads that Engine's local send lists and explicit disposition log, then writes the existing aggregate JSON and Markdown outcome reports. HQ Tools attaches those report artifacts to the completed job.

The report contains counts and rates by variant, send coverage, reply categories, maturity-window outcomes, provider/config metadata, and descriptive uncertainty. It does not read reply/message text, call providers, send outreach, or choose a winner. Only the aggregate report files are attached; the source lead-list rows and message contents stay on the PC.

Experiment IDs are validated before they are used in report filenames. They may contain letters, numbers, dots, underscores, and hyphens, up to 80 characters.

This is a runner catalog update: fetch the toolkit and restart the connected PC runner to show the tool in HQ Tools. No `dbi-citadel` screen or migration change was needed because the tools panel uses the PC runner's published catalog.

Validation for this slice: catalog generator execution, Python compilation, CLI help, catalog structure/size check, and `git diff --check`; no test suite was run.

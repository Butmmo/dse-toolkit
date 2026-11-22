# Stage 23: HQ enrichment tool metadata

## What changed

Added structured discovery metadata to the DSE Toolkit catalog for the existing website, lead-signal, and Presence enrichment tools. The metadata records the tool category, research source, cost conditions, expected output summary, and relevant Engine paths where applicable. The existing `outputs` file patterns remain intact for the runner.

HQ Tools can use this catalog metadata to explain tool choices without guessing at provider pricing or output files.

## Verification

Catalog regenerated with `python bridge/add_enrich_tools.py`. Python syntax compilation and Git whitespace checks remain to be run before commit. No SQL is required; no runner install is included.

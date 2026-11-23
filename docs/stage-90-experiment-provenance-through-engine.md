# Stage 90: Keep experiment provenance through Engine imports

The experiment ID, A/B variant, target field, provider pair, stable lead ID, and exact waterfall config SHA-256 now pass through the enrichment import-ready CSV, Engine CSV normalization, and the generated Engine lead list. This lets the experiment provenance survive the usual enrich → import → build-list path for later operational analysis. Ordinary non-experiment imports do not get these extra columns from the enrichment import-ready exporter.

The tags are descriptive metadata only. They do not alter lead selection, scoring, channel choice, outreach content, or sending behavior. Ordinary non-experiment imports and generated lists retain their previous column set.

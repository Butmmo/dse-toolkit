# Stage 78: Evaluation score provenance

The enrichment score JSON now includes `scoring_provenance` with the UTC scoring time, SHA-256 digest of the exact review CSV bytes, and all thresholds, bootstrap replicate counts, and seeds used for this run. The optional Markdown brief repeats the timestamp and source digest so copied summaries remain traceable to their input file. The absolute source path remains available in the JSON report.

The digest lets a reviewer verify that a later score used the exact same input bytes. To reproduce the same report values, use the same input CSV and recorded settings; the UTC timestamp itself will naturally differ on a later run. The provenance does not validate label quality or sample representativeness.

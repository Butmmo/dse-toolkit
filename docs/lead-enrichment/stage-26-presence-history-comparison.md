# Stage 26: Compare Presence checks over time

## What changed

Repeated Presence social searches now compare the current source URLs with the previous saved check for the same lead. The CSV and Presence shelf report the prior check time, newly returned links, links whose search snippet/title/publication date changed, and links not returned by a complete comparison. Partial searches are labeled `partial_check` or `partial_first_check`; they do not mark missing results as not returned and do not replace the last complete baseline. The first complete check is clearly labeled as a baseline.

History is stored locally at `data/presence-history.json`, keyed by a SHA-256 hash of stable business/contact identifiers. The snapshot retains only source URL, title, subject, snippet hash, publication date and freshness, and expires after 180 days. It does not retain raw lead names or email addresses in the history file. The current CSV still carries the sources it already reports.

## Interpretation

A result that is absent from a later search is only described as “not returned”; search rankings and snippets can vary, so it does not mean the post or profile was deleted. Changed snippets or titles can reflect search-index changes, so they are review prompts and not proof that the underlying post/profile changed. Newly returned links are candidates for human review, not proof that a business has changed or improved its reputation. Existing person/company separation and freshness labels remain intact.

## Verification

Compile the changed Python files, regenerate and parse the toolkit catalog, and inspect the diff. No live social search or automated tests are run in this slice.

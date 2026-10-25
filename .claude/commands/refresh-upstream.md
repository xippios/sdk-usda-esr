Refresh the upstream documentation snapshot for USDA FAS Export Sales Reporting: $ARGUMENTS

The snapshot in `docs/upstream/` is the reference for every endpoint wrapper
(ADR-0003). It is refreshed deliberately, by PR, so changes are visible as diffs.

1. Work on a branch `docs/upstream-<yyyy-mm-dd>`.
2. A source whose documentation needs a reproducible capture keeps
   `scripts/refresh_upstream.py`. Where it exists, run it from the repository root as its
   docstring says, usually `uv run scripts/refresh_upstream.py`, and skip the by-hand
   fetch. Otherwise fetch the documentation pages from
   https://apps.fas.usda.gov/opendatawebV2/ (and any pages the arguments name). Save each page under
   `docs/upstream/` as Markdown where the page is HTML (convert, keep headings, tables and
   parameter lists; drop navigation) or as the original file where it is JSON, YAML,
   OpenAPI or PDF. A table with merged cells (`rowspan`, `colspan`) or a nested table
   stays HTML inside the Markdown file: a pipe table would lose its structure. Keep file
   names stable across refreshes so diffs are meaningful.
3. Update `docs/upstream/FETCHED.md` (conventions §3, ADR-0003): per file the URL, the
   `Fetched` time and a note, `Fetched` being the UTC time of the run in ISO 8601 with an
   explicit `Z` (`date -u +%FT%TZ`, e.g. `2026-10-24T09:15:00Z`), never a local date or
   time, and the note saying where a table is kept as HTML; and under Attribution the
   copyright line as the documentation states it (`© 2026 Example Ltd.`), or that it
   states none. Where `scripts/refresh_upstream.py` writes the file itself, it writes the
   same, and you check it instead.
4. Diff against the previous snapshot: `git diff --stat docs/upstream/` and read the
   changes. Summarise in the PR description what changed upstream: new or removed
   operations, renamed or newly required parameters, changed semantics, and which
   wrappers in `src/xippios/usda/esr/api/` are affected.
5. Do not change any code in this PR, with one exception: `scripts/refresh_upstream.py`,
   the capture script, may change with the snapshot it captures. If wrappers must follow,
   list them as follow-up issues or `/add-endpoint` runs.
6. Open the PR with the definition-of-done checklist. Do not merge.

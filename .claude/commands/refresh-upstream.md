Refresh the upstream documentation snapshot for USDA FAS Export Sales Reporting: $ARGUMENTS

The snapshot in `docs/upstream/` is the reference for every endpoint wrapper
(ADR-0003). It is refreshed deliberately, by PR, so changes are visible as diffs, and
captured by `scripts/refresh_upstream.py`, so that a refresh is reproducible. The PR
meets the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and the
reviewer judges it against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. Work on a branch `docs/upstream-<yyyy-mm-dd>`.
2. **Compare first.** Where the script is filled, `uv run scripts/refresh_upstream.py
   --check` fetches everything and compares it with the snapshot, writing nothing: exit
   0 means upstream serves what the snapshot records, `Fetched` aside, and there is
   nothing to refresh unless the arguments name new pages; exit 1 names the files that
   differ. A capture script of the source's own shape without `--check` is run as its
   docstring says, and the diff in step 5 does the comparing.
3. **Fill the script where it is still the template's skeleton** (it refuses to run
   until `PAGES` or `SPEC_URL` is set), once, then keep it in step with upstream:
   - `PAGES`: the documentation pages from https://apps.fas.usda.gov/opendatawebV2/ and any the arguments
     name, each with its file under `docs/upstream/`, the names stable across refreshes so
     diffs are meaningful: Markdown where the page is HTML, the original file where it is
     JSON, YAML, OpenAPI or PDF. A page the snapshot records without a file, a 403 or a
     404 or a page without documentation text (a client-rendered shell), is a shell row,
     `Page(url, status=403, note=...)`, with `stable=False` where its body changes on
     every request (a per-request reference).
   - `SPEC_URL`, the convention for a machine-readable API document (an OpenAPI or
     Swagger file) that the documentation names inside a page rather than links (a Swagger
     UI's configuration, a page's settings): find it there, record its URL in `SPEC_URL`,
     and the script keeps the document verbatim as `SPEC_FILE`. Where the page's setting
     must be read on every run, the script reads it there instead, and `CAPTURE` says
     from where. The `Documentation` row of `CLAUDE.md` points here.
   - `reduce`, where a page is not kept as fetched. HTML becomes Markdown, its headings,
     tables and parameter lists kept and its navigation dropped, with `markdownify`, the
     one converter a capture script may declare: `dependencies = ["markdownify==X.Y.Z"]`
     in the script's `# /// script` block, and the same pin in the dev group of
     `pyproject.toml`, so that `mypy --strict` reads its types; the two pins move
     together. A table with merged cells (`rowspan`, `colspan`) or a nested table stays
     HTML inside the Markdown file, since a pipe table would lose its structure, and its
     row's note says so. A source whose API is one part of a shared upstream document
     keeps its part (`load_json`, which stops unless the whole document re-serialises to
     the fetched text, then `dump_json`) and marks the page `excerpt=True`: its row
     records the whole document's size and sha256 (conventions §3).
   - `ATTRIBUTION`: every copyright line, licence or terms of use the documentation
     states, as printed (`© 2026 Example Ltd.`), or none. The script checks every page on
     every run and stops, before writing, when one states something not recorded.
   - `CAPTURE`: how the snapshot is captured, a few sentences for `FETCHED.md`; and the
     module docstring, which says what the script captures.
4. **Capture.** `uv run scripts/refresh_upstream.py` fetches every page before it writes
   anything, then writes the files and regenerates `docs/upstream/FETCHED.md` (conventions
   §3, ADR-0003): `Fetched`, the UTC time of the run in ISO 8601 with an explicit `Z`;
   under Attribution the statements as recorded, or that the documentation states none;
   one row per file and per page recorded without a file, with its HTTP status, the size
   and sha256 of the body as fetched, and ETag and Last-Modified where sent. Read the
   result.
5. Diff against the previous snapshot: `git diff --stat docs/upstream/` and read the
   changes. Summarise in the PR description what changed upstream: new or removed
   operations, renamed or newly required parameters, changed semantics, and which
   wrappers in `src/xippios/usda/esr/api/` are affected.
6. Do not change any code in this PR, with one exception: `scripts/refresh_upstream.py`,
   the capture script, may change with the snapshot it captures, and so may the
   converter's pin in the dev group (`pyproject.toml`, `uv.lock`). If wrappers must
   follow, list them as follow-up issues or `/add-endpoint` runs.
7. Stage the snapshot (`git add docs/upstream scripts`) before
   `uv run pre-commit run --all-files`, which checks only the files in git's index: an
   unstaged new file would escape the secret scan.
8. Open the PR, its body as the definition of done says. Do not merge.

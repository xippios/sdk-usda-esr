Refresh the upstream documentation snapshot for USDA FAS Export Sales Reporting: $ARGUMENTS

The snapshot in `docs/upstream/` is the reference for every endpoint wrapper
(sdk-core ADR-0028). It is refreshed deliberately, by pull request, so changes are visible
as diffs (conventions §3), and captured by `scripts/refresh_upstream.py`, so that a
refresh is reproducible. The change meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **Compare first.** Where the script is filled, `uv run scripts/refresh_upstream.py
   --check` fetches everything and compares it with the snapshot, writing nothing. It
   compares content: a file after `canonical`, and `FETCHED.md` but for its rows'
   measures, Fetched, Bytes, sha256, ETag and Last-Modified. Exit 0 means upstream
   serves what the snapshot records, and there is nothing to refresh unless the arguments
   name new pages; a measure that moved while the content stayed is printed as
   information. Exit 1 names the files that differ. A capture script of the source's own
   shape without `--check` is run as its docstring says, and the diff in step 4 does the
   comparing.
2. **Fill the script where it is still the template's skeleton** (it refuses to run
   until `PAGES` or `SPEC_URL` is set), once, then keep it in step with upstream:
   - `PAGES`: the documentation pages from https://apps.fas.usda.gov/opendatawebV2/ and any the arguments
     name, each a `Page(url, file)` with its file under `docs/upstream/`, the names stable
     across refreshes so diffs are meaningful: Markdown where the page is HTML, the
     original file where it is JSON, YAML, OpenAPI or PDF. A page the snapshot records
     without a file, a 404 or a page without documentation text (a client-rendered
     shell), has no file, `Page(url, status=404, note=...)`, and `stable=False` where its
     body changes on every request (a per-request reference, a nonce), which keeps its
     Last-Modified and leaves the reason to its note. The other kinds of page:
     - a page that is itself the terms, kept whole, `terms=True`: it must print each
       statement `ATTRIBUTION` records from it, and nothing else on it is searched;
     - a small answer of the API, kept verbatim under `docs/upstream/samples/`,
       `sample=True`: it documents the answer's shape and is no test fixture, and its row
       says so (conventions §3). The skeleton sends no credential, so a sample whose
       operation needs the source's credentials is requested by a capture script of the
       source's own, and neither a credential nor a token is written;
     - a page read for one fact it holds, such as the page that names the API document,
       recorded without a file, `names=` that text: a page that no longer holds it stops
       the run;
     - a page that an anonymous client cannot read, `status=403`, or `status=302` where it
       redirects to a login on another host: requested once, without credentials, its row
       goes to `Not fetched` with its status and the host it redirects to. The script
       follows no redirect to another host and imitates no browser (conventions §3);
     - a page whose URL another page gives, such as the newest release's page in a
       publication's list of releases: `linked`, which reads the page that gives it and
       names it, captured right after.
   - `NOT_FETCHED`: each page the documentation links that the snapshot deliberately does
     not request, a feed, a third-party specification (cited, not snapshotted), an API
     answer or a page that is no API documentation, as `NotFetched(url, reason)`; its row
     in `FETCHED.md`'s table `Not fetched` gives the reason.
   - `SPEC_URL`, the convention for a machine-readable API document (an OpenAPI or
     Swagger file) that the documentation names inside a page rather than links (a Swagger
     UI's configuration, a page's settings): find it there, record its URL in `SPEC_URL`,
     and the script keeps the document verbatim as `SPEC_FILE`. Where the page's setting
     must be read on every run, the script reads it there instead, and `CAPTURE` says
     from where. `SPEC_PAGE` replaces the document's row where it needs another, such as
     a document served in a new order on each request. The `Documentation` row of
     `CLAUDE.md` points here.
   - `reduce`, where a page is not kept as fetched. HTML becomes Markdown, its headings,
     tables and parameter lists kept and its navigation dropped, with `markdownify`, the
     one converter a capture script may declare: `dependencies = ["markdownify==X.Y.Z"]`
     in the script's `# /// script` block, and the same pin in the dev group of
     `pyproject.toml`, so that `mypy --strict` reads its types; the two pins move
     together. The packages markdownify pulls in are pinned in the block at the versions
     `uv.lock` holds, or the block sets `exclude-newer` under `[tool.uv]` to the date of
     the pin, so that a release of theirs cannot change the conversion. markdownify's
     types name `convert` and `convert_soup` alone: a conversion of the script's own
     subclasses `MarkdownConverter` and types the parsed elements its hooks receive as
     `Any`, which come from markdownify, so the script declares nothing else. The
     standard library's `html.parser` is no dependency: a script that converts with it
     declares none. A table with merged cells (`rowspan`, `colspan`) or a nested table
     stays HTML inside the Markdown file, since a pipe table would lose its structure, and
     its row's note says so. A source whose API is one part of a shared upstream document
     keeps its part (`load_json`, which stops unless the whole document re-serialises to
     the fetched text, then `dump_json`) and marks the page `excerpt=True`: its row
     records the whole document's size and sha256 (conventions §3).
   - `canonical`, where a document comes in a new order on each request with nothing else
     changed, such as an API document whose members do: the form with the order fixed,
     which `--check` compares, so a new order is no change; `reduce` returns that form
     too where the file is to be written in it.
   - `ATTRIBUTION`: every copyright line, licence or terms of use the documentation
     states, as printed (`© 2026 Example Ltd.`), or none, each a
     `Statement(text, source, where, link)`: its text as printed, the URL of the page that
     prints it, where it stands, and the URL it links to where it is a link. The script
     reads each page's visible text, its comments and scripts left out, and a binary file
     not at all. On every run it stops, before writing, when a page no longer prints a
     statement recorded from it, or states one not recorded; an API document's `info`
     names a licence, terms or a contact only as a statement recorded from it. A
     statement on a page whose text the script does not read, a PDF or a sample, is quoted
     as one no run checks, and read again by hand at each refresh. A line
     that only a browser shows, a footer a script assembles, is seen by no fetch: record
     it from a browser, by hand, with `source=""` and, in `where`, the page and the date
     it was read on, so that `FETCHED.md` quotes it, and read it again at each refresh.
   - `VOCABULARY`: the words that stop the run without stating anything, a field of the
     API or a trade term, which the search then reads past; `FETCHED.md` lists them, and
     `CAPTURE` says why. It is the other way out of a stop, beside recording a statement.
   - `CAPTURE`: how the snapshot is captured, a few sentences for `FETCHED.md`; and the
     module docstring, which says what the script captures.
3. **Capture.** `uv run scripts/refresh_upstream.py` fetches every page before it writes
   anything, then writes the files and regenerates `docs/upstream/FETCHED.md` (conventions
   §3, sdk-core ADR-0028): `Fetched`, the UTC time of the run in ISO 8601 with an explicit
   `Z`; under Attribution the statements as recorded, or that the documentation states
   none; one row per file and per page recorded without a file, with its HTTP status, the
   size and sha256 of the body as fetched, and ETag and Last-Modified where sent; a row
   for `docs/upstream/OBSERVED.md` where it exists; and the table `Not fetched`. Read the
   result.
4. Diff against the previous snapshot: `git diff --stat docs/upstream/` and read the
   changes. Summarise in the pull request what changed upstream: new or removed
   operations, renamed or newly required parameters, changed semantics, and which
   wrappers in `src/xippios/usda/esr/api/` are affected.
5. What upstream does but never documents, a type, a field, an answer's shape or a
   refusal that departs from the documentation, goes in `docs/upstream/OBSERVED.md`, the
   one file under `docs/upstream/` written by hand, each note with its evidence: the
   probe's date, operation and sample. The script neither writes nor checks it, and
   lists it in `FETCHED.md`. Notes the source keeps elsewhere, in its README or its
   capture script, move there with this refresh (conventions §3).
6. Run again each script of the source's own that reads `docs/upstream/`, such as one
   that takes names or columns from a snapshot's table, since a refresh can change what
   it reads, and say in the pull request what it found.
7. Change no code with the snapshot, with one exception: `scripts/refresh_upstream.py`,
   the capture script, may change with the snapshot it captures, and so may the
   converter's pin in the dev group (`pyproject.toml`, `uv.lock`). If wrappers must
   follow, list them as follow-up issues or `/add-endpoint` runs.
8. A changelog fragment under `changelog/`, as `changelog/README.md` lays it out, says
   what the refreshed snapshot records that changed upstream.
9. Stage the snapshot (`git add docs/upstream scripts`) before
   `uv run pre-commit run --all-files`, which checks only the files in git's index: an
   unstaged new file would escape the secret scan. A row the script writes with an ETag
   ends in the scan's allowlist mark, since an ETag of hex digits reads to the scan as a
   secret. Then run the other checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

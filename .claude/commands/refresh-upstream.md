Refresh the upstream documentation snapshot for USDA FAS Export Sales Reporting: $ARGUMENTS

The snapshot in `docs/upstream/` is the reference for every endpoint wrapper
(sdk-core ADR-0028). It is refreshed deliberately, by pull request, so changes are visible
as diffs, and captured by `scripts/refresh_upstream.py`, so that a refresh is
reproducible; conventions §3 holds its rules, and core's README, under "The snapshot
script's frame", the frame that serves them. The change meets sdk-core's definition of
done, https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its
review checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **Compare first.** Where `SNAPSHOT` names its pages, `uv run scripts/refresh_upstream.py
   --check` fetches everything and compares it with the snapshot, writing nothing, the one
   comparison of the snapshot with upstream (conventions §3). Exit 0 means upstream
   serves what the snapshot records, and there is nothing to refresh unless the arguments
   name new pages; exit 1 names the files that differ.
2. **Fill the declaration where it names no page yet**, once, then keep it in step with
   upstream. `scripts/refresh_upstream.py` declares `SNAPSHOT`, a `Snapshot` that core's
   frame, `xippios.core.refresh`, runs: it fetches each page through core's client, checks
   the attribution, writes the files and `FETCHED.md`, compares with `--check`, and
   refuses to run while `pages` is empty. The script imports and declares alone, its run
   under `if __name__ == "__main__":`. A source fills these fields, and its module
   docstring, which says what the script captures:
   - `pages`: the documentation pages from https://apps.fas.usda.gov/opendatawebV2/ and any the arguments
     name, each a `Page(url, file)` with its file under `docs/upstream/`, named stably:
     Markdown where the page is HTML, the original file where it is JSON, YAML, OpenAPI or
     PDF. A page recorded without a file, a 404 or a client-rendered shell, takes
     `Page(url, status=404, note=...)`, and `stable=False` where its body changes on every
     request. The other kinds of page:
     - the terms, kept whole, `terms=True`;
     - a small answer of the API under `docs/upstream/samples/`, `sample=True`, which is
       no test fixture; one whose operation needs the source's credentials takes
       `keyed=True`, and the declaration takes the source's own client, `client=`, and the
       variables its credentials read, `variables=`: such a sample alone sends them,
       `--keyless` fetches the rest, and neither a credential nor a token is written;
     - a page read for one fact it holds, recorded without a file, `names=` that text;
     - a page that an anonymous client cannot read, `status=403`, or `status=302` where it
       redirects to a login on another host, whose row goes to `Not fetched`;
     - a page whose URL another page gives, such as the newest release in a list of
       releases: the hook `linked`, which reads the row of the page that gives it.
   - `not_fetched`: each page the documentation links that the snapshot deliberately does
     not request, as `NotFetched(url, reason)`.
   - `SPEC_URL`, a constant of the script, where the documentation names a machine-readable
     API document inside a page rather than links it: the document kept verbatim as one of
     `pages`, `Page(SPEC_URL, "openapi/openapi.json", note="SPEC_URL, verbatim")`, or read
     on every run by `linked`. The `Documentation` row of `CLAUDE.md` points here.
   - `reduce`, where a page is not kept as fetched. HTML becomes Markdown with the
     source's converter, pinned in the dev group of `pyproject.toml` and locked in
     `uv.lock`: markdownify, whose types name `convert` and `convert_soup` alone, so a
     conversion of the script's own subclasses `MarkdownConverter` and types its hooks'
     elements as `Any`, or the standard library's `html.parser`, which needs no pin. A
     table with merged cells or a nested table stays HTML. A source whose API is one part
     of a shared document keeps its part with `read_json` and `dump_json` and marks the
     page `excerpt=True`.
   - `canonical`, a hook where a document comes in a new order on each request with
     nothing else changed: the form with the order fixed, which `--check` compares.
   - `attribution`: every copyright line, licence or terms of use the documentation
     states, as printed, each a `Statement(text, source, where, link)`, or none, which the
     frame checks on every run. A statement on a page the frame does not read, a PDF or a
     sample, and a line that only a browser shows, recorded by hand with `source=""` and
     the page and the date in `where`, are read again by hand at each refresh.
   - `vocabulary`: the words that stop the run without stating anything, a field of the
     API or a trade term, which `capture` explains.
   - `capture`: how the snapshot is captured, a few sentences for `FETCHED.md`.

   Every hook stops the run with core's `changed` on a page it does not recognise, before
   anything is written. What some sources do beyond these, a row's note made from its
   answer, several files from one page, a section of their own, the wait for a 429 that
   the client's retry policy gives, a file kept as recorded where only its order moved,
   by `reduce`, and a page from the publisher's second origin, as two declared pages, the
   declaration takes as the table of core's README under "The snapshot script's frame"
   gives it.
3. **Capture.** `uv run scripts/refresh_upstream.py` fetches every page before it writes
   anything, then writes the files and `docs/upstream/FETCHED.md` whole, in the one form
   that its last line names (conventions §3). Read the result.
4. Diff against the previous snapshot: `git diff --stat docs/upstream/` and read the
   changes. Summarise in the pull request what changed upstream: new or removed
   operations, renamed or newly required parameters, changed semantics, and which
   wrappers in `src/xippios/usda/esr/api/` are affected.
5. What upstream does but never documents goes in `docs/upstream/OBSERVED.md`, the one
   file under `docs/upstream/` written by hand, each note with its evidence, as
   conventions §3 lays it out. Notes the source keeps elsewhere move there with this
   refresh.
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
   unstaged new file would escape the secret scan. Then run the other checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

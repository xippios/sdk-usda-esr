Refresh the packaged reference data for USDA FAS Export Sales Reporting: $ARGUMENTS

Reference data the upstream publishes for every caller alike (code lists, attribute
lists, report calendars) may ship inside the package under
`src/xippios/usda/esr/reference/` and is loaded with `xippios.core.reference`. It
comes from the upstream, never from memory. Not every source packages lists: one that
changes often stays a lookup task that calls upstream. A multi-tenant source
(sdk-core ADR-0036) packages no tenant data, only reference lists that are the same for
every tenant, if any. The change meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. Identify the upstream list endpoint for each list named in the arguments, using
   `docs/upstream/`; a wrapper for it belongs in `api/` (`/add-endpoint`).
2. Add the list to `LISTS`, `ID_LISTS` or `TABLES` in `scripts/refresh_reference.py`,
   as its docstring says for the list's shape (a list of values, a list of integer ids
   and names, or a table: conventions §3), with the upstream operation it comes from,
   and its name to `PACKAGED_LISTS` in `params.py`; then run the script from the
   repository root with whatever the list endpoints need in the environment (a key only
   where they take one). It fetches every list, writes each `reference/<name>.json` with
   `PackagedList.write` (the operation, the UTC time of the fetch, upstream's records),
   regenerates `enums.py` with one `render_enums` call and formats it with `ruff format`
   and `ruff check --fix` (sdk-core ADR-0031); commit both as the script leaves them. It
   sends each request once, with no retry, so a run that fails writes nothing and is run
   again, and after the fetches it prints the requests it sent and the quota left that
   upstream reported, a failed run's too: say both in the pull request.
   `--only <list> ...` fetches the named lists
   alone and keeps every other list's file, so a change that packages a new list
   refreshes that list and no other.
   `uv run python scripts/refresh_reference.py --render-only` regenerates `enums.py`
   from the packaged files alone, without a request or a key, as an adoption does after
   a core release changes the renderer (conventions §15, item 6). A source whose script
   keeps a shape of its own, with other names than `LISTS`, `ID_LISTS`, `TABLES` and
   `PACKAGED_LISTS` or with `PACKAGED_LISTS` left empty, follows that script's docstring
   instead.
3. Update the provenance table in `reference/README.md`: the file, its origin (the
   endpoint or URL it was fetched from, or the `docs/upstream/` file it was rebuilt from)
   and the fetch time (for a rebuilt file, the snapshot's `Fetched` time).
4. If agents have no lookup task for this list yet, add one with `/add-endpoint` so they
   can look the codes up: one lookup task per list (`list_<thing>`), or the upstream's
   own lookup operation when it serves every list through one. A lookup over a packaged
   list returns the packaged data, it does not call upstream. A list an agent needs whole
   that is longer than the default result cap (200 rows or 64 KB) gets a cap of its own,
   `MCP_CAPS` in `tasks.py`, keyed by the task's name (sdk-core ADR-0038).
5. Update what pins the old lists: counts and dates in list-task docstrings and in
   tests. A test that reads the counts and the fetch date, `fetched`, from the packaged
   file needs no change (`/add-endpoint`, step 6), where a pinned `fetched` changes with
   every refresh. A test that compares a packaged list with the recorded answer of its
   list endpoint fails once a record changes: record those fixtures again in the same
   change with `/record-fixture`, and add their calls to the requests the refresh sent.
6. A changelog fragment under `changelog/`, as `changelog/README.md` lays it out, says
   which lists changed.
7. Run the checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`,
   and summarise the diff in the pull request: how many rows changed, any codes that
   disappeared (those may break existing fixtures or callers).

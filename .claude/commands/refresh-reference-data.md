Refresh the packaged reference data for USDA FAS Export Sales Reporting: $ARGUMENTS

Reference data the upstream publishes for every caller alike (code lists, attribute
lists, report calendars) may ship inside the package under
`src/xippios/usda/esr/reference/`, from the upstream and never from memory, as
conventions §3 lays it out; a list that changes often stays a lookup task that calls
upstream. The change meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. Identify the upstream list endpoint for each list named in the arguments, using
   `docs/upstream/`; a wrapper for it belongs in `api/` (`/add-endpoint`).
2. Declare the list as one `Listed` of `LISTS` in `scripts/refresh_reference.py`, the
   script's one `Lists(package, lists, packaged, client, quota_header, before, after)` of
   `xippios.core.refresh`, as the script's examples show for its shape: its name, which
   is its file `reference/<name>.json` and what `--only` takes; its fetch through the
   wrapper in `api/`; `endpoint`, the upstream operation it comes from; its
   `Enumeration`, if any; and its `origin` where its provenance row names more than that
   operation. Add its name to `PACKAGED_LISTS` in `params.py`, which the script hands
   core's frame as `packaged`. Then run the script from the repository root with whatever
   the list endpoints need in the environment (a key only where they take one). Its one
   call, `run(declaration, argv=None)`, fetches every list before it writes one, each
   request once, and writes the packaged files, their rows in `reference/README.md` and
   `enums.py` as one, so a run that fails writes nothing and is run again; commit what it
   leaves. It prints the requests it sent and the quota left that upstream reported, a
   failed run's too: say both in the pull request. `--only <list> ...` refreshes the named
   lists alone and keeps every other list's file, and
   `uv run python scripts/refresh_reference.py --render-only` writes `enums.py` and the
   provenance rows from the packaged files alone, without a request or a key, as an
   adoption does after a core release changes the renderer (conventions §15, item 6).
   What a script writes beside the lists goes in the hooks `before` and `after` of `Lists`.
3. Read the list's row in the provenance table of `reference/README.md`, which the run
   wrote: the file, its origin and the UTC time of the fetch.
4. Declare the list for the nightly live comparison in `tests/test_live.py`, which
   collects core's test: in `LIVE_LISTS`, by its name, its codes as the package declares
   them, `PackagedList.codes(...)`, and the wrapper in `api/` that fetches it now, or in
   `NO_LIVE_LIST` with the reason it is not compared, a list that no endpoint serves, say.
   Core's family check fails a packaged list that stands in neither (conventions §10).
5. If agents have no lookup task for this list yet, add one with `/add-endpoint` so they
   can look the codes up: one lookup task per list (`list_<thing>`), or the upstream's
   own lookup operation when it serves every list through one. A lookup over a packaged
   list returns the packaged data and does not call upstream, and a list an agent needs
   whole gets a cap of its own in `MCP_CAPS` (conventions §8).
6. Update what pins the old lists: counts and dates in list-task docstrings and in
   tests. A test that reads the counts and the fetch date, `fetched`, from the packaged
   file needs no change (`/add-endpoint`, step 6). A test that compares a packaged list
   with the recorded answer of its list endpoint fails once a record changes: record
   those fixtures again in the same change with `/record-fixture`, and add their calls to
   the requests the refresh sent.
7. A changelog fragment under `changelog/`, as `changelog/README.md` lays it out, says
   which lists changed.
8. Run the checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`,
   and summarise the diff in the pull request: how many rows changed, any codes that
   disappeared (those may break existing fixtures or callers).

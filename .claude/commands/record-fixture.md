Record a fixture for USDA FAS Export Sales Reporting: $ARGUMENTS

Expected arguments: `<wrapper> <case> [key=value ...]`: the endpoint wrapper the fixture
serves, or the task whose every exchange it records (step 3), a short name for the case,
and the request parameters, for example `get_series_by_year north_2024 region_code=R1 year=2024`.

Fixtures are recorded through the real client, never typed in by hand, and land at
`tests/fixtures/<wrapper>/<case>.json` with credentials scrubbed, named as conventions §10
names them. A source with a recorder of its own, `scripts/record_fixture.py`, records with
it. A fixture rides in the change of the task it tests, which meets sdk-core's definition
of done, https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its
review checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md:
steps 4 to 6 are what they check in a fixture.

1. The credential comes from the environment, `DATA_GOV_API_KEY`: never read, test or print that variable, not even to see whether it is set (conventions §7). The client's auth reads it when it sends and refuses an unset or empty one before anything is sent, with a `ConfigError` that names the variable, never a value.

2. Find the request path and parameters for the endpoint in `docs/upstream/` and in the
   wrapper under `src/xippios/usda/esr/api/`. Use the wrapper's parameter names.

3. Record it with a one-off script run through `uv run python`:

   ```python
   from pathlib import Path

   from xippios.core.testing import fixture_path, record
   from xippios.usda.esr._client import client

   fixture = record(
       client,
       "<request path>",  # relative to the base URL, as in the wrapper
       fixture_path(Path("tests/fixtures"), "<wrapper>", "<case>"),
       params={...},  # the parameters from the arguments
   )
   print(fixture.response.status, fixture.request.url)
   ```

   `record` sends the one request through `client` itself, never retried and never
   answered from the cache, keeps a 4xx or a 5xx as it came and refuses an answer of a 1xx
   or a 3xx status before anything is written (conventions §10); a script on an event loop
   awaits `record.async_fn` with the same arguments. A wrapper that routes to a second base
   passes that base's absolute URL in place of the request path; the fixture's directory
   is still the wrapper's. Error cases, a 404 for an unknown code say, are worth recording.

   A task that sends more than one request, a count and its data, a series of periods or
   the pages of a list, is recorded by the source's own capture, as conventions §10 lays
   it out: the task called as a caller calls it, each
   exchange built with `fixture_from_response(response, scrub=..., rewrite=...)` and all
   of them written with `write_fixture(fixture, path)` once every one passed, under the
   task's name as `<case>.json`, `<case>_2.json` and on.

   A downloaded file's fixture is the GET exchange of the file's URL, absolute where the
   file lives on another host, to which the client sends no credential, since it sends
   them to its base URL's origin alone (conventions §6); its envelope keeps the URL,
   `recorded_at`, the `ETag` and `Last-Modified` headers, and for a cut body the whole
   file's size and sha256 (step 5).

4. Check the file: `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<wrapper>/<case>.json`
   must print nothing but `REDACTED` values, and for a task's recording the same over
   each file it wrote,
   `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<task>/<case>.json tests/fixtures/<task>/<case>_*.json`.
   A match in upstream's own text (a word such as `SECRETARY` in a name) is no credential:
   read every match by eye. If a credential slipped through, delete the file and stop:
   report which field leaked so the scrubber in `xippios-core` can learn it.
   A documented personal identifier the source keeps out of its projections (`ssn`,
   `iban` and their like, conventions §3) is recorded with `scrub=Scrub(secrets=[...])`,
   which replaces each value in its every encoded form, or rewritten by `rewrite=`, a step
   of the source's own, a `Rewrite` that `xippios.core.testing` exports. The step writes
   `REDACTED` for a field of the request and drops none (conventions §10). A source that
   needs the answer itself sends the one request with `send_once`, which writes nothing,
   and builds and writes the fixture as a task's capture does. Grep each file for those
   fields too (`grep -nE '"(ssn|iban)"' <file>`): every match must show a scrubbed value,
   and a real value found means the file is deleted, never committed.

5. The fixture file stays under 256 KiB, as `ci.yml` checks (conventions §10). Narrow
   the query first. A JSON array too large for the cap is recorded with `max_bytes=`
   (`80_000` keeps the file under the cap), or `keep="last"` beside it for a list ordered
   oldest first; the recorder cuts no other body, so record a small real answer or a
   sample instead, whose file lives under `tests/fixtures/files/<file_kind>/` with its
   row in `tests/fixtures/files/README.md`.

6. Reference it from a test with the `replay_fixture("<wrapper>", "<case>")` fixture, and
   each exchange of a task's recording by its own case,
   `replay_fixture("<task>", "<case>_2")` and on. Stage it (`git add tests/fixtures`) before `uv run pre-commit run --all-files`, which
   scans only the files in git's index: an unstaged fixture escapes detect-secrets. When
   detect-secrets flags a recorded HTML error page (a site's "Page not found" carries
   hashes it reads as secrets), never edit the fixture to pass it: narrow the request,
   or drop the fixture and keep the status alone, named in the PR description with the
   call counted. An HTML error body is kept only when a test needs it.

   A line of a fixture that the scan flags and a person judged no secret is an audited
   entry of `.secrets.baseline`, `"is_secret": false`, which names the fixture's path
   twice: as its key under `results` and as its own `"filename"`. A pull request that
   renames or moves the fixture, a directory renamed by conventions §10 say, moves its
   entries to the new path in the same commit, the key and each `"filename"` both, their
   audit kept, and stages the baseline with the move. The hook flags the lines again
   while either still names the old path or the baseline's change is unstaged, and
   `uv run detect-secrets scan --baseline .secrets.baseline` keeps them under the new
   path with the audit dropped.

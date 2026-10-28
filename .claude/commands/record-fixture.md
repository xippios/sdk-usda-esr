Record a fixture for USDA FAS Export Sales Reporting: $ARGUMENTS

Expected arguments: `<endpoint> <case> [key=value ...]`: the upstream operation the wrapper
is named after, a short name for the case, and the request parameters, for example
`get_example by_year year=2024`.

Fixtures are recorded through the real client, never typed in by hand (conventions §10).
The file lands at `tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed. It
rides in the PR of the task it tests: the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, lists its
checks, and the reviewer judges them against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. Confirm `DATA_GOV_API_KEY` is set in the environment (`[ -n "${DATA_GOV_API_KEY}" ] && echo ok`); never print its value.

2. Find the request path and parameters for the endpoint in `docs/upstream/` and in the
   wrapper under `src/xippios/usda/esr/api/`. Use the wrapper's parameter names.

3. Record it with a one-off script run through `uv run python`:

   ```python
   from pathlib import Path

   from xippios.core.testing import fixture_path, record_sync
   from xippios.usda.esr._client import client

   fixture = record_sync(
       client,
       "<request path>",  # relative to the base URL, as in the wrapper
       fixture_path(Path("tests/fixtures"), "<endpoint>", "<case>"),
       params={...},  # the parameters from the arguments
   )
   print(fixture.response.status, fixture.request.url)
   ```

   Error cases (a 404 for an unknown code, for instance) are worth recording too; the
   recorder keeps them instead of raising. A source whose upstream counts a quota records
   through a client that never retries, so a 5xx spends no quota on a retry; core's
   `record` takes no `retry=`, so pass such a client in place of `client`:
   `AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)), auth=auth)`,
   with `AsyncClient` and `RetryPolicy` from `xippios.core` and
   `config` and `auth` from `xippios.usda.esr._client`.

   A downloaded file's fixture is the GET exchange of the file's URL, the one the
   download task streams: pass that URL in place of the request path, absolute where
   the file lives on another host, with `auth=None` there so the client's credentials
   never go to it. The plugin replays it for the download call, and its envelope keeps
   the provenance: the URL, `recorded_at`, the `ETag` and `Last-Modified` headers where
   upstream sends them, and, for a cut body, the whole file's `original_bytes` and
   `sha256` (step 5).

4. Check the file: `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<endpoint>/<case>.json`
   must print nothing but `REDACTED` values. A match in upstream's own text (a word such
   as `SECRETARY` in a name or a description) is no credential: read every match by eye.
   If a credential slipped through, delete the file and stop: report which field leaked
   so the scrubber in `xippios-core` can learn it. Where the response carries a documented
   personal identifier the source keeps out of its projections (`ssn`, `iban` and their
   like, ADR-0017), record with `scrub=Scrub(secrets=[...])` from `xippios.core.testing`,
   or rewrite those values by key in a recorder step of the source's own, on the
   `Fixture` before the write (ADR-0024), and grep the file for those fields too
   (`grep -nE '"(ssn|iban)"' <file>`, with the fields the source declares): every match
   must show a scrubbed value. A real value found means the file is deleted, never
   committed.

5. The fixture file stays under 256 KiB (conventions §10, ADR-0019 decision 5); `ci.yml`
   fails on a larger one. Narrow the query first. A text body or a JSON array too large
   for the cap is recorded with `max_bytes=` (`80_000` keeps the file under the cap: it
   bounds the body, which the file escapes as a JSON string): a JSON array keeps its
   first whole elements, cut in upstream's own text, a text its first bytes, and the
   envelope marks the cut with `truncated: true`, `original_bytes` and `sha256` of the
   whole body and, for an array, `original_count`; replay serves the cut body. The
   recorder refuses `max_bytes=` on a JSON object, whose parts are no list to take the
   first of: record a small real answer instead (a short date range, one commodity). An
   XML, ZIP, gzip, XLS or XLSX body is never cut either, nor one that is not UTF-8 text:
   record a small real sample (a short query, one member of the archive, a few rows). A
   downloaded file is recorded whole when it is small, else with `max_bytes=` where it
   is text. The sample file a parser test reads is no recorded exchange: it lives under
   `tests/fixtures/files/<file_kind>/`, its provenance one row in
   `tests/fixtures/files/README.md` (ADR-0020). A test on a cut fixture or a sample
   asserts the shape, never a size.

6. Reference it from a test with the `replay_fixture("<endpoint>", "<case>")` fixture.
   Stage it (`git add tests/fixtures`) before `uv run pre-commit run --all-files`, which
   scans only the files in git's index: an unstaged fixture escapes detect-secrets. When
   detect-secrets flags a recorded HTML error page (a site's "Page not found" carries
   hashes it reads as secrets), never edit the fixture to pass it: narrow the request,
   or drop the fixture and keep the status alone, named in the PR description with the
   call counted. An HTML error body is kept only when a test needs it.

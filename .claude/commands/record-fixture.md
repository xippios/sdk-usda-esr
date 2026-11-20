Record a fixture for USDA FAS Export Sales Reporting: $ARGUMENTS

Expected arguments: `<wrapper> <case> [key=value ...]`: the endpoint wrapper the fixture
serves, a short name for the case, and the request parameters, for example
`get_example by_year year=2024`.

Fixtures are recorded through the real client, never typed in by hand (conventions §10).
The file lands at `tests/fixtures/<wrapper>/<case>.json` with credentials scrubbed: the
directory is named after the wrapper function (conventions §2), and `<case>` is
lowercase snake case for the words you choose, an upstream code inside it written as
upstream writes it (`CH_2026_8.json`). A fixture recorded through a task rather than a
wrapper, such as a download's metadata or a helper's answer, lives under the task's
name. It rides in the change of the task it tests, which meets sdk-core's definition of
done, https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its
review checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md:
steps 4 to 6 are what they check in a fixture.

1. The key comes from the environment, `DATA_GOV_API_KEY`: never read, test or print that variable, not even to see whether it is set. The client guards the key itself: where the variable is unset or empty, it refuses on its first request, before anything is sent, with a `ConfigError` that names the variable, never a value.

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
       fixture_path(Path("tests/fixtures"), "<wrapper>", "<case>"),
       params={...},  # the parameters from the arguments
   )
   print(fixture.response.status, fixture.request.url)
   ```

   A wrapper that routes to a second base of the upstream passes that base's absolute URL
   in place of the request path, as the wrapper does; the fixture's directory is still
   the wrapper's.

   Error cases (a 404 for an unknown code, for instance) are worth recording too; the
   recorder keeps them instead of raising. A recording is one request: the recorder sends
   it once through `client`, never retried, whatever the client's `RetryPolicy` says, and
   never answered from the cache, so a 429 or a 5xx is recorded as it came and spends no
   second request on an upstream that counts a quota (conventions §10). Pass
   `client` itself: a recording needs no client of its own.

   A downloaded file's fixture is the GET exchange of the file's URL, the one the
   download task streams: pass that URL in place of the request path, absolute where
   the file lives on another host. The client sends its credentials to the base URL's
   origin alone, its scheme, host and port, so a file on another host is recorded
   without them and needs no `auth=None` (conventions §6). The plugin replays it for the
   download call, and its envelope keeps the provenance: the URL, `recorded_at`, the
   `ETag` and `Last-Modified` headers where upstream sends them, and, for a cut body,
   the whole file's `original_bytes` and `sha256` (step 5).

4. Check the file: `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<wrapper>/<case>.json`
   must print nothing but `REDACTED` values. A match in upstream's own text (a word such
   as `SECRETARY` in a name or a description) is no credential: read every match by eye.
   If a credential slipped through, delete the file and stop: report which field leaked
   so the scrubber in `xippios-core` can learn it. Where the response carries a documented
   personal identifier the source keeps out of its projections (`ssn`, `iban` and their
   like, sdk-core ADR-0017), record with `scrub=Scrub(secrets=[...])` from
   `xippios.core.testing`, or rewrite those values by key in a recorder step of the
   source's own. `record` writes the file itself and takes no hook, so that step sends the
   request itself, with `request(..., raise_on_error=False)` on a client built for one
   attempt,
   `AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)), auth=auth)`,
   with `AsyncClient` and `RetryPolicy` from `xippios.core` and
   `config` and `auth` from `xippios.usda.esr._client`. It builds the
   `Fixture` in memory with `fixture_from_response(response, scrub=...)`, rewrites the
   values on it and writes it with `write_fixture(fixture, path)`, both from
   `xippios.core.testing`, which lays it out as `record` does, so nothing unscrubbed
   touches disk (conventions §10). Grep the file for those fields too
   (`grep -nE '"(ssn|iban)"' <file>`, with the fields the source declares): every match
   must show a scrubbed value. A real value found means the file is deleted, never
   committed.

5. The fixture file stays under 256 KiB (conventions §10); `ci.yml` fails on one over it
   that a pull request adds or changes. A fixture over the cap that a pull request only
   moves, its content unchanged, stays as it was recorded until a pull request records
   it again, and that recording cuts it: no fixture is kept whole over the cap by
   exception. Narrow the query first. A text body or a JSON answer too large for the cap
   is recorded with `max_bytes=` (`80_000` keeps the file under the cap: it bounds the
   body, which the file escapes as a JSON string). A JSON array keeps its first whole
   elements, or its last with `keep="last"` for a list ordered oldest first, cut in
   upstream's own text; a JSON object is cut the same way, at the array of the top-level
   key that `array_key=` names (`array_key="data"` for `{"data": [...]}`), the rest of
   the object kept as upstream wrote it; a text keeps its first bytes. The envelope marks
   the cut with `truncated: true`, `original_bytes` and `sha256` of the whole body and,
   for an array, `original_count`; replay serves the cut body. The recorder refuses
   `max_bytes=` on a JSON object without `array_key=`: name the key, or record a small
   real answer instead (a short date range, one commodity). An XML, ZIP, gzip, XLS or
   XLSX body is never cut, nor one that is not UTF-8 text: record a small real sample (a
   short query, one member of the archive, a few rows). The recorder reads at most
   32 MiB of a body (`max_read_bytes=`) and refuses a larger answer before it writes
   anything. A downloaded file is recorded whole when it is small, else with
   `max_bytes=` where it is text. The sample file a parser test reads is no recorded
   exchange: it lives under `tests/fixtures/files/<file_kind>/`, its provenance one row
   in `tests/fixtures/files/README.md` (sdk-core ADR-0020). A test on a cut fixture or a
   sample asserts the shape, never a size.

6. Reference it from a test with the `replay_fixture("<wrapper>", "<case>")` fixture.
   Stage it (`git add tests/fixtures`) before `uv run pre-commit run --all-files`, which
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

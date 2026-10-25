Record a fixture for USDA FAS Export Sales Reporting: $ARGUMENTS

Expected arguments: `<endpoint> <case> [key=value ...]`: the upstream operation the wrapper
is named after, a short name for the case, and the request parameters, for example
`get_records by_year year=2024`.

Fixtures are recorded through the real client, never typed in by hand. The file lands at
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed.

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
   recorder keeps them instead of raising.

4. Check the file: `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<endpoint>/<case>.json`
   must print nothing but `REDACTED` values. If a credential slipped through, delete the
   file and stop: report which field leaked so the scrubber in `xippios-core` can learn it.
   Where the response carries a documented personal identifier the source keeps out of
   its projections (`ssn`, `iban` and their like, ADR-0017), record with
   `scrub=Scrub(secrets=[...])` or `Scrub(rewrite=...)` from `xippios.core.testing`, and
   grep the file for those fields too (`grep -nE '"(ssn|iban)"' <file>`, with the fields
   the source declares): every match must show a scrubbed value. A real value found means
   the file is deleted, never committed.

5. Keep the fixture small enough to review (narrow the query if the body is huge), then
   reference it from a test with the `replay_fixture("<endpoint>", "<case>")` fixture.

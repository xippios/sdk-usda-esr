# sdk-usda-esr — instructions for Claude Code

`xippios-usda-esr` wraps USDA FAS Export Sales Reporting as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and its code rules. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file.

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA FAS Export Sales Reporting, https://www.fas.usda.gov/programs/export-sales-reporting-program |
| API base URL | `https://api.fas.usda.gov`, api.data.gov's gateway (the portal document's `host`): `BASE_URL` is the host root, and every path keeps the snapshot's `/api/esr/` prefix (`/api/esr/commodities`, `/api/esr/exports/commodityCode/{commodityCode}/...`) |
| Documentation | https://apps.fas.usda.gov/opendatawebV2/, snapshotted in `docs/upstream/` |
| Credentials | `DATA_GOV_API_KEY` from the environment, sent as the `X-Api-Key` header by `xippios.core.data_gov`'s `Gateway` (`_client.auth` is `gateway.auth`); the key is api.data.gov's, shared by every package that reads `DATA_GOV_API_KEY`. sdk-core ADR-0032: one key variable per issuer when one key serves several sources, so every source reached through api.data.gov (`usda-psd`, `usda-esr`, `usda-gats`) reads `DATA_GOV_API_KEY`, and one key is one gateway quota |
| Rate limit | sdk-core ADR-0033, decisions 1–5. Pace: 60 requests per minute, burst 1 (`RateLimit(per_minute=60, burst=1)` in `_client.py`, enforced client-side): a self-imposed pace, upstream documents none (the snapshot names no limit). Quota: api.data.gov's 1,000 requests per rolling hour per key, reported in `x-ratelimit-limit` / `x-ratelimit-remaining` on every keyed answer (the hourly quota, not a pace) and shared with `usda-psd`, `usda-gats` and every process using the same `DATA_GOV_API_KEY`; it may be spent, it is not pre-rationed. The quota is the gateway's: `Gateway.policy` of `xippios.core.data_gov`, one `QuotaPolicy` per process for the key, which `_client.py` installs with `gateway.install` (sdk-core ADR-0032, sdk-core ADR-0037), keeps the snapshot from every answer from the wire, never a cache hit's, and gates: once the quota is spent the next request waits it out inside the call, logged, when that is within the policy's `pause_cap` (30 s by default), and otherwise raises `RateLimitError` with `retry_after` without sending, a refusal that speaks for `api.data.gov` (its `source`). The wait counts from the last answer: a 429's `Retry-After`, else the policy's `window` of one hour (the gateway sends no reset header). `gateway.classify`, which `classify` asks first, maps the 429 (`OVER_RATE_LIMIT`, not recorded for ESR) to `RateLimitError` with `retry_after` the wait the policy keeps the quota spent for, from `Retry-After`, else 3600 s, and core shapes its retries from that: a wait beyond `RetryPolicy.backoff_max` is raised after one request. In offline tests core's pytest plugin bypasses the limiter and the quota policy and forgets the snapshot around each test; a test that asserts a wait or a refusal is marked `rate_limited` |
| Write tools | no, this package is read-only |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

`_client.py` builds on `xippios.core.data_gov.Gateway` (sdk-core ADR-0032, decision 5; sdk-core
ADR-0023), which holds what every source behind api.data.gov shares: the `X-Api-Key` auth, the
one `QuotaPolicy` per process on `x-ratelimit-*`, the `API_KEY_*`, `OVER_RATE_LIMIT` and
`NOT_FOUND` mappings with host-free messages, and, since `Gateway(SOURCE, data_path=DATA_PATH)`
names the exports paths, ESR's empty 404 there as core's `NoDataForYear`
(https://github.com/xippios/sdk-core/issues/106). `classify` asks `gateway.classify` first and
keeps ESR's own answers after it, an empty 404 elsewhere and the 400 below.

## Upstream behaviour the package relies on

The snapshot types every response as `object` and defines no schema, so what ESR does beyond
it, the answers' shapes, its empty answers and its refusals, is noted in
`docs/upstream/OBSERVED.md`, each note with the probe that showed it: its date, its
operation and the recording under `tests/fixtures/` or the request. This section holds what
the package does with it; `_client.classify` maps ESR's own answers once.

- Codes are `int`, as the snapshot types the path parameters and as the wire carries them
  (https://github.com/xippios/sdk-usda-esr/pull/3): `get_exports(104, 2024, 1220)`.
- Record shapes of the four lists, the exports records and the release list are in
  `models.py`, each naming its fixture: the eight quantities as `Decimal` (net sales can be
  negative), `weekEndingDate` as `date`, the countries' names padded as upstream sends them.
  A week that straddles two market years comes in each, and the records carry no market
  year, so `get_weekly_series` keeps both, the older year's row first.
- `allCountries` has no paging. Over MCP `get_exports` keeps the family's cap, 200 rows or 64
  KB, with a note of its own that names `country_code` (`tasks.MCP_CAPS`; conventions §8,
  sdk-core ADR-0038; https://github.com/xippios/sdk-usda-esr/pull/3), and the cap's note tells
  agents to pass it: one destination is up to 54 rows. `get_weekly_series` makes one request
  per market year, at most 10 per call (`tasks.SERIES_MAX_YEARS`) in Python, over HTTP and over
  MCP alike, and over MCP keeps the same cap, about three market years, with a note of its own
  that names `start_year` and `end_year` (https://github.com/xippios/sdk-usda-esr/pull/10).
- Destination `9990` (UNKNOWN) comes in `allCountries` as a row like any country's: the
  slices keep and rank it like any other code.
- Empty means empty, not an error: `params` refuses unknown codes (`UnknownCode`, naming the
  nearest codes) and market years after the current UTC year plus two before the call. A
  market year ESR has not released cannot be told from one without exports, so
  `get_weekly_series` reads the release list for a range that ends in the current UTC year or
  later and refuses one past the commodity's current market year with `NotFoundError` naming
  the latest released one (https://github.com/xippios/sdk-usda-esr/pull/10; conventions §4;
  sdk-core ADR-0041, decisions 6 and 7). The current year counts too: a market year named by
  it may have begun without a week released, as a calendar-year commodity's does in January.
- ESR's empty 404 for a market year it holds no data for (1900) is mapped by the gateway to
  core's `xippios.core.data_gov.NoDataForYear`, a `NotFoundError` (only that answer on an
  exports path, `_client.DATA_PATH`). `get_weekly_series` skips such a year inside its
  range, as sdk-usda-psd's `get_time_series` does, and a released year answering `[]`
  adds no rows (https://github.com/xippios/sdk-usda-esr/pull/10). Where ESR's data begins
  is not established, so no lower bound beyond four digits is set
  (`params.EARLIEST_MARKET_YEAR`).
- ESR's 400 for a path value that is not an integer is mapped to `InvalidRequestError`;
  never sent, since parameters are `int`.
- api.data.gov's 403 for an invalid key is mapped by the gateway to `AuthError` naming the
  code and `DATA_GOV_API_KEY`.
- `meta.vintage` of `get_exports` is the latest `weekEndingDate` among the records as
  an ISO date (`"2024-06-06"` for wheat white to Canada 2024), `None` for an empty
  answer, and its `meta.published_at` stays `None`: it makes no second call
  (https://github.com/xippios/sdk-usda-esr/pull/3). `get_release_dates`'
  `meta.published_at` is the newest `releaseTimeStamp` as upstream gives it, naive,
  with `meta.published_at_naive` set, since the snapshot states no zone and none is
  invented; its `meta.vintage` is that record's `releaseTimeStamp` text as upstream
  prints it (`"2026-10-22T08:30:42.67"`, two fractional digits), kept beside the
  parsed value as `DataReleaseInfo.release_time_stamp_text`, which no adapter
  serialises; both `None` for an empty answer
  (https://github.com/xippios/sdk-usda-esr/pull/7; sdk-core ADR-0041, decision 2).

## Layout

```
src/xippios/usda/esr/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the configured client (base URL, key, rate limit, classify, quota) and
                   ENV_VARS, the variables the package reads, for a host
  models.py        pydantic models mirroring upstream payloads (UpstreamModel); by the
                   family's precedent also an enumeration written by hand, for a value set
                   upstream documents and no packaged list renders
  api/             endpoint wrappers, one module per upstream operation (conventions §2),
                   named after it in snake case without the ESRData_ prefix: get_country_data
  tasks.py         task functions; __all__ is what the adapters register, MCP_CAPS any
                   per-tool result caps
  mcp.py           xippios-usda-esr-mcp entry point: build() the tool set, server
  http.py          FastAPI router
  params.py        packaged lists (PACKAGED_LISTS, read with PackagedList.load) and the code
                   and year checks
  enums.py         IntEnum UnitId from the packaged unitsOfMeasure; never edited by hand
  reference/       packaged code lists (JSON) plus README with provenance
scripts/
  refresh_upstream.py    regenerates the docs/upstream/ snapshot, stdlib only, no key
  refresh_reference.py   fetches the packaged lists through api/ (four keyed calls, each
                         sent once and counted, with the quota left), --only some of them,
                         and regenerates enums.py; --render-only renders it without a call
  adr_index.py           writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                         --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <wrapper>/<case>.json, never hand-written
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_tasks.py    per-task replay tests, MCP and HTTP
  test_lists.py    the list tasks answer the recorded lists from the package, without a call
  test_slices.py   the slices replay the recorded exports answers: selection and order only
  test_api.py      replay tests for the endpoint wrappers
  test_client.py   wiring, classify on recorded error bodies, core's quota policy on a 429
  test_params.py   packaged lists, the enum and the code and year checks
  test_refresh_reference.py  the reference script offline: one attempt per request, the
                   count, --only, every fetch before the first write, the render
  test_refresh_upstream.py   the capture script's FETCHED.md offline: the row of OBSERVED.md
  test_observed.py docs/upstream/OBSERVED.md as committed: each note's probe, its files
  test_live.py     @pytest.mark.live smoke tests, one per task (13 keyed calls in all: the
                   weekly series spans two market years, and the list tasks' test compares
                   each packaged list with the live one), and the template's keyless
                   reachability check
docs/
  upstream/        documentation snapshot, FETCHED.md and OBSERVED.md, the notes by hand
  adr/             this package's design decisions, one NNNN-<slug>.md record each, laid
                   out in its README.md
  adr.md           the index of the decisions, written by scripts/adr_index.py, never by hand
  adr.json         the same index, for machines
  reports/         dated reports, the evidence a decision cites, laid out in its README.md
changelog/         the next release's changelog entries, one fragment per change, laid out
                   in its README.md
CHANGELOG.md       the releases, each section assembled from the fragments
.github/workflows/ ci.yml (the required ci check, with the changelog and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), organization.yml (the organization's checks from xippios/.github:
                   conventions, a review of a pull request against the documents the README
                   lists, and adr-index, which runs scripts/adr_index.py --check),
                   siblings.yml (the sibling proof of sdk-core ADR-0006: this wheel beside the
                   siblings under xippios.usda, a visible check the ruleset does not require)
.github/scripts/   check-siblings.sh, which siblings.yml runs; the template's, as is the workflow
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

The import path is `xippios.usda.esr` (sdk-core ADR-0006); `src/xippios/` is a
namespace package, and so is `src/xippios/usda/`, the provider level.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this Layout says so (conventions §2).

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1, DATA_GOV_API_KEY

uv run xippios-usda-esr-mcp   # stdio; add --http for streamable HTTP
```

`uv run pytest` is offline: core's plugin refuses the network and skips the rate limiter's
waits in every test not marked `live` (conventions §10, sdk-core ADR-0035). A test that
asserts a limiter wait or a quota pause is marked `rate_limited`, one that must reach the
network `network`.
It sends the key's placeholder, with `DATA_GOV_API_KEY` set to it because
`pyproject.toml` names that variable under `xippios_placeholder_key_envs`; the package
keeps no placeholder fixture of its own.

`.github/workflows/live.yml` runs the live tests nightly at 05:40 UTC, a time derived from
the slug so that sources sharing a key never start together, and on demand; a pull request never runs them.
Only its `uv run pytest -m live --tb=short --assert=plain` step sees the key, from the org secret `DATA_GOV_API_KEY`.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Code rules

- Three layers (sdk-core ADR-0001, conventions §2): endpoint wrappers in `api/`, task
  functions in `tasks.py`, adapters in `mcp.py` and `http.py`. The adapters register
  `tasks.__all__` and call only tasks, the tasks call only wrappers and reference data, and
  a wrapper returns models.
- Upstream's documented error shapes go into `classify` in `_client.py`, once, and an error
  class of the package's own into `errors.py`; a wrapper never inspects a status code
  (conventions §5, §6).
- One limiter paces each host the package sends to (conventions §2, §6). A second base URL
  on the host of the API base URL goes through the one `client` of `_client.py` by its
  absolute URL, and `classify`'s path checks name both bases. An origin or mirror that the
  publisher runs itself, where its canonical host refuses automated requests, takes that
  host's pace through the same client, and `docs/upstream/` names both hosts; a mirror that
  anyone else runs is never sent to. A host that a dependency sends to is reached through
  the dependency's tasks alone. Any other host gets a client of its own in `_client.py`,
  its base URL and its `RateLimit` beside the first's, and a row of its own in the table
  under What this package wraps, with its pace and where the pace comes from.
- A change brings its tests, written before the code, and passes the offline checks above;
  its changelog entry is a fragment under `changelog/`, one file holding its bullet, as
  `changelog/README.md` lays it out (conventions §12). Commit subjects follow Conventional
  Commits (conventions §13): the rule binds a pull request's own commits, not the commit
  that lands the pull request on `main`, whose subject GitHub writes.
- `ruff` leaves `docs/` and `.claude/` alone (`pyproject.toml`), so the upstream snapshot
  keeps its bytes: never reformat it.
- A convention that seems wrong is followed anyway and said in the pull request; changing
  it is a change of sdk-core's `docs/conventions.md` with an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping it for key patterns
  (conventions §10).
- Never read or print `.envrc`, `.env`, the credential variable of this package,
  `DATA_GOV_API_KEY`, or any variable ending in `_API_KEY`, `_TOKEN` or
  `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never put logic in `mcp.py` or `http.py`, and never add a route or a tool by hand: the
  adapters register `tasks.__all__` (sdk-core ADR-0001).
- Never rename or re-map an upstream concept to another source's (sdk-core ADR-0028).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (sdk-core ADR-0017).
- Never edit `docs/upstream/` by hand but `docs/upstream/OBSERVED.md`, the notes on what
  upstream does but never documents: `/refresh-upstream` fetches the rest, and the pull
  request shows its diff (conventions §3).
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15): the
update renders the template's files again and never overwrites the files this package
fills, `__init__.py`, `_client.py`, `errors.py`, `models.py`, `api/`, `parse/`, `tasks.py`,
`tasks_write.py`, `params.py`, `enums.py`, `reference/`, `scripts/refresh_reference.py`,
`scripts/refresh_upstream.py`, `tests/test_tasks.py`, `tests/test_live.py`,
`tests/fixtures/`, `docs/upstream/`, `docs/adr.md`, `docs/adr.json`, `README.md`,
`CHANGELOG.md` and `CLAUDE.md`. sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at upstream
semantics or the shape of the public API.

## USDA FAS Export Sales Reporting specifics

- The quota is the gateway's, not this package's: `_client.py` puts `Gateway.policy`,
  core's one `QuotaPolicy` per process for the shared key, on `config` with
  `gateway.install(...)`, and `classify` asks `gateway.classify` first, which maps a spent
  quota's 429 to `RateLimitError` with `retry_after` (sdk-core ADR-0032, sdk-core ADR-0033,
  sdk-core ADR-0037). An endpoint added here installs no policy of its own; only ESR's own
  error shapes go into `classify`, after the gateway's.
- The live run, `uv run pytest -m live --tb=short --assert=plain`, spends 13 keyed calls
  of the shared quota: one per test in `tests/test_live.py`, two for the weekly series' two
  market years, and none for the keyless reachability check.

# sdk-usda-esr — instructions for Claude Code

`xippios-usda-esr` wraps USDA FAS Export Sales Reporting as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file is the contract for every session
that works here; the family rules it points to apply as well.

@.claude/family.md

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA FAS Export Sales Reporting, https://www.fas.usda.gov/programs/export-sales-reporting-program |
| API base URL | `https://api.fas.usda.gov`, api.data.gov's gateway (the portal document's `host`): `BASE_URL` is the host root, and every path keeps the snapshot's `/api/esr/` prefix (`/api/esr/commodities`, `/api/esr/exports/commodityCode/{commodityCode}/...`) |
| Documentation | https://apps.fas.usda.gov/opendatawebV2/, snapshotted in `docs/upstream/` |
| Credentials | `DATA_GOV_API_KEY` from the environment, sent as the `X-Api-Key` header by `xippios.core.data_gov`'s `Gateway` (`_client.auth` is `gateway.auth`); the key is api.data.gov's, shared by every package that reads `DATA_GOV_API_KEY`. ADR-0009: one key variable per issuer when one key serves several sources, so every source reached through api.data.gov (`usda-psd`, `usda-esr`, `usda-gats`) reads `DATA_GOV_API_KEY`, and one key is one gateway quota |
| Rate limit | ADR-0010, decisions 1–5. Pace: 60 requests per minute, burst 1 (`RateLimit(per_minute=60, burst=1)` in `_client.py`, enforced client-side): a self-imposed pace, upstream documents none (the snapshot names no limit). Quota: api.data.gov's 1,000 requests per rolling hour per key, reported in `x-ratelimit-limit` / `x-ratelimit-remaining` on every keyed answer (the hourly quota, not a pace) and shared with `usda-psd`, `usda-gats` and every process using the same `DATA_GOV_API_KEY`; it may be spent, it is not pre-rationed. The quota is the gateway's: `Gateway.policy` of `xippios.core.data_gov`, one `QuotaPolicy` per process for the key, which `_client.py` installs with `gateway.install` (ADR-0009, ADR-0015), keeps the snapshot from every answer from the wire, never a cache hit's, and gates: once the quota is spent the next request waits it out inside the call, logged, when that is within the policy's `pause_cap` (30 s by default), and otherwise raises `RateLimitError` with `retry_after` without sending, a refusal that speaks for `api.data.gov` (its `source`). The wait counts from the last answer: a 429's `Retry-After`, else the policy's `window` of one hour (the gateway sends no reset header). `gateway.classify`, which `classify` asks first, maps the 429 (`OVER_RATE_LIMIT`, not recorded for ESR) to `RateLimitError` with `retry_after` the wait the policy keeps the quota spent for, from `Retry-After`, else 3600 s, and core shapes its retries from that: a wait beyond `RetryPolicy.backoff_max` is raised after one request. In offline tests core's pytest plugin bypasses the limiter and the quota policy and forgets the snapshot around each test; a test that asserts a wait or a refusal is marked `rate_limited` |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.

`_client.py` builds on `xippios.core.data_gov.Gateway` (family review C14, ADR-0023), which
holds what every source behind api.data.gov shares: the `X-Api-Key` auth, the one
`QuotaPolicy` per process on `x-ratelimit-*`, and the `API_KEY_*`, `OVER_RATE_LIMIT` and
`NOT_FOUND` mappings with host-free messages. `classify` asks `gateway.classify` first and
keeps ESR's own answers after it, the empty 404 and the 400 below.

## Upstream behaviour established by fixtures

The snapshot types every response as `object` and defines no schema, so these facts come
from the answers recorded on 2026-10-25, and three on 2026-10-28, under `tests/fixtures/`;
`_client.classify` maps them once.

- Codes are integers on the wire and in the snapshot (`int32` path parameters), and the
  package takes them as `int` (Johannes, 2026-10-25): `get_exports(104, 2024, 1220)`.
- Record shapes of the four lists and the release list are in `models.py`, each naming
  its fixture: 44 commodities (101 to 1702, each with its `unitId`), 211 countries (1 to
  9990, `countryName` and `countryDescription` padded with spaces upstream and kept so),
  12 regions (`regionId`, `regionName`; 99 is UNKNOWN), 5 units (`unitId`, `unitNames`,
  plural upstream).
- Exports records (`ESRData_GetCountryData`, `ESRData_GetAllCountriesData`;
  `models.CommodityData`): one per destination and week, eight quantities as JSON
  integers (`Decimal` here; net sales can be negative), `unitId`, and `weekEndingDate` as
  a midnight without zone (`date` here). Wheat white to Canada 2024: 54 weeks
  (`wheat_white_canada_2024`, 18,010 bytes); 2023, recorded 2026-10-28
  (`wheat_white_canada_2023`, 17,669 bytes): 53 weeks from 2022-06-02 to 2023-06-01. The
  week ending 2023-06-01 is in both, with other values: a week that straddles two market
  years comes in each, and the records carry no market year, so `get_weekly_series` keeps
  both, the older year's row first.
- `allCountries` has no paging: cottonseed 2024 is 498 records for 11 destinations,
  139,119 bytes (`cottonseed_2024`); wheat HRW 2024, measured and not kept, 1,136 records
  for 28 destinations, 319,532 bytes. Over MCP `get_exports` keeps the family's cap, 200
  rows or 64 KB, with a note of its own that names `country_code` (`tasks.MCP_CAPS`;
  conventions §8, ADR-0016; Johannes, 2026-10-25), and the cap's note tells agents to pass
  it: one destination is up to 54 rows. `get_weekly_series` makes one request per market
  year, at most 10 per call (`tasks.SERIES_MAX_YEARS`) in Python, over HTTP and over MCP
  alike, and over MCP keeps the same cap, about three market years, with a note of its
  own that names `start_year` and `end_year` (Johannes, 2026-10-28).
- Destination `9990` (UNKNOWN) arrives in `allCountries` as a row like any country:
  wheat white 2027, recorded 2026-10-28 (`wheat_white_2027`, 119,811 bytes), is 385
  records for 22 destinations over 20 weeks, a `9990` row in each of them; wheat white
  2024, measured the same day and not kept, 1,012 records for 22 destinations, 312,360
  bytes as a fixture, over the 256 KiB cap, `9990` in all 54 weeks. The slices keep and
  rank it like any other code.
- Unknown commodity (999) and unknown country (9999): HTTP 200 with `[]`; so are a
  future market year (2099) and valid codes without exports (rye `allCountries` 2024).
  Empty means empty, not an error; `params` refuses unknown codes (`UnknownCode`, naming
  the nearest codes) and market years after the current UTC year plus two before the call.
  Market year 2028 of wheat white to Canada answers HTTP 200 with `[]` as well (probed
  2026-10-28, one keyed call, not kept; wheat's current market year is 2027), so a market
  year ESR has not released cannot be told from one without exports: `get_weekly_series`
  reads the release list for a range that ends in the current UTC year or later and
  refuses one past the commodity's current market year with `NotFoundError` naming the
  latest released one (Johannes, 2026-10-28; conventions §4; ADR-0022, amendment points
  6 and 7). The current year counts too: a market year named by it may have begun
  without a week released, as a calendar-year commodity's does in January (market years
  start in June, August, September, October or January, per the recorded release list).
- Market year 1900: HTTP 404 with an empty `text/plain` body on both exports forms (the
  one-country `get_country_data/year_1900`; `get_all_countries_data/year_1900`, 1,393
  bytes, recorded 2026-10-28), mapped to `errors.NoDataForYear`, a `NotFoundError` (only
  that answer on an exports path). `get_weekly_series` skips such a year inside its range,
  as sdk-usda-psd's `get_time_series` does, and a released year answering `[]` adds no
  rows (Johannes, 2026-10-28).
  Market years 1998 and 1999 answered `[]` for wheat white to Canada (probed, not kept),
  so where ESR's data begins is not established and no lower bound beyond four digits is
  set.
- A non-integer path value (`commodityCode/abc`): HTTP 400 `{"message": "The request is
  invalid."}`, mapped to `InvalidRequestError`; never sent, since parameters are `int`.
- Invalid key: HTTP 403 `{"error": {"code": "API_KEY_INVALID", ...}}`, no quota headers,
  mapped to `AuthError` naming the code and `DATA_GOV_API_KEY` (recorded with a bogus key).
- Release dates (`ESRData_GetDataReleaseInfo`; `models.DataReleaseInfo`): one record per
  commodity with the current `marketYear`, named by its end year, its `marketYearStart`
  and `marketYearEnd`, and `releaseTimeStamp` without a zone (all 44 at
  `2026-10-22T08:30:42.67`). Market years differ per commodity: wheat June to May, corn
  and soybeans September to August, cotton August to July, beef and pork the calendar year.
- `meta.vintage` of `get_exports` is the latest `weekEndingDate` among the records as an
  ISO date (`"2024-06-06"` for wheat white to Canada 2024), `None` for an empty answer,
  and its `meta.published_at` stays `None`: it makes no second call (Johannes,
  2026-10-25). `get_release_dates`' `meta.published_at` is the newest `releaseTimeStamp`
  as upstream gives it, naive, with `meta.published_at_naive` set, since the snapshot
  states no zone and none is invented; its `meta.vintage` is that record's
  `releaseTimeStamp` text as upstream prints it (`"2026-10-22T08:30:42.67"`, two
  fractional digits), kept beside the parsed value as
  `DataReleaseInfo.release_time_stamp_text`, which no adapter serialises; both `None`
  for an empty answer (Johannes, 2026-10-28, superseding the ruling of 2026-10-26;
  ADR-0022, rule 2).

## Layout

```
src/xippios/usda/esr/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the configured client (base URL, key, rate limit, classify, quota)
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation, named after it in
                   snake case without the ESRData_ prefix (conventions §2): get_country_data
  tasks.py         task functions; __all__ is what the adapters register, MCP_CAPS any
                   per-tool result caps
  mcp.py           xippios-usda-esr-mcp entry point
  http.py          FastAPI router
  errors.py        NoDataForYear, ESR's empty 404 for a market year (UnknownCode is core's)
  params.py        packaged lists (PACKAGED_LISTS, read with PackagedList.load) and the code
                   and year checks
  enums.py         IntEnum UnitId from the packaged unitsOfMeasure; never edited by hand
  reference/       packaged code lists (JSON) plus README with provenance
scripts/
  refresh_upstream.py    regenerates the docs/upstream/ snapshot, stdlib only, no key
  refresh_reference.py   fetches the packaged lists through api/ (four keyed calls) and
                         regenerates enums.py; --render-only renders it without a call
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
  test_live.py     @pytest.mark.live smoke tests, one per task (13 keyed calls in all: the
                   weekly series spans two market years, and the list tasks' test compares
                   each packaged list with the live one), and the template's keyless
                   reachability check
docs/upstream/     documentation snapshot and FETCHED.md
.github/workflows/ ci.yml (the required ci check), publish.yml (tag to PyPI), live.yml (nightly live tests),
                   gates.yml (the merge gates as jobs, off until GATES_CALLER is 1),
                   siblings.yml (the sibling proof of ADR-0006: this wheel beside the
                   siblings under xippios.usda, a visible check the ruleset does not require)
.github/scripts/   check-siblings.sh, which siblings.yml runs; the template's, as is the workflow
.claude/family.md  the family rules, the template's, imported above
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep,
                   adopt-release
```

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package, and so is every level
between it and the package (`src/xippios/usda/`). The import path is
`xippios.usda.esr` (ADR-0006).

## Commands

```bash
uv run pytest -m live --tb=short   # needs XIPPIOS_LIVE_TESTS=1 and DATA_GOV_API_KEY

uv run xippios-usda-esr-mcp   # stdio; add --http for streamable HTTP
```

The offline run sends core's placeholder key, with `DATA_GOV_API_KEY` set to it because
`pyproject.toml` names that variable under `xippios_placeholder_key_envs`; the package
keeps no placeholder fixture of its own.

`.github/workflows/live.yml` runs `uv run pytest -m live --tb=short` with
`XIPPIOS_LIVE_TESTS=1` nightly at 05:40 UTC, a time derived from the slug so that sources
sharing a key never start together. Only its `uv run pytest -m live --tb=short` step sees
the key, from the org secret `DATA_GOV_API_KEY`.

## USDA FAS Export Sales Reporting specifics

- The quota is the gateway's, not this package's: `_client.py` puts `Gateway.policy`,
  core's one `QuotaPolicy` per process for the shared key, on `config` with
  `gateway.install(...)`, and `classify` asks `gateway.classify` first, which maps a spent
  quota's 429 to `RateLimitError` with `retry_after` (ADR-0009, ADR-0010, ADR-0015). An
  endpoint added here installs no policy of its own; only ESR's own error shapes go into
  `classify`, after the gateway's.
- The live run, `uv run pytest -m live --tb=short`, spends 13 keyed calls of the shared
  quota: one per test in `tests/test_live.py`, two for the weekly series' two market
  years, and none for the keyless reachability check.

# xippios-usda-esr

Typed Python client, MCP server and FastAPI routes for
[USDA FAS Export Sales Reporting](https://www.fas.usda.gov/programs/export-sales-reporting-program), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries its metadata (source, endpoint,
retrieved_at, request).

## Install

```bash
uv add xippios-usda-esr            # client only
uv add "xippios-usda-esr[mcp]"     # + MCP server
uv add "xippios-usda-esr[http]"    # + FastAPI router
```

It depends on `xippios-usda-fas`, installed with it: the shared package of the USDA FAS
sources, whose api.data.gov gateway sends the key and keeps its quota, and whose kit of the
FAS portal the documentation snapshot is taken with.

Set `DATA_GOV_API_KEY` in the environment. Nothing is read from files.

## 30-second example

```python
from xippios.usda.esr import get_exports, get_release_dates

result = get_exports(104, 2024, country_code=1220)  # wheat white, market year 2024, to Canada
week = result.data[-1]
week.week_ending_date, week.accumulated_exports, week.unit_id  # 2024-06-06, Decimal('16217'), 1
result.meta.vintage, result.meta.published_at  # None, None: the exports state no release
result.meta.retrieved_at, result.meta.request

releases = get_release_dates()  # one record per commodity
wheat = next(r for r in releases.data if r.commodity_code == 104)
wheat.market_year, wheat.market_year_start, wheat.release_time_stamp  # 2027, 2026-06-01, ...
releases.meta.vintage  # "2026-10-22T08:30:42.67": store it for the next call
changed = get_release_dates(since=releases.meta.vintage)  # released strictly later only
changed.data, changed.meta.vintage  # [] when nothing was released since; the newest release
(year,) = get_release_dates(commodity_code=104).data  # wheat white's current market year
year.market_year, year.market_year_start, year.market_year_end  # 2027, 2026-06-01, 2027-05-31
```

Codes are ESR's own integers (commodity `104` wheat white, `401` corn, `801` soybeans;
country `1220` Canada, `2010` Mexico, `5880` Japan), checked against the lists packaged
in `reference/` before any call: ESR answers an unknown code with an empty list, so the
package refuses it and names the closest codes. A market year is ESR's, named by the year
it ends in and different per commodity (wheat 2024 is June 2023 to May 2024; corn and
soybeans run September to August, cotton August to July). Leave out the country for every
destination at once, one row per destination and week; the MCP server returns at most
200 rows per call, so pass a country there. Quantities are `Decimal` in Python and JSON
numbers over MCP and HTTP, in the unit `unit_id` names (`enums.UnitId`). The arguments that
identify a record come first, in the order of upstream's path, and every filter is passed by
name: `country_code`, `start_year`, `end_year`, `since`, `region_id` and `search`.

ESR answers a market year it has not released with an empty list, as it answers a year
without exports, so `get_exports` raises `NotFoundError` for a market year past the
commodity's current one, naming it (`get_release_dates` names it too; wheat: 2027 in October
2026). For a market year from the current calendar year on it reads the release list first,
one request more: one call sends at most 2 requests. An empty list means no exports.

`get_weekly_series` makes the request `get_exports` makes for one country once per market
year from `start_year` to `end_year`, at most 10 market years per call, and only orders the
records:

```python
from xippios.usda.esr import get_weekly_series

series = get_weekly_series(104, 1220, start_year=2023, end_year=2024)  # two requests
len(series.data)  # 107: 53 + 54 weeks of wheat white to Canada
series.meta.notes  # ["Market years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows."]
```

A week that straddles two market years comes once for each, the older one's row first:
the week ending 2023-06-01 closes wheat's 2023 and opens its 2024, and the note's counts say
which rows are whose. A market year ESR holds no data for is skipped and named in the note,
so `get_weekly_series(104, 1220, start_year=1900, end_year=1900)` is an empty list. A range
past the commodity's current market year raises `NotFoundError` naming the latest released
one, as `get_exports` does; a range ending in the current calendar year or later reads the
release list first, one request more, so one call sends at most 11 requests.

The `list_*` tasks look codes up in the packaged lists, without a call:

```python
from xippios.usda.esr import list_commodities, list_countries

result = list_countries(region_id=11)  # ESR's region WESTERN HEMISPHERE (list_regions)
[c.country_code for c in result.data][:3]  # [1010, 1220, 1610], 40 in upstream order
result.meta.endpoint, result.meta.retrieved_at  # "ESRData_GetCountries", 2026-10-28T19:19:52Z
list_countries(search="united").data  # 4120, 5200, 7830: code, name, description or GENC code
list_countries(search="deu").data  # 4280 GERMANY, by its GENC code "DEU"
list_commodities(search="wheat").data  # 101 to 107 and 201 Wheat Products
```

`meta.retrieved_at` of a list is when the package fetched it, and its `meta.vintage` is
`None`, since upstream gives these lists no version. Names are upstream's, padding
included: `country_name` is `"CANADA  "`. The list tasks spend no request of the
api.data.gov quota.

## MCP

```json
{
  "mcpServers": {
    "usda-esr": {
      "command": "uvx",
      "args": ["--from", "xippios-usda-esr[mcp]", "xippios-usda-esr-mcp"],
      "env": { "DATA_GOV_API_KEY": "..." }
    }
  }
}
```

Tools are read-only and named `usda_esr_<verb>_<noun>`. Results are capped, at
200 rows or 64 KB unless a tool has a cap of its own, with a note on how to see the rest;
`usda_esr_list_countries` has a cap of its own, 250 rows, so all 211 countries arrive.
`usda_esr_get_weekly_series` keeps the default, about three market years of one
destination, and its note says to narrow `start_year` and `end_year`.
`--http` serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `ESRData_GetCountryData` (`exports/commodityCode/{commodityCode}/countryCode/{countryCode}/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year, *, country_code)` | `usda_esr_get_exports` | alpha; a market year past the commodity's current one is refused |
| `ESRData_GetAllCountriesData` (`exports/commodityCode/{commodityCode}/allCountries/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year)` | `usda_esr_get_exports` | alpha |
| `ESRData_GetCountryData` | `get_weekly_series(commodity_code, country_code, *, start_year, end_year)` | `usda_esr_get_weekly_series` | alpha; a range of market years, one request per market year, at most 10; a range past the commodity's current market year is refused |
| `ESRData_GetDataReleaseInfo` (`datareleasedates`) | `get_release_dates(*, commodity_code=None, since=None)` | `usda_esr_get_release_dates` | alpha; `since` keeps the commodities released after an earlier call's `meta.vintage`, `commodity_code` one commodity's record |
| `ESRData_GetCommodities` (`commodities`) | `list_commodities(*, search=None)` | `usda_esr_list_commodities` | packaged; `list_*` task |
| `ESRData_GetCountries` (`countries`) | `list_countries(*, region_id=None, search=None)` | `usda_esr_list_countries` | packaged; `list_*` task |
| `ESRData_GetRegions` (`regions`) | `list_regions()` | `usda_esr_list_regions` | packaged; `list_*` task |
| `ESRData_GetUnitsOfMeasure` (`unitsOfMeasure`) | `list_units_of_measure()` | `usda_esr_list_units_of_measure` | packaged, `enums.UnitId`; `list_*` task |

0.3.0 covers the same tasks as 0.2.0, which added `get_market_year`, `since` on
`get_release_dates` and the range of `get_weekly_series`, and requires xippios-core 0.4.x
(`~=0.4.0`); 0.2.0 does not work with core 0.4.0. Alpha: the public surface may change in a
minor version before 1.0 (conventions §12); `CHANGELOG.md` lists every change.

Every request counts against api.data.gov's quota of 1,000 requests per hour per key,
shared by every package using the same `DATA_GOV_API_KEY`; the `list_*` tasks spend none.
The client keeps its own pace of one request per second; once the quota is spent it waits
for the quota to come back when that takes at most 30 s, and otherwise raises
`RateLimitError` with `retry_after` instead of sending.

## Upstream terms and attribution

Data comes from USDA FAS Export Sales Reporting (https://www.fas.usda.gov/programs/export-sales-reporting-program) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Workflows

`ci.yml` runs ruff, its format check, mypy, pytest and pre-commit on Python 3.12, 3.13 and
3.14, requires a changelog entry of every pull request but Dependabot's and refuses a
fixture file over 256 KiB that a pull request adds or changes. It runs on every pull request and,
called by `publish.yml`, once for a release, and its job `ci` is the check the
organization's ruleset requires. It is handed no secret, and no variable switches it off.

`publish.yml` is the release train (conventions §12): on a push to `main` whose
`pyproject.toml` names a version that has no tag yet and has its section in `CHANGELOG.md`,
it runs `ci.yml`, refuses a core pinned to git, tags the merge commit, builds the package
and, once a reviewer of the environment `pypi` approves the run, publishes it to PyPI by
trusted publishing. Every push to `main` and a dispatch start it, and a push that brings no
release ends quietly. It is handed no secret: the step that tells a release is handed the
job's token as `GH_TOKEN`, the tag goes with the job's token and PyPI trusts the workflow
itself. Its job `tag` holds the one checkout of the repository that keeps its credentials,
since it pushes the tag with the job's token; every other checkout sets
`persist-credentials: false` (conventions §13). No variable switches it off.

`live.yml` runs every `live` test against the upstream with `--tb=short --assert=plain`, so
its public log holds neither a failing test's arguments nor the values an assertion compared.
It runs every night at 05:40 UTC and on demand, never on a pull request.
Its pytest step alone is handed `XIPPIOS_LIVE_TESTS` and, each from the secret of the same
name, `DATA_GOV_API_KEY`, so the checkout, setup-uv and `uv sync` see none.
A variable `WORKFLOW_LIVE` of `off`, the repository's over the organization's, switches it off.

`conventions.yml` calls the organization's review of a pull request against the documents
listed under Documents below, the check `conventions / conventions`, when a pull request
opens, is pushed to, reopens or is edited, and on a push to `main` or a dispatch the review
of the range of commits, `range / range`. It hands the review the organization's
secret of the model's key, by name. A variable `WORKFLOW_CONVENTIONS` of `off`, the
repository's over the organization's, switches both off.

`adr-index.yml` calls the organization's check of the ADR index, `adr-index / adr-index`,
which runs `scripts/adr_index.py --check`, when a pull request opens, is pushed to or
reopens. It hands over nothing, and the called workflow reads its switch itself: a variable
`WORKFLOW_ADR_INDEX` of `off`, the repository's over the organization's, skips the check.

`siblings.yml` runs `.github/scripts/check-siblings.sh`, which installs the wheel beside
every sibling on PyPI under the same provider namespace that shares its core minor and
beside the source packages it depends on, and proves that the namespace levels stay portions
(sdk-core ADR-0006, sdk-core ADR-0021). It runs on every pull request and push to `main`, a
check the ruleset does not require, in a workflow of its own, since `ci.yml` is core's file,
which `publish.yml` calls for a release. It hands the script the job's read-only token as
`GITHUB_TOKEN`, for the listing of the organization's repositories, since GitHub limits the
calls of a runner without one. A variable `WORKFLOW_SIBLINGS` of `off`, the repository's
over the organization's, switches it off.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions every xippios source package follows: its layout, names, results, tests and releases.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-usda-esr: [docs/adr.md](https://github.com/xippios/sdk-usda-esr/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.
- sdk-usda-esr: [docs/upstream/FETCHED.md](https://github.com/xippios/sdk-usda-esr/blob/main/docs/upstream/FETCHED.md) — the snapshot of the upstream documentation, the reference for names, parameters and semantics.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-usda-esr/blob/main/LICENSE).

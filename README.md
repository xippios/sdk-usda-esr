# xippios-usda-esr

Typed Python client, MCP server and FastAPI routes for
[USDA FAS Export Sales Reporting](https://www.fas.usda.gov/programs/export-sales-reporting-program), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-usda-esr            # client only
uv add "xippios-usda-esr[mcp]"     # + MCP server
uv add "xippios-usda-esr[http]"    # + FastAPI router
```

Set `DATA_GOV_API_KEY` in the environment. Nothing is read from files.

## 30-second example

```python
from xippios.usda.esr import get_exports, get_market_year, get_release_dates

result = get_exports(104, 2024, 1220)  # wheat white, market year 2024, to Canada
week = result.data[-1]
week.week_ending_date, week.accumulated_exports, week.unit_id  # 2024-06-06, Decimal('16217'), 1
result.meta.vintage  # "2024-06-06": the latest week ending date in the answer
result.meta.published_at  # None: get_release_dates tells when ESR released the data
result.meta.retrieved_at, result.meta.request

releases = get_release_dates()  # one record per commodity
wheat = next(r for r in releases.data if r.commodity_code == 104)
wheat.market_year, wheat.market_year_start, wheat.release_time_stamp  # 2027, 2026-06-01, ...
releases.meta.vintage  # "2026-10-22T08:30:42.67": store it for the next call
changed = get_release_dates(since=releases.meta.vintage)  # released strictly later only
changed.data, changed.meta.vintage  # [] when nothing was released since; the newest release
year = get_market_year(104).data  # wheat white's current market year, one record
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
numbers over MCP and HTTP, in the unit `unit_id` names (`enums.UnitId`).

The slices make the requests `get_exports` makes and only select and order their
records; nothing is excluded, so `9990` UNKNOWN ranks like a country when ESR sends it.
`get_weekly_series` makes one request per market year from `start_year` to `end_year`,
at most 10 market years per call:

```python
from xippios.usda.esr import get_latest_week, get_top_destinations, get_weekly_series
from xippios.usda.esr.models import ExportField

week = get_latest_week(1201, 2024)  # cottonseed: the newest week, one row per destination
len(week.data), week.meta.vintage  # 11, "2024-08-01"
top = get_top_destinations(1201, 2024, ExportField.OUTSTANDING_SALES, n=3)
[r.country_code for r in top.data]  # [5800, 5880, 5230], largest first, ties in upstream order
series = get_weekly_series(104, 1220, 2023, 2024)  # wheat white to Canada, two requests
len(series.data), series.meta.vintage  # 107 (53 + 54 weeks), "2024-06-06"
```

A week that straddles two market years comes once for each, the older one's row first:
the week ending 2023-06-01 closes wheat's 2023 and opens its 2024. A market year ESR holds
no data for is skipped, so `get_weekly_series(104, 1220, 1900, 1900)` is an empty list.

`field` takes upstream's names of the eight quantities (`"outstandingSales"`,
`"accumulatedExports"`, ...; `models.ExportField`), which the MCP and HTTP schemas list.

The `list_*` tasks look codes up in the packaged lists, without a call:

```python
from xippios.usda.esr import list_commodities, list_countries

result = list_countries(region_id=11)  # ESR's region WESTERN HEMISPHERE (list_regions)
[c.country_code for c in result.data][:3]  # [1010, 1220, 1610], 40 in upstream order
result.meta.endpoint, result.meta.retrieved_at  # "ESRData_GetCountries", 2026-10-25 (fetched)
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
| `ESRData_GetCountryData` (`exports/commodityCode/{commodityCode}/countryCode/{countryCode}/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year, country_code)` | `usda_esr_get_exports` | alpha |
| `ESRData_GetAllCountriesData` (`exports/commodityCode/{commodityCode}/allCountries/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year)` | `usda_esr_get_exports` | alpha |
| `ESRData_GetAllCountriesData` | `get_latest_week(commodity_code, market_year)` | `usda_esr_get_latest_week` | alpha; slice |
| `ESRData_GetAllCountriesData` | `get_top_destinations(commodity_code, market_year, field, n=10)` | `usda_esr_get_top_destinations` | alpha; slice |
| `ESRData_GetCountryData` | `get_weekly_series(commodity_code, country_code, start_year, end_year)` | `usda_esr_get_weekly_series` | alpha; slice over a range of market years, one request per market year, at most 10 |
| `ESRData_GetDataReleaseInfo` (`datareleasedates`) | `get_release_dates(since=None)` | `usda_esr_get_release_dates` | alpha; `since` keeps the commodities released after an earlier call's `meta.vintage` |
| `ESRData_GetDataReleaseInfo` | `get_market_year(commodity_code)` | `usda_esr_get_market_year` | alpha; one commodity's record |
| `ESRData_GetCommodities` (`commodities`) | `list_commodities(search)` | `usda_esr_list_commodities` | packaged; `list_*` task |
| `ESRData_GetCountries` (`countries`) | `list_countries(region_id, search)` | `usda_esr_list_countries` | packaged; `list_*` task |
| `ESRData_GetRegions` (`regions`) | `list_regions()` | `usda_esr_list_regions` | packaged; `list_*` task |
| `ESRData_GetUnitsOfMeasure` (`unitsOfMeasure`) | `list_units_of_measure()` | `usda_esr_list_units_of_measure` | packaged, `enums.UnitId`; `list_*` task |

0.1.0, the first release, covered nine of these tasks; `get_market_year`, `since` on
`get_release_dates` and the range of `get_weekly_series`, which replaces its 0.1.0
`market_year`, are unreleased. Alpha: the public surface may change in a minor version
before 1.0 (conventions §12); `CHANGELOG.md` lists every change.

Every request counts against api.data.gov's quota of 1,000 requests per hour per key,
shared by every package using the same `DATA_GOV_API_KEY`; the `list_*` tasks spend none.
The client keeps its own pace of one request per second; once the quota is spent it waits
for the quota to come back when that takes at most 30 s, and otherwise raises
`RateLimitError` with `retry_after` instead of sending.

## Upstream terms and attribution

Data comes from USDA FAS Export Sales Reporting (https://www.fas.usda.gov/programs/export-sales-reporting-program) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

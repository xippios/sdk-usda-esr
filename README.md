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
from xippios.usda.esr import get_exports, get_release_dates

result = get_exports(104, 2024, 1220)  # wheat white, market year 2024, to Canada
week = result.data[-1]
week.week_ending_date, week.accumulated_exports, week.unit_id  # 2024-06-06, Decimal('16217'), 1
result.meta.vintage  # "2024-06-06": the latest week ending date in the answer
result.meta.published_at  # None: get_release_dates tells when ESR released the data
result.meta.retrieved_at, result.meta.request

releases = get_release_dates()  # one record per commodity, no parameters
wheat = next(r for r in releases.data if r.commodity_code == 104)
wheat.market_year, wheat.market_year_start, wheat.release_time_stamp  # 2027, 2026-06-01, ...
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

The `list_*` tasks look codes up in the packaged lists, without a call:

```python
from xippios.usda.esr import list_commodities, list_countries

result = list_countries(region_id=11)  # ESR's region WESTERN HEMISPHERE (list_regions)
[c.country_code for c in result.data][:3]  # [1010, 1220, 1610], 40 in upstream order
result.meta.endpoint, result.meta.vintage  # "ESRData_GetCountries", "2026-10-25" (fetched)
list_countries(search="united").data  # 4120, 5200, 7830: code, name, description or GENC code
list_countries(search="deu").data  # 4280 GERMANY, by its GENC code "DEU"
list_commodities(search="wheat").data  # 101 to 107 and 201 Wheat Products
```

`meta.vintage` of a list is the day the package fetched it (upstream gives these lists no
version), `meta.retrieved_at` when the task answered. Names are upstream's, padding
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
`--http` serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `ESRData_GetCountryData` (`exports/commodityCode/{commodityCode}/countryCode/{countryCode}/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year, country_code)` | `usda_esr_get_exports` | alpha |
| `ESRData_GetAllCountriesData` (`exports/commodityCode/{commodityCode}/allCountries/marketYear/{marketYear}`) | `get_exports(commodity_code, market_year)` | `usda_esr_get_exports` | alpha |
| `ESRData_GetDataReleaseInfo` (`datareleasedates`) | `get_release_dates()` | `usda_esr_get_release_dates` | alpha |
| `ESRData_GetCommodities` (`commodities`) | `list_commodities(search)` | `usda_esr_list_commodities` | packaged; `list_*` task |
| `ESRData_GetCountries` (`countries`) | `list_countries(region_id, search)` | `usda_esr_list_countries` | packaged; `list_*` task |
| `ESRData_GetRegions` (`regions`) | `list_regions()` | `usda_esr_list_regions` | packaged; `list_*` task |
| `ESRData_GetUnitsOfMeasure` (`unitsOfMeasure`) | `list_units_of_measure()` | `usda_esr_list_units_of_measure` | packaged, `enums.UnitId`; `list_*` task |

Alpha: the public surface may change in a minor version before 1.0 (conventions §12);
`CHANGELOG.md` lists every change.

## Upstream terms and attribution

Data comes from USDA FAS Export Sales Reporting (https://www.fas.usda.gov/programs/export-sales-reporting-program) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

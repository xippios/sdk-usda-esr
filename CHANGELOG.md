# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for USDA FAS Export Sales Reporting, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI, the nightly live tests and publishing.
- Upstream documentation snapshot of 2026-10-25 in `docs/upstream/`: the ESR part (seven
  `/api/esr/` operations) of the FAS Open Data Services portal's Swagger 2.0 document and
  of the API's own Swashbuckle document, with `FETCHED.md`; written by
  `scripts/refresh_upstream.py` (standard library only, no key), which also records the
  portal and Swagger UI shells, the ESR program page (403 to headless clients) and the
  ESR query URLs (404) without files.
- `get_exports(commodity_code, market_year, country_code=None)`, MCP tool
  `usda_esr_get_exports`: US weekly export sales of one commodity in one ESR market year,
  to one destination (`ESRData_GetCountryData`) or to every one (`ESRData_GetAllCountriesData`),
  one `CommodityData` record per destination and week with `Decimal` quantities and
  `week_ending_date` as a date. Codes are integers, checked against the packaged lists
  before any call (`errors.UnknownCode`, naming the closest codes, since ESR answers an
  unknown code with an empty list); market years after the current UTC year plus two are
  refused (ESR answers them with an empty list), and ESR's empty 404 for a market year it
  lacks is `errors.NoDataForYear`, a `NotFoundError`. `meta.vintage` is the latest week
  ending date in the answer; `meta.published_at` stays `None`. Over MCP a cut answer's
  note names `country_code` (`tasks.MCP_CAPS`).
- `get_latest_week(commodity_code, market_year)`,
  `get_top_destinations(commodity_code, market_year, field, n=10)` and
  `get_weekly_series(commodity_code, country_code, market_year)`, MCP tools
  `usda_esr_get_latest_week`, `usda_esr_get_top_destinations` and
  `usda_esr_get_weekly_series`: the slices, each one upstream request
  (`ESRData_GetAllCountriesData` for the first two, `ESRData_GetCountryData` for the
  series) whose records are only selected and ordered: the newest week's records, one per
  destination; those sorted by one quantity, largest first, ties in upstream order, the
  first `n`; one destination's weeks, oldest first. Nothing is excluded. `meta.vintage` is
  the latest week among the records considered, `meta.published_at` `None`; an empty
  answer is an empty result. `field` is a `models.ExportField`, a `StrEnum` of the
  record's eight quantities by their upstream names, which the MCP and HTTP schemas list.
- `get_release_dates()`, MCP tool `usda_esr_get_release_dates`: when ESR last released each
  commodity's export data, with its current market year (`ESRData_GetDataReleaseInfo`);
  `meta.vintage` is the latest release time stamp's text (`"2026-10-22T08:30:42.670000"`,
  `isoformat()` of upstream's `2026-10-22T08:30:42.67`), `meta.published_at` `None` since
  the documentation states no time zone for `releaseTimeStamp`.
- `list_commodities(search=None)`, `list_countries(region_id=None, search=None)`,
  `list_regions()` and `list_units_of_measure()`, MCP tools `usda_esr_list_commodities`,
  `usda_esr_list_countries`, `usda_esr_list_regions` and `usda_esr_list_units_of_measure`:
  ESR's four code lists, answered from the packaged files without an upstream call, in
  upstream order with upstream's names and padding. `meta.endpoint` is the operation the
  list came from, `meta.vintage` the day the package fetched it, `meta.retrieved_at` when
  the task answered; `meta.total` stays `None`. `search` is a case-insensitive substring
  match on the code (as digits) and the name, for countries also the description and the
  GENC code; `region_id` selects the countries of one region exactly. Over MCP
  `usda_esr_list_countries` has a cap of its own, 250 rows, so all 211 countries arrive,
  and its note names `region_id` and `search`; `usda_esr_list_commodities`' note names
  `search` (`tasks.MCP_CAPS`).
- Endpoint wrappers for the seven ESR operations under `api/`, named after the snapshot's
  operationIds, and their models, built from the recorded answers.
- The configured client for api.data.gov's gateway: the `X-Api-Key` header from
  `DATA_GOV_API_KEY`, the self-imposed pace of 60 requests per minute, core's
  `QuotaPolicy` on the gateway's hourly quota of 1,000 requests per key shared with
  xippios-usda-psd and xippios-usda-gats, and `classify` for the gateway's `API_KEY_*`,
  `OVER_RATE_LIMIT` and `NOT_FOUND` answers and ESR's own 404 and 400.
- Packaged reference data in `reference/` (44 commodities, 211 countries, 12 regions, 5
  units, fetched 2026-10-25) written by `scripts/refresh_reference.py`, which also renders
  the `IntEnum` `enums.UnitId`.
- `scripts/check-siblings.sh` and its workflow `siblings.yml`, a check of its own that the
  org ruleset does not require: this wheel installs with xippios-usda-psd and
  xippios-usda-nass, both from PyPI, as portions of the `xippios.usda` namespace
  (ADR-0006); `PSD_REQUIREMENT` and `NASS_REQUIREMENT` override either.

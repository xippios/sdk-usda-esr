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
- `get_release_dates()`, MCP tool `usda_esr_get_release_dates`: when ESR last released each
  commodity's export data, with its current market year (`ESRData_GetDataReleaseInfo`);
  `meta.vintage` is the latest release time stamp's text (`"2026-10-22T08:30:42.670000"`,
  `isoformat()` of upstream's `2026-10-22T08:30:42.67`), `meta.published_at` `None` since
  the documentation states no time zone for `releaseTimeStamp`.
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
  org ruleset does not require: this wheel installs with xippios-usda-psd (PyPI) and
  xippios-usda-nass (pinned to its main commit 727c9eb until its 0.1.0 is on PyPI) as
  portions of the `xippios.usda` namespace (ADR-0006).

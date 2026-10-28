# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

Adopted xippios-core 0.3.0, sdk-template v0.3.0 and conventions 1.22 (conventions §15).

### Added

- `get_release_dates(since=None)`: `since` takes the `meta.vintage` text of an earlier
  call (`"2026-10-22T08:30:42.67"`) and keeps the commodities whose `release_time_stamp`
  is strictly later, so a caller stores `meta.vintage` and passes it next time; an empty
  list means nothing was released since. `meta.vintage` and `meta.published_at` stay the
  newest release of ESR's whole answer, filtered or not, and `meta.request` carries
  `since` when given. A text that is not an ISO date and time, or one with a time zone,
  is refused with `InvalidRequestError` before the call. Still one request.
- `get_market_year(commodity_code)`, MCP tool `usda_esr_get_market_year`: one commodity's
  record of `ESRData_GetDataReleaseInfo` as ESR sends it, its current market year with
  the first and last day and its last release (wheat white: 2027, 2026-06-01 to
  2027-05-31). `meta.vintage` is the record's release time stamp as ESR prints it,
  `meta.published_at` its value without a zone, with `meta.published_at_naive`. An
  unknown code is refused with `UnknownCode` before the call; a packaged code the release
  list lacks raises `NotFoundError`. One request.
- Two recordings of `ESRData_GetAllCountriesData`. Market year 1900 for every country
  answers HTTP 404 with an empty body, as the one-country form does, so `get_exports`
  without a country, `get_latest_week` and `get_top_destinations` raise `NoDataForYear`
  for it, as 0.1.0 assumed without a recording. Wheat white 2027 carries a `9990`
  (UNKNOWN) destination in every week, and the slices keep and rank it like any other
  code.
- A recording of `ESRData_GetCountryData` for wheat white to Canada, market year 2023:
  53 weeks from 2022-06-02 to 2023-06-01, the last of them also the first week of market
  year 2024 with other values, so the two-year series replays two recorded years.

### Changed

- **BREAKING:** depends on `xippios-core~=0.3.0`, and its `mcp`, `http` and `testing`
  extras likewise, in place of `~=0.2.0`.
- **BREAKING:** the seven endpoint wrappers take conventions 1.22 §2's names, module and
  function alike: the upstream operation in snake case without the `ESRData_` prefix
  every operation shares, so `ESRData_GetCountryData` is `get_country_data` in
  `api/get_country_data.py`, and likewise `get_all_countries_data`, `get_commodities`,
  `get_countries`, `get_data_release_info`, `get_regions` and `get_units_of_measure`.
  The old names are no longer importable from `xippios.usda.esr.api`. The fixture
  directories follow (`tests/fixtures/get_country_data/`, conventions §10).
  `meta.endpoint` keeps the verbatim operation id (`"ESRData_GetCountryData"`), and the
  tasks and MCP tools are unchanged.
- **BREAKING:** `get_weekly_series(commodity_code, country_code, start_year, end_year)`
  replaces `get_weekly_series(commodity_code, country_code, market_year)`, in Python, as
  the MCP tool `usda_esr_get_weekly_series` and as the HTTP route alike, both years
  required, as sdk-usda-psd's `get_time_series` takes them: `get_weekly_series(104, 1220,
  2024)` is now `get_weekly_series(104, 1220, 2024, 2024)`. It makes one
  `ESRData_GetCountryData` request per market year, oldest first, at the client's pace of
  one a second, and orders the records of every year by `week_ending_date`, otherwise
  unchanged; a week in two market years comes once for each, the older year's row first.
  At most 10 market years per call: a longer range, or an `end_year` before
  `start_year`, is refused with `InvalidRequestError` before any request, and a year
  refused by its shape or as future is named as `start_year` or `end_year`
  (`params.validate_market_year` gains the keyword `name`, `"market_year"` by default,
  so every other refusal reads as before).
  `meta.request` carries `start_year` and `end_year` in place of `market_year`;
  `meta.vintage` is the last week of the whole series. A market year ESR holds no data
  for (its empty 404) is skipped instead of raised, so `get_weekly_series(104, 1220, 1900,
  1900)` answers `[]` where 0.1.0's `get_weekly_series(104, 1220, 1900)` raised
  `NoDataForYear`; `get_exports` still raises it for a single year. A released year that
  answers `[]` had no exports and adds no rows. Any other error stops the series. ESR
  answers a market year it has not released with `[]` too, so a range whose `end_year`
  is the current calendar year or later makes one request more, first, to the release
  list (`ESRData_GetDataReleaseInfo`), and an `end_year` after the commodity's current
  market year raises `NotFoundError` naming the latest released market year and the
  range asked, before any yearly request: wheat's 2024 to 2028 is refused in October
  2026, its current market year being 2027, and in January a calendar-year commodity's
  new year is refused until ESR's release list names it. A range ending before the
  current calendar year makes no such request. Over MCP the default cap of 200 rows or
  64 KB applies, about three market years, with a note that names `start_year` and
  `end_year`.
- `get_release_dates`: `meta.published_at` is now set, the newest `releaseTimeStamp` as
  ESR gives it, naive, with `meta.published_at_naive` true; `meta.vintage` is that time
  stamp's text as upstream prints it (`"2026-10-22T08:30:42.67"`), no longer the
  `isoformat()` of the parsed value (`"2026-10-22T08:30:42.670000"`); both `None` for an
  empty answer. `models.DataReleaseInfo` keeps the text as the read-only
  `release_time_stamp_text`, which no adapter serialises, so its rows are unchanged.
- `models.DataReleaseInfo` equality: a record parsed from upstream's text no longer
  equals one with the same values built by keyword from a `datetime`, nor one
  round-tripped through its own `model_dump()` or `dump_upstream()`, because the release
  text sits in a private attribute, which pydantic compares; compare two records'
  `model_dump()` for their values alone.
- The `list_*` tasks' `meta`, now built by core's `PackagedList`: `retrieved_at` is when
  the packaged list was fetched (2026-10-25, the files' bare date read as 00:00 UTC), no
  longer when the task answered, and `vintage` is `None`, no longer the fetch date.
- `meta.request` leaves out a parameter left `None`: `get_exports` without
  `country_code`, `list_commodities` and `list_countries` without their filters.
- The gateway's answers are mapped by `xippios.core.data_gov`'s `Gateway`: its
  `API_KEY_*` refusals, its 429 and its `NOT_FOUND`, with the same error classes. Its
  quota policy, one per process for `DATA_GOV_API_KEY`, refuses a request into a spent
  quota with `source` `"api.data.gov"`, not `"usda-esr"`, and a message that starts
  "api.data.gov quota of the key in DATA_GOV_API_KEY spent"; a 429's message no longer
  says "Nothing was retried". `_client.policy` gives way to `_client.gateway`.
- An MCP tool argument the schema refuses is answered
  `error: InvalidRequestError: <argument>: <message>` (core 0.3.0).
- `enums.py` is rendered by core's `render_enums`; `UnitId` and its members are
  unchanged.
- `scripts/check-siblings.sh` is replaced by the template's
  `.github/scripts/check-siblings.sh`, which `siblings.yml` runs and which finds the
  siblings under `xippios.usda` itself.

### Removed

- `xippios.usda.esr.errors.UnknownCode`, replaced by `xippios.core.UnknownCode`, an
  `InvalidRequestError` as before: its message reads "999 is not a commodity_code in the
  packaged commodities list (fetched 2026-10-25). Did you mean ...", its `fetched` is
  a datetime and its `closest` a tuple.
- `params.PackagedList` and `params.packaged_values`: core's
  `PackagedList.load(params.PACKAGE, name)` reads a packaged list.

## [0.1.0] - 2026-10-26

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template) v0.2.0: configured
  client for USDA FAS Export Sales Reporting, MCP server and FastAPI router wired to the
  task layer, test harness, CI, the nightly live tests and publishing.
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

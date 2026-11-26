# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [0.4.0] - 2026-11-26

### Added

- `get_weekly_series` names its market years in `meta.notes`, each answered one with its count
  of rows in the order of the rows and each passed over for having no data in ESR: `Market
  years in the order of the rows: 2023 with 53 rows, 2024 with 54 rows.` The counts tell
  apart the two rows of a week that straddles two market years, since a record states none.
  (https://github.com/xippios/sdk-core/issues/478, https://github.com/xippios/sdk-usda-esr/issues/23)
- The answers are kept in core's response cache for 300 s, every path alike, an expired answer
  dropped and the bodies held under a bound of bytes, so a second read of the release list, of
  an exports answer or of a market year of the series within that time sends no request.
  (https://github.com/xippios/sdk-core/issues/479,
  https://github.com/xippios/sdk-usda-esr/issues/65)
- The MCP tool `usda_esr_get_exports` takes `offset`, the rows already shown: a cut answer's
  note ends with `continue with offset=<n>`, and each continuation runs the task again, which
  core's response cache answers, showing the next older weeks, while the last page's note
  names its rows alone. (sdk-core ADR-0047, https://github.com/xippios/sdk-usda-esr/issues/28)
- The answers of `get_exports` and `get_weekly_series` name the commodity and the country asked
  for and the commodities, countries and units of their rows in `meta.names`,
  `{"commodity_code": {"104": "Wheat - White"}, "country_code": {"1220": "CANADA"}, "unit_id":
  {"1": "Metric Tons"}}`, by the packaged lists, `get_release_dates` names its commodities and
  the one asked for, `list_commodities` its units and `list_countries` its regions and the one
  asked for. A row's code that the packaged list lacks is left out of the names and said in
  `meta.notes`, so no answer is withheld for it.
  (sdk-core ADR-0067, https://github.com/xippios/sdk-usda-esr/issues/30,
  https://github.com/xippios/sdk-usda-esr/issues/85)

### Changed

- The README's `## Scope` states what of ESR the package wraps and what it leaves out: all
  seven operations of the snapshot, read as JSON, with every path parameter an argument of a
  task, and XML the one documented choice that a caller cannot make.
  (https://github.com/xippios/sdk-usda-esr/issues/62)
- The descriptions and the cap notes of the MCP tools `usda_esr_get_exports` and
  `usda_esr_get_weekly_series` state the most that one call sends, retries counted: 2
  requests in 8 attempts, and 11 requests in 44 attempts. (https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-usda-esr/issues/62)
- `meta.retrieved_at` of `get_exports`, `get_release_dates` and `get_weekly_series` is the
  client's time of the answer, the time its entry was stored where core's cache answers it and
  the oldest of the market years that `get_weekly_series` puts together, where it read the time
  the answer's metadata was made. (https://github.com/xippios/sdk-core/issues/479)
- The descriptions of `usda_esr_get_exports`, `usda_esr_get_release_dates` and
  `usda_esr_get_weekly_series` are their tasks' docstrings before `Args:`, each under 1,000
  characters, and the text of each argument stands in the tool's input schema: the examples
  of a range's requests stand under `end_year`, and the measures of upstream's answers in
  `docs/upstream/OBSERVED.md`. (https://github.com/xippios/sdk-core/issues/485)
- A cut answer of the MCP tools `usda_esr_get_exports` and `usda_esr_get_weekly_series`
  shows the newest weeks, oldest first, where it showed the oldest, and its note names the
  rows shown, `showing rows 299 to 498 of 498`. The note of `usda_esr_get_weekly_series` says
  that the newest weeks are shown where it said the oldest come first.
  (sdk-core ADR-0047, https://github.com/xippios/sdk-usda-esr/issues/28)
- A code that is not an integer is refused in xippios-core's wording, which names the integer
  codes of the packaged list with its fetch date, says that nothing was sent and, for a text of
  digits, names the integer to pass, followed by the reason ESR's codes are checked, its class
  `InvalidRequestError` kept. `list_countries(region_id=...)` refuses a region the packaged
  regions list lacks with `UnknownCode`, naming the closest ids, where it answered an empty
  list. (sdk-core ADR-0045, https://github.com/xippios/sdk-usda-esr/issues/27)
- Every refusal of a call as given says `Nothing was sent.` after its first sentence: an
  unknown code, a market year that is not four digits or lies in the future, a `since` that
  is not a release time, a range of market years that runs backwards, and the MCP adapter's
  refusal of an argument. The refusals' classes are unchanged.
  (https://github.com/xippios/sdk-core/issues/481)
- The refusal before a request into api.data.gov's spent quota, which the package shares with
  every source that reads `DATA_GOV_API_KEY`, says `quota spent (` with the gateway's name as
  its source and no longer names the key's variable. The gateway now comes from
  `xippios-usda-fas`. (https://github.com/xippios/sdk-core/issues/485,
  https://github.com/xippios/sdk-usda-esr/issues/66)
- `get_weekly_series` refuses a range over its ceiling of 10 market years in xippios-core's
  wording, which names the range and the ceiling and says that nothing was sent, followed by
  the range to ask for as before, its class `InvalidRequestError` kept. A request after the
  first market year that fails raises its error, its class kept, naming the market years
  answered before it and that the series returns nothing. (sdk-core ADR-0054,
  https://github.com/xippios/sdk-usda-esr/issues/29)
- A quantity without fractional digits is a JSON integer in the answers over MCP and HTTP,
  `16217` where it read `16217.0`. It stays a `Decimal` in Python.
  (https://github.com/xippios/sdk-core/issues/478)

### Breaking

- The endpoint wrappers under `api/` return core's `Answer`, the parsed answer as its
  `payload` beside the time it was retrieved as its `retrieved_at`, where they returned the
  parsed answer itself, so a caller of `api.get_commodities()` or another wrapper reads its
  `.payload`. That of `api.get_data_release_info()` is the `ReleaseList`.
  (https://github.com/xippios/sdk-core/issues/479)
- `get_exports` and `get_weekly_series` leave `meta.vintage` empty, where it held the newest
  `week_ending_date` of the rows, since an exports answer states no release of its own. The
  newest week is the last row's `week_ending_date`, and `get_release_dates` gives the
  commodity's last release. (https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-usda-esr/issues/67)
- `get_exports` raises `NotFoundError` for a market year that ESR has not released, naming the
  commodity's current market year, where it answered the empty list that ESR gives a year
  without exports, so the empty list now means no exports alone. For a market year from the
  current calendar year on it reads the release list first, one request more, which core's
  response cache answers within its lifetime. Its refusal, as `get_weekly_series`' of a range
  past that year and either task's of a commodity that the release list lacks, says that the
  release list was read and no exports were requested.
  (sdk-core ADR-0054, https://github.com/xippios/sdk-usda-esr/issues/21,
  https://github.com/xippios/sdk-usda-esr/issues/84)
- The arguments that identify a record stay positional in the order of upstream's path, and
  every filter and every argument of the package's own is keyword-only:
  `get_exports(104, 2024, country_code=1220)`, `get_weekly_series(104, 1220, start_year=2023,
  end_year=2024)`, `get_release_dates(since=...)`, `list_countries(region_id=11)` and
  `list_commodities(search="wheat")`, where 0.3.0 took the same values by position. Over MCP
  and HTTP nothing changes, since a tool and a route take their arguments by name.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-usda-esr/issues/68)
- `DataReleaseInfo.release_time_stamp_text` leaves: `release_time_stamp` is the one reading of
  `releaseTimeStamp`, a naive `datetime` that keeps upstream's fraction of a second, and a
  record equals one built from its values. `meta.vintage` of `get_release_dates` still holds
  the newest release as upstream sent it, `"2026-10-22T08:30:42.67"`, which the wrapper
  `api.get_data_release_info` now answers beside the records, as a `ReleaseList`.
  (https://github.com/xippios/sdk-usda-esr/issues/60, https://github.com/xippios/sdk-usda-esr/issues/69)
- `NoDataForYear`, which `get_exports` raises for a market year that ESR holds no data for, is
  `xippios.usda.fas.NoDataForYear`, since xippios-core 0.5.0 holds no
  `xippios.core.data_gov`, so an import of it by that module fails. It is still a
  `NotFoundError`, which `except NotFoundError` catches as before.
  (https://github.com/xippios/sdk-core/issues/485, https://github.com/xippios/sdk-usda-esr/issues/66)
- The package depends on `xippios-core~=0.5.0`, its extras likewise, and on
  `xippios-usda-fas~=0.1.0`, is updated to sdk-template v0.5.0 and applies conventions 1.30.
  (https://github.com/xippios/sdk-usda-esr/issues/62)
- `get_market_year` leaves, with its MCP tool and its route, and `get_release_dates` takes
  `commodity_code`, which keeps that commodity's record, its current market year, after the
  one request: `get_release_dates(commodity_code=104).data` in place of
  `get_market_year(104).data`, a list of one record, empty where the release list lacks the
  commodity, where `get_market_year` raised `NotFoundError`.
  (https://github.com/xippios/sdk-core/issues/474, https://github.com/xippios/sdk-usda-esr/issues/64)
- `get_top_destinations` and `get_latest_week` leave, with their MCP tools, their routes and
  `models.ExportField`, by the boundary of a source package: a task that ranks or picks the
  newest week for the caller is not the package's. A caller reads the same records from
  `get_exports` and ranks or picks them itself. (https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-usda-esr/issues/63)

## [0.3.0] - 2026-11-21

### Added

- `xippios.usda.esr.mcp.build()` returns the read-only tool set that `xippios-usda-esr-mcp`
  serves, xippios-core's `ToolSet` with the caps of `tasks.MCP_CAPS`, so a host serves the
  same tools beside other sources' in one server. `ENV_VARS`, beside `SOURCE` in
  `xippios.usda.esr.mcp`, names the one variable the package reads, `DATA_GOV_API_KEY`,
  secret and required. (https://github.com/xippios/sdk-core/issues/245,
  https://github.com/xippios/sdk-template/issues/81)

### Changed

- The tests of the client's error mapping serve each answer as sdk-core's conventions §10
  allow: a recorded answer at its own operation's path, or the recorded empty 404 of a market
  year at its own path with its content type replaced, never one operation's answer at
  another operation's path. A caller sees no change.
  (https://github.com/xippios/sdk-usda-esr/issues/53)
- The `NotFoundError` and the `InvalidRequestError` that the client maps from ESR's own
  answers name the request by its method and its path, as xippios-core's
  `request_description` gives it, where they named the path alone. An empty 404 other
  than an exports path's empty market year reads
  `ESR has no data for GET <path> (HTTP 404 with an empty body)`, where it read
  `ESR has no data for <path> (HTTP 404 with an empty body)`, and the 400 for a path value
  that is not an integer starts `ESR refused GET <path> (HTTP 400: <message>)`, where it
  started `ESR refused <path> (HTTP 400: <message>)`. Neither error's class, source or any
  other attribute changes. (https://github.com/xippios/sdk-usda-esr/issues/49)
- What ESR was observed doing beyond its documentation, the answers' shapes, its empty
  answers and its refusals, moves from `CLAUDE.md` and the docstring of
  `params.EARLIEST_MARKET_YEAR` into `docs/upstream/OBSERVED.md`. Each note there ends
  with the date, the operation and the recording or the request it was observed from, and
  `docs/upstream/FETCHED.md` lists the file in a row of its own.
  (https://github.com/xippios/sdk-usda-esr/issues/48)
- `CLAUDE.md`, the docstrings of `tasks.py` and `params.py`, a comment in `models.py` and
  the tests cite each decision on the package's behaviour by the pull request that took it,
  where they gave a first name and a date, and `_client.py` and `CLAUDE.md` cite the shared
  gateway by sdk-core's ADR-0032, decision 5, where they named an internal review. The
  capture script, and with it `docs/upstream/FETCHED.md`, says when and where the portal's
  Swagger document was found without naming who fetched it.
  (https://github.com/xippios/sdk-usda-esr/issues/17)
- The docstrings of `get_exports`, `get_latest_week` and `get_top_destinations`, their MCP
  tools' descriptions, say that an empty list may be a market year ESR has not released
  yet as well as one without exports, since ESR answers both with an empty list and these
  tasks read no release list. `get_market_year` names a commodity's current market year.
  (https://github.com/xippios/sdk-usda-esr/issues/18)
- `xippios-usda-esr-mcp` names itself in its usage line and its errors, an unknown option
  ending `xippios-usda-esr-mcp: error: unrecognized arguments: --<option>`, where they
  named the server, `xippios-usda-esr`. Its help says that `--allow-remote` changes
  nothing, since this read server is not held to loopback, where it spoke of a write
  server. (https://github.com/xippios/sdk-core/issues/167)
- A tool's error answer sets `isError` on its result beside the text
  `error: <ErrorClass>: <message>`, an unknown commodity or country code's `UnknownCode`
  as well as a refused argument, so a client tells a refusal from data without reading the
  text. (https://github.com/xippios/sdk-core/issues/168)
- A route answers an argument that its schema refuses, a `market_year` of `2024/25`, a
  `field` outside the eight quantities or a missing `commodity_code` say, as problem
  details before the task runs: HTTP 422, the title `InvalidRequestError` and the detail
  `<argument>: <message>`, where FastAPI's own 422 listed its error details with the
  input. (https://github.com/xippios/sdk-core/issues/66)
- A refusal of a commodity or country code that the packaged lists lack ends with
  `If upstream added it since, the packaged list is out of date.`, where it named the
  maintainers' `/refresh-reference-data`, which an agent cannot run.
  (https://github.com/xippios/sdk-core/issues/111)
- Adopts sdk-template v0.3.4, from v0.3.1, with conventions 1.27 and no new core minor: the
  floor stays `xippios-core~=0.3.0`. The README lists the package's documents under
  `## Documents`, and `CLAUDE.md` holds the rules that `.claude/family.md` carried, which
  leaves with `/adopt-release`, citing sdk-core's decision records as `sdk-core ADR-NNNN`.
  Changelog entries are fragments under `changelog/`, the package's own decisions go into
  `docs/adr/` with the index that `scripts/adr_index.py` writes, and a pull request runs the
  organization's checks from `organization.yml`, where `gates.yml` was.
  (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/sdk-usda-esr/issues/15)
- Adopted sdk-template v0.3.1 (conventions §15), with no new core minor: the floor stays
  `xippios-core~=0.3.0`. `.github/CODEOWNERS` is rendered from the template's answers and
  names the code owner whom GitHub asks to review a change to `.github/`, `CLAUDE.md`,
  `.claude/`, `pyproject.toml` or `.copier-answers.yml`; `.gitignore` leaves copier's
  `*.rej` and `*.orig` out; `.claude/family.md`, `/adopt-release`, `/release-prep` and the
  PR template no longer say how a pull request reaches `main`.

### Breaking

- A tool refuses an argument that it does not declare before it runs, whatever its value:
  `usda_esr_get_exports` called with `country` for `country_code` answers
  `error: InvalidRequestError: country: Not an argument of this tool` and names the
  arguments it takes, where the argument was dropped and the tool fetched every
  destination. (https://github.com/xippios/sdk-core/issues/84)
- `NoDataForYear`, raised for a market year ESR holds no data for, such as 1900, is
  xippios-core's `xippios.core.data_gov.NoDataForYear`, and `xippios.usda.esr.errors` is
  gone. The class is still a `NotFoundError` with `path`, the tasks' messages still name
  commodity, country and market year, and an `except NotFoundError` catches it as before.
  An endpoint wrapper of `api/` raises it with core's text, `no data for <path> (HTTP 404
  with an empty body): the year it names holds no data upstream`, where it read
  `ESR has no data for <path> (HTTP 404 with an empty body)`, and one that a caller builds
  takes the source as `source=`, `None` by default, where the package's class set
  `usda-esr`. (https://github.com/xippios/sdk-core/issues/106)
- Adopts sdk-template v0.4.0, from v0.3.4, with `core_version=0.4.0`: the package depends
  on `xippios-core~=0.4.0`, its extras likewise, and follows conventions 1.28.
  (https://github.com/xippios/sdk-template/releases/tag/v0.4.0,
  https://github.com/xippios/sdk-usda-esr/issues/43)

## [0.2.0] - 2026-10-28

0.2.0 is built on xippios-core 0.3.0 and sdk-template v0.3.0 and follows conventions
1.22. Its breaking changes: it requires `xippios-core~=0.3.0`; the seven endpoint
wrappers in `xippios.usda.esr.api` are named after their upstream operations without the
`ESRData_` prefix (`get_country_data` for `ESRData_GetCountryData`), and the old names
are gone; `get_weekly_series` takes a range of market years, `start_year` and
`end_year`, in place of one `market_year`, with one request per market year and at most
10 a call; and three names leave the package's API, `errors.UnknownCode` for
`xippios.core.UnknownCode`, and `params.PackagedList` and `params.packaged_values` for
`xippios.core.PackagedList.load`. 0.2.0 also changes values in the result envelope: the
`list_*` tasks' `meta.retrieved_at` is when the list was fetched and their
`meta.vintage` is `None`, `get_release_dates` sets `meta.published_at` and gives
`meta.vintage` as upstream's text, and `meta.request` leaves out a parameter left
`None`. New are `get_release_dates(since)`, which keeps only the commodities ESR
released after an earlier call's `meta.vintage`, so a caller can tell whether anything
changed, and `get_market_year(commodity_code)`, one commodity's current market year and
last release. Three new recordings cover ESR's answer for every destination at once and
a second market year of one destination. The packaged code lists were fetched again on
2026-10-28 with their records unchanged, and now carry the full UTC time of the fetch.

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
  the packaged list was fetched (`2026-10-28T19:19:52Z` for the countries), no longer
  when the task answered, and `vintage` is `None`, no longer the fetch date.
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
- The packaged lists re-fetched on 2026-10-28, records unchanged (44 commodities, 211
  countries, 12 regions, 5 units); `fetched` now a full UTC time, to the second, in each
  `reference/*.json` (ADR-0022, amendment 2026-10-27, point 1), where 0.1.0's files
  carried the bare date 2026-10-25. `enums.UnitId` is re-rendered, only its docstring's
  fetch date moving.

### Removed

- **BREAKING:** `xippios.usda.esr.errors.UnknownCode`, replaced by
  `xippios.core.UnknownCode`, an `InvalidRequestError` as before: its message reads "999
  is not a commodity_code in the packaged commodities list (fetched 2026-10-28). Did you
  mean ...", its `fetched` is a datetime and its `closest` a tuple.
- **BREAKING:** `params.PackagedList` and `params.packaged_values`: core's
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

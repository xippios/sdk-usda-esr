# sdk-usda-esr — instructions for Claude Code

`xippios-usda-esr` wraps USDA FAS Export Sales Reporting as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and what only it knows. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file. The
rules that no change breaks stand in `.claude/rules/never.md`, which Claude Code loads with
this file.

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA FAS Export Sales Reporting, https://www.fas.usda.gov/programs/export-sales-reporting-program |
| API base URL | `https://api.fas.usda.gov`, api.data.gov's gateway (the portal document's `host`): `BASE_URL` is the host root, and every path keeps the snapshot's `/api/esr/` prefix (`/api/esr/commodities`, `/api/esr/exports/commodityCode/{commodityCode}/...`) |
| Documentation | https://apps.fas.usda.gov/opendatawebV2/, snapshotted in `docs/upstream/` |
| Credentials | `DATA_GOV_API_KEY` from the environment, sent as the `X-Api-Key` header by the `Gateway` of `xippios.usda.fas`, the shared package of the FAS sources (`_client.auth` is `gateway.auth`); the key is api.data.gov's, shared by every package that reads `DATA_GOV_API_KEY`. sdk-core ADR-0032: one key variable per issuer when one key serves several sources, so every source reached through api.data.gov (`usda-psd`, `usda-esr`, `usda-gats`) reads `DATA_GOV_API_KEY`, and one key is one gateway quota |
| Rate limit | sdk-core ADR-0033, decisions 1–5. Pace: 60 requests per minute, burst 1 (`RateLimit(per_minute=60, burst=1)` in `_client.py`, enforced client-side): a self-imposed pace, upstream documents none (the snapshot names no limit). Quota: api.data.gov's 1,000 requests per rolling hour per key, reported in `x-ratelimit-limit` / `x-ratelimit-remaining` on every keyed answer (the hourly quota, not a pace) and shared with `usda-psd`, `usda-gats` and every process using the same `DATA_GOV_API_KEY`; it may be spent, it is not pre-rationed. The quota is the gateway's: `Gateway.policy` of `xippios.usda.fas`, one `QuotaPolicy` per process for the key, which `_client.py` installs with `gateway.install` (sdk-core ADR-0032, sdk-core ADR-0037), keeps the snapshot from every answer from the wire, never a cache hit's, and gates: once the quota is spent the next request waits it out inside the call, logged, when that is within 30 s, and otherwise raises `RateLimitError` with `retry_after` without sending, a refusal that says `quota spent` and speaks for `api.data.gov` (its `source`). The wait counts from the last answer: a 429's `Retry-After`, else the policy's `window` of one hour (the gateway sends no reset header). `gateway.classify`, which `classify` asks first, maps the 429 (`OVER_RATE_LIMIT`, not recorded for ESR) to `RateLimitError` with `retry_after` the wait the policy keeps the quota spent for, from `Retry-After`, else 3600 s, and core shapes its retries from that: a wait beyond `RetryPolicy.backoff_max` is raised after one request. In offline tests core's pytest plugin bypasses the limiter and the quota policy and forgets the snapshot around each test; a test that asserts a wait or a refusal is marked `rate_limited` |
| Write tools | no, this package is read-only |
| Depends on | `xippios-usda-fas~=0.1.0`, key `DATA_GOV_API_KEY`: its publisher's shared package, which holds no task and serves no tool (sdk-core ADR-0021, sdk-core ADR-0065, decision 1). The package takes from it the api.data.gov gateway, `Gateway` and `API_KEY_ENV`, for `_client.py`, FAS's `NoDataForYear` for `tasks.py`, `REMAINING_HEADER` for the reference script, all four from its root, and the kit of the FAS portal, `Portal` of `xippios.usda.fas.portal`, for the snapshot script |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

`_client.py` builds on the `Gateway` of `xippios.usda.fas` (sdk-core ADR-0032, decision 5;
sdk-core ADR-0065, decision 1), which holds what every source behind api.data.gov shares: the
`X-Api-Key` auth, the one `QuotaPolicy` per process on `x-ratelimit-*`, the `API_KEY_*`,
`OVER_RATE_LIMIT` and `NOT_FOUND` mappings with host-free messages, and, since
`Gateway(SOURCE, data_path=DATA_PATH)` names the exports paths, FAS's empty 404 there as the
shared package's `NoDataForYear` (https://github.com/xippios/sdk-core/issues/106). The client
keeps upstream's answers in core's `MemoryCache` at its default lifetime, 300 s for every path,
since the package reads public data alone (conventions §6). `classify` asks `gateway.classify`
first and keeps ESR's own answers after it, an empty 404 elsewhere and the 400 below.

## Upstream behaviour the package relies on

The snapshot types every response as `object` and defines no schema, so what ESR does beyond
it, the answers' shapes, its empty answers and its refusals, is noted in
`docs/upstream/OBSERVED.md`, each note with the probe that showed it: its date, its
operation and the recording under `tests/fixtures/` or the request. This section holds what
the package does with it; `_client.classify` maps ESR's own answers once.

- Codes are `int`, as the snapshot types the path parameters and as the wire carries them
  (https://github.com/xippios/sdk-usda-esr/pull/3). The arguments that identify a record are
  positional in the order of upstream's path, and every optional filter and every argument
  of the package's own is keyword-only (https://github.com/xippios/sdk-usda-esr/issues/60,
  part 1): `get_exports(104, 2024, country_code=1220)`.
- Record shapes of the four lists, the exports records and the release list are in
  `models.py`, each naming its fixture: the eight quantities as `Decimal` (net sales can be
  negative), `weekEndingDate` as `date`, the countries' names padded as upstream sends them.
  A week that straddles two market years comes in each, and the records carry no market
  year, so `get_weekly_series` keeps both, the older year's row first.
- `allCountries` has no paging. Over MCP `get_exports` keeps the family's cap, 200 rows or 64
  KB, with a note of its own that names `country_code` (`tasks.MCP_CAPS`; conventions §8,
  sdk-core ADR-0038; https://github.com/xippios/sdk-usda-esr/pull/3), and the cap's note tells
  agents to pass it: one destination is up to 54 rows. The cap is paged and keeps the newest
  weeks: a continuation runs the task again, which core's cache answers. `get_weekly_series`
  makes one request per market year, at most 10 per call (`tasks.SERIES`, core's `Ceiling`) in
  Python, over HTTP and over MCP alike, and over MCP keeps the same cap, about three market
  years, the newest weeks shown, with a note of its own that names `start_year` and `end_year`
  (https://github.com/xippios/sdk-usda-esr/pull/10). The docstring and the cap's note of each
  of the two state the most that one call sends, with core's four attempts for each request:
  2 requests and 8 attempts for `get_exports`, 11 and 44 for `get_weekly_series`, the release
  list counted; a change of the requests a task sends changes both.
- Destination `9990` (UNKNOWN) comes in `allCountries` as a row like any country's: the
  tasks keep it like any other code.
- Empty means empty, not an error: `params` refuses unknown codes (`UnknownCode`, naming the
  nearest codes) and market years after the current UTC year plus two before the call. A
  market year ESR has not released cannot be told from one without exports, so `get_exports`
  and `get_weekly_series` read the release list for a market year from the current UTC year
  on, the series for its `end_year`, and refuse one past the commodity's current market year
  with `NotFoundError` naming the latest released one, both through `tasks._check_released`
  (https://github.com/xippios/sdk-usda-esr/pull/10,
  https://github.com/xippios/sdk-usda-esr/issues/21; conventions §4; sdk-core ADR-0041,
  decisions 6 and 7). The read is one request, which core's cache answers within its
  lifetime. The current year counts too: a market year named by it may have begun without a
  week released, as a calendar-year commodity's does in January.
- ESR's empty 404 for a market year it holds no data for (1900) is mapped by the gateway to
  the shared package's `xippios.usda.fas.NoDataForYear`, a `NotFoundError` (only that answer
  on an exports path, `_client.DATA_PATH`). `get_exports` raises it again, naming what was
  asked for. `get_weekly_series` skips such a year inside its range, as sdk-usda-psd's
  `get_time_series` does, and a released year answering `[]` adds no rows
  (https://github.com/xippios/sdk-usda-esr/pull/10); its `meta.notes` names each market year
  answered with its count of rows, in the order of the rows, and each passed over, since no
  record states its market year (https://github.com/xippios/sdk-usda-esr/issues/23). Where
  ESR's data begins is not established, so no lower bound beyond four digits is set
  (`params.EARLIEST_MARKET_YEAR`).
- ESR's 400 for a path value that is not an integer is mapped to `InvalidRequestError`;
  never sent, since parameters are `int`.
- api.data.gov's 403 for an invalid key is mapped by the gateway to `AuthError` naming the
  code and `DATA_GOV_API_KEY`.
- `meta.vintage` and `meta.published_at` of `get_exports` and `get_weekly_series` stay
  `None`: the exports records state no release, and `vintage` is set only from an
  identifier that upstream states for the data answered, which a week computed from the
  records is not (conventions §4; https://github.com/xippios/sdk-usda-esr/issues/67). Each
  docstring says so and names `get_release_dates` for the release. `get_release_dates`'
  `meta.published_at` is the newest `releaseTimeStamp` as upstream gives it, naive,
  with `meta.published_at_naive` set, since the snapshot states no zone and none is
  invented; its `meta.vintage` is that record's `releaseTimeStamp` exactly as upstream
  sent it (`"2026-10-22T08:30:42.67"`). `DataReleaseInfo` keeps the time as its one parsed
  field, a naive `datetime` with every digit upstream sends, and no text beside it
  (https://github.com/xippios/sdk-usda-esr/issues/60, part 3), so the wrapper
  `api.get_data_release_info` reads each record's text from the decoded answer and hands
  the texts to the task beside the records, in its `ReleaseList`, a list in the order of
  the records, and the task reads the newest record's text at its place
  (`tasks._newest`); both `None` for an empty answer
  (https://github.com/xippios/sdk-usda-esr/pull/7; sdk-core ADR-0041, decision 2).

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1, DATA_GOV_API_KEY

uv run xippios-usda-esr-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs the live tests nightly at 05:40 UTC, a time derived from
the slug so that sources sharing a key never start together, and on demand; a pull request never runs them.
Only its `uv run pytest -m live --tb=short --assert=plain` step sees the key, from the org secret `DATA_GOV_API_KEY`.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them, the
docstring of `mcp.py` included: its own words go into a file it fills. A line it has to
add to one, such as a dependency in `pyproject.toml`, the update carries into the new
render, silently where the release leaves the lines around it alone and as a conflict
where it changes them.

## USDA FAS Export Sales Reporting specifics

- The quota is the gateway's, not this package's: `_client.py` puts `Gateway.policy` of
  `xippios.usda.fas`, the one `QuotaPolicy` per process for the shared key, on `config` with
  `gateway.install(...)`, and `classify` asks `gateway.classify` first, which maps a spent
  quota's 429 to `RateLimitError` with `retry_after` (sdk-core ADR-0032, sdk-core ADR-0033,
  sdk-core ADR-0037). An endpoint added here installs no policy of its own; only ESR's own
  error shapes go into `classify`, after the gateway's.
- The live run, `uv run pytest -m live --tb=short --assert=plain`, spends keyed calls of the
  shared quota, one for each request that core's cache does not answer; core's testing plugin
  prints their count as `requests sent by the live run: <n>`.

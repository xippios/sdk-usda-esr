# sdk-usda-esr — instructions for Claude Code

`xippios-usda-esr` wraps USDA FAS Export Sales Reporting as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file is the contract for every session
that works here; the family rules it points to apply as well.

## What this package wraps

| | |
| --- | --- |
| Upstream | USDA FAS Export Sales Reporting, https://www.fas.usda.gov/programs/export-sales-reporting-program |
| API base URL | `https://api.fas.usda.gov`, api.data.gov's gateway (the portal document's `host`): `BASE_URL` is the host root, and every path keeps the snapshot's `/api/esr/` prefix (`/api/esr/commodities`, `/api/esr/exports/commodityCode/{commodityCode}/...`) |
| Documentation | https://apps.fas.usda.gov/opendatawebV2/, snapshotted in `docs/upstream/` |
| Credentials | `DATA_GOV_API_KEY` from the environment, sent as the `X-Api-Key` header. ADR-0009: one key variable per issuer when one key serves several sources, so every source reached through api.data.gov (`usda-psd`, `usda-esr`, `usda-gats`) reads `DATA_GOV_API_KEY`, and one key is one gateway quota |
| Rate limit | ADR-0010, decisions 1–5. Pace: 60 requests per minute, burst 1 (`RateLimit(per_minute=60, burst=1)` in `_client.py`, enforced client-side): a self-imposed pace, upstream documents none (the snapshot names no limit). Quota: api.data.gov's 1,000 requests per rolling hour per key, reported in `x-ratelimit-limit` / `x-ratelimit-remaining` on every keyed answer (the hourly quota, not a pace) and shared with `usda-psd`, `usda-gats` and every process using the same `DATA_GOV_API_KEY`; it may be spent, it is not pre-rationed. Core's `QuotaPolicy` (`_client.policy`, ADR-0015) keeps the snapshot from every answer from the wire, never a cache hit's, and gates: once the quota is spent the next request waits it out inside the call, logged, when that is within `RetryPolicy.backoff_max` (30 s by default), and otherwise raises `RateLimitError` with `retry_after` without sending. The wait counts from the last answer: a 429's `Retry-After`, else the policy's `window` of one hour (the gateway sends no reset header). `classify` maps the 429 (`OVER_RATE_LIMIT`, not recorded for ESR) to `RateLimitError` with `retry_after` from `Retry-After`, else 3600 s, and core shapes its retries from that: a wait beyond `backoff_max` is raised after one request. In offline tests core's pytest plugin bypasses the limiter and the quota policy and forgets the snapshot around each test; a test that asserts a wait or a refusal is marked `rate_limited` |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.
If it is empty or stale, run `/refresh-upstream` first and review the diff. Never write a
wrapper from memory of the API.

The gateway pieces in `_client.py` (the `X-Api-Key` auth, the `QuotaPolicy` on
`x-ratelimit-*`, the `API_KEY_*`, `OVER_RATE_LIMIT` and `NOT_FOUND` mappings with
host-free messages) are the third copy of sdk-usda-psd's adopted shape, accepted until
core 0.3.0 brings a shared api.data.gov gateway module (family review C14, conventions §15
item 4); they move there then.

## Upstream behaviour established by fixtures

The snapshot types every response as `object` and defines no schema, so these facts come
from the answers recorded on 2026-10-25 under `tests/fixtures/`; `_client.classify` maps
them once.

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
  a midnight without zone (`date` here). Wheat white to Canada 2024: 54 weeks.
- `allCountries` has no paging: cottonseed 2024 is 498 records for 11 destinations,
  139,119 bytes (`cottonseed_2024`); wheat HRW 2024, measured and not kept, 1,136 records
  for 28 destinations, 319,532 bytes. Over MCP `get_exports` keeps the family's cap, 200
  rows or 64 KB, with a note of its own that names `country_code` (`tasks.MCP_CAPS`;
  conventions §8, ADR-0016; Johannes, 2026-10-25), and the docstring tells agents to pass
  it: one destination is up to 54 rows.
- Unknown commodity (999) and unknown country (9999): HTTP 200 with `[]`; so are a
  future market year (2099) and valid codes without exports (rye `allCountries` 2024).
  Empty means empty, not an error; `params` refuses unknown codes (`UnknownCode`, naming
  the nearest codes) and market years after the current UTC year plus two before the call.
- Market year 1900: HTTP 404 with an empty `text/plain` body on the exports path, mapped
  to `errors.NoDataForYear`, a `NotFoundError` (only that answer on an exports path).
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
  ISO date (`"2024-06-06"` for wheat white to Canada 2024), `None` for an empty answer; of
  `get_release_dates` the latest `releaseTimeStamp`'s text, its `isoformat()`: upstream
  writes two fractional digits (`2026-10-22T08:30:42.67`), the vintage renders six
  (`"2026-10-22T08:30:42.670000"`; Johannes, 2026-10-26, for every FAS package).
  `meta.published_at` stays `None` for both: `get_exports` makes no second call, and the
  snapshot states no zone for `releaseTimeStamp` (Johannes, 2026-10-25); no zone is
  invented, since core's `ResultMeta` refuses a naive `published_at`.

## Read first, in this order

1. `docs/upstream/FETCHED.md` and the files it lists: what the upstream actually offers
2. The family conventions: `../sdk-core/docs/conventions.md` and `../sdk-core/docs/adr/`
   (also at https://github.com/xippios/sdk-core/tree/main/docs)
3. `../sdk-core/docs/definition-of-done.md`: what a PR must satisfy
4. The family file `../CLAUDE.md`
5. When a new core minor or template release comes: conventions §15, the adoption
   checklist, which `/adopt-release` walks

## The one rule: three layers (ADR-0001)

```
api/<operation>.py   one async function per upstream operation, upstream names, returns models
tasks.py             the public API: composes wrappers, returns Result[T], sync facade via sync()
mcp.py  http.py      adapters: register tasks.__all__, nothing else. Never edited to add an endpoint.
```

Adapters call only task functions. Tasks call only endpoint wrappers and reference
data. If logic appears in `mcp.py` or `http.py`, it belongs in `tasks.py`.

## Layout

```
src/xippios/usda/esr/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the configured client (base URL, key, rate limit, classify, quota)
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation
  tasks.py         task functions; __all__ is what the adapters register, MCP_CAPS any
                   per-tool result caps
  mcp.py           xippios-usda-esr-mcp entry point
  http.py          FastAPI router
  errors.py        UnknownCode (a code the packaged lists lack), NoDataForYear
  params.py        packaged lists (PACKAGED_LISTS, packaged_values()) and the code and year checks
  enums.py         IntEnum UnitId from the packaged unitsOfMeasure; never edited by hand
  reference/       packaged code lists (JSON) plus README with provenance
scripts/
  refresh_upstream.py    regenerates the docs/upstream/ snapshot, stdlib only, no key
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  check-siblings.sh      this wheel, xippios-usda-psd and xippios-usda-nass share xippios.usda
                         (both siblings from PyPI; workflow siblings.yml)
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written
  test_tasks.py    structural checks on every task plus per-task replay tests, MCP and HTTP
  test_lists.py    the list tasks answer the recorded lists from the package, without a call
  test_slices.py   the slices replay the recorded exports answers: selection and order only
  test_api.py      replay tests for the endpoint wrappers
  test_client.py   wiring, classify on recorded error bodies, core's quota policy on a 429
  test_params.py   packaged lists, the enum and the code and year checks
  test_adapters.py the adapters expose exactly tasks.__all__
  test_layout.py   namespace levels stay empty; py.typed ships
  test_live.py     @pytest.mark.live smoke tests, one per task (10 keyed calls in all: the
                   list tasks' test compares each packaged list with the live one), and the
                   template's keyless reachability check
docs/upstream/     documentation snapshot and FETCHED.md
.github/workflows/ ci.yml (the required ci check), publish.yml (tag to PyPI), live.yml (nightly live tests),
                   siblings.yml (scripts/check-siblings.sh, this package's own: a visible check
                   the org ruleset does not require)
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep,
                   adopt-release
```

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package, and so is every level
between it and the package (`src/xippios/usda/`).
Never add one; `tests/test_layout.py` fails if it appears. The import path is
`xippios.usda.esr` (ADR-0006).

## How to add an endpoint

Run `/add-endpoint <upstream operation>`. In short:

1. Read the operation in `docs/upstream/`. Names, parameters and semantics come from
   there, snake_cased, nothing renamed, nothing normalised across sources.
2. `models.py`: an `UpstreamModel` per payload object; dates, numbers and enums typed.
3. `api/<operation>.py`: one async wrapper that calls `_client.client` and returns
   models through `xippios.core.parse`.
4. `tasks.py`: an async task that composes wrappers and returns `Result[T]` with full
   `ResultMeta` (source, endpoint, request parameters, `published_at`/`vintage` when the
   upstream gives them). Derive the sync one with `sync()`, add its name to `__all__`,
   re-export it from `__init__.py`. What it returns leaves out documented personal
   identifiers (`ssn`, `iban` and their like) unless it fetches them deliberately and
   says so, and a write task does not echo one in `meta.request` (ADR-0017).
5. Docstring for agents: one sentence, then `Args:` with examples of valid values for
   every parameter. The MCP tool description and the OpenAPI summary come from it.
6. `/record-fixture` for at least one case, a replay test in `test_tasks.py` that also
   calls the tool end to end with `xippios.core.testing.mcp_call` (and compares what was
   sent through `sent_urls(route)`, never a request from `route.calls`), a live smoke test
   in `test_live.py`.
7. `CHANGELOG.md` under Unreleased, README status table, then the full check suite.

Reference lookups (commodities, countries, attributes) are tasks too, named
`list_<thing>`, so agents can form valid calls; one whose whole list an agent needs and
the default result cap (200 rows or 64 KB) would cut gets a cap of its own in `MCP_CAPS`
in `tasks.py`, which `mcp.py` passes through (ADR-0016). A task-shaped function that returns a
subset of an upstream record builds its model with `UpstreamModel.project`; nothing is
renamed or computed, parsing a value (`parse_decimal`) is the only override. Upstream's
documented error shapes go into `ClientConfig.classify` in `_client.py`, once; wrappers
use `client.get_json` and never inspect status codes. An upstream that reports an hourly
or daily quota gets one `QuotaPolicy` installed on `config` there, as `_client.py` does:
`policy = QuotaPolicy(...)` installed on `config` with `policy.install(...)`, and
`classify` maps its answer to a spent quota to `RateLimitError` with `retry_after`
(ADR-0010, ADR-0015).

## How to record a fixture

Run `/record-fixture <endpoint> <case> <parameters>`. It performs one live request
through the real client with `xippios.core.testing.record_sync` and writes
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed. Grep the file for
key patterns, and for the personal identifiers the package keeps out of its projections
(ADR-0017), before committing. Fixtures are never typed in by hand.

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays fixtures
uv run pytest -m live              # needs XIPPIOS_LIVE_TESTS=1 and DATA_GOV_API_KEY
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
uv run xippios-usda-esr-mcp   # stdio; add --http for streamable HTTP
```

The offline run is core's plugin's (ADR-0013): in every test not marked `live` it refuses
the network and skips the rate limiter's waits, and the key sent is its placeholder,
with `DATA_GOV_API_KEY` set to it because `pyproject.toml` names that variable under
`xippios_placeholder_key_envs`; the package keeps no placeholder fixture of its own.
A test that asserts a limiter wait or a quota pause is marked `rate_limited`, one that
must reach the network `network`.

`.github/workflows/live.yml` runs `uv run pytest -m live` with `XIPPIOS_LIVE_TESTS=1`
nightly at 05:40 UTC, a time derived from the slug so that sources sharing a key never
start together, and on demand from the Actions tab; pull requests never run live tests.
Only its `uv run pytest -m live` step sees the key, from the org secret `DATA_GOV_API_KEY`.

## Workflow rules

- Branch from `main` as `feature/<topic>`, `fix/<topic>`, `chore/<topic>` or `docs/<topic>`.
  Never commit to `main`.
- Commit small, with Conventional Commits messages (`feat(tasks): add get_balance_sheet`).
- Open the PR with `gh pr create`; the body is the definition-of-done checklist from
  `.github/PULL_REQUEST_TEMPLATE.md`, ticked honestly, with assumptions listed.
- `ruff` leaves `docs/` alone; never reformat the upstream snapshot.
- Template and core updates: a new sdk-template release, and the core minor it carries,
  arrive in one adoption PR, `chore/template-update-<tag>`, before the next release
  (conventions §15); `/adopt-release <tag>` walks it, and it auto-merges after the
  reviewer's `ready`. `uvx copier update` re-renders the files the template owns
  (`tests/conftest.py`, `tests/test_layout.py` and `tests/test_adapters.py` among them;
  answers are in `.copier-answers.yml`) and never overwrites the files this package fills:
  `__init__.py`, `_client.py`, `models.py`, `api/`, `tasks.py`, `tasks_write.py`,
  `params.py`, `enums.py`, `reference/`, `scripts/`, `tests/test_tasks.py`,
  `tests/test_tasks_write.py`, `tests/test_live.py`, `tests/fixtures/`, `docs/upstream/`,
  `README.md` and `CHANGELOG.md`. Template changes to those are listed per release under
  "Hand-apply" in sdk-template's
  [CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md); port them
  by hand in the same PR.
- If a convention seems wrong, say so in the PR and follow it anyway; changing it is a
  PR against `sdk-core/docs/conventions.md` plus an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping for key patterns.
- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`.
- Never write a key into a file or a commit.
- Never put logic in `mcp.py` or `http.py`; never add a route or tool by hand.
- Never rename or re-map an upstream concept to another source's (ADR-0003).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (ADR-0017).
- Never edit `docs/upstream/` by hand; `/refresh-upstream` fetches, a PR reviews.
- Never add `src/xippios/__init__.py` or `src/xippios/usda/__init__.py`, the provider level.
- Never tag, merge, release, force-push, or touch `gh secret`. Those are human actions;
  the one exception is enabling auto-merge on a `chore/template-update*` or
  `chore/release-*` PR after the reviewer's `ready` (ADR-0018).

## When something is unclear

Prefer the smallest change that satisfies the documents above, state the assumption in
the PR description, and stop rather than guess at upstream semantics or public API shape.

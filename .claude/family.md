The family rules for every `xippios-<source>` repository; `CLAUDE.md` imports this file and holds the facts of this package.

## Read first, in this order

1. `docs/upstream/FETCHED.md` and the files it lists: what the upstream actually offers,
   the reference for names, parameters and semantics. If the snapshot is empty or stale,
   run `/refresh-upstream` first and review the diff. Never write a wrapper from memory
   of the API.
2. The family conventions and ADRs:
   https://github.com/xippios/sdk-core/blob/main/docs/conventions.md and
   https://github.com/xippios/sdk-core/tree/main/docs/adr
3. What a PR must satisfy,
   https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and what the
   reviewer checks it against,
   https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md
4. The facts of this package in `CLAUDE.md`. The workspace's own `CLAUDE.md` applies
   as well when you work from it.
5. When a new core minor or template release comes: conventions §15, the adoption
   checklist, which `/adopt-release` walks

## The one rule: three layers (ADR-0001)

```
api/<operation>.py   one async function per upstream operation, upstream names, returns models
tasks.py             the public API: composes wrappers, returns Result[T], sync facade via sync()
mcp.py  http.py      adapters: register tasks.__all__, nothing else. Never edited to add an endpoint.
```

Adapters call only task functions. Tasks call only endpoint wrappers and reference
data. If logic appears in `mcp.py` or `http.py`, it belongs in `tasks.py`. `api/` holds
one module per upstream operation, or one per service where operation ids repeat across
services; the Layout in `CLAUDE.md` says which.

A source whose upstream publishes files keeps the three layers (ADR-0020): `api/` wraps
the HTTP endpoints it has, a catalog say, the download goes through core's `download` or
through the source package it depends on, and `parse/` holds one module per file kind
with one function, `parse_<file_kind>(path) -> list[Model]`, whose library (a
spreadsheet reader, `pypdf`) the source declares, never core. A PDF is read for its
narrative text only, never for numbers: a figure a task returns comes from the XLS,
XML, CSV or TXT the release carries, or is not returned. A bulk task, one that returns a
file or a list read from one, is named in `BULK_TASKS` in `tasks.py`, beside `MCP_CAPS`:
it is Python-only, no tool and no route, since the adapters skip it and no tool hands
an agent a file path (ADR-0019 decision 4).

## Namespace packages (ADR-0006)

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package, and so is every level between it and the
package (the provider level of a nested import path). `CLAUDE.md`'s Layout names them.
Never add a namespace `__init__.py`; `tests/test_family.py` fails if it appears.

## How to add an endpoint

Run `/add-endpoint <upstream operation>`. In short:

1. Read the operation in `docs/upstream/`. Names, parameters and semantics come from
   there, snake_cased, nothing renamed, nothing normalised across sources.
2. `models.py`: an `UpstreamModel` per payload object; dates, numbers and enums typed.
   An enumeration written by hand, for a value set upstream documents, lives there too,
   unexported, since `enums.py` is generated whole.
3. `api/<operation>.py`, or the service's module: one async wrapper that calls
   `_client.client` and returns models through `xippios.core.parse`.
4. `tasks.py`: an async task that composes wrappers and returns `Result[T]` with full
   `ResultMeta` (source, endpoint, request parameters, `published_at`/`vintage` when the
   upstream gives them). Derive the sync one with `sync()`, add its name to `__all__`,
   re-export it from `__init__.py`. What it returns leaves out documented personal
   identifiers (`ssn`, `iban` and their like) unless it fetches them deliberately and
   says so (ADR-0017).
5. Docstring for agents: one sentence, then `Args:` with examples of valid values for
   every parameter. The MCP tool description and the OpenAPI summary come from it.
6. `/record-fixture` for at least one case, a replay test in `test_tasks.py` that also
   calls the tool end to end with `xippios.core.testing.mcp_call` (and compares what was
   sent through `sent_query(route)` or `sent_urls(route)`, never a request from
   `route.calls`), a live smoke test in `test_live.py`.
7. `CHANGELOG.md` under Unreleased, README status table (the task's name first in its
   cell, in backticks, as the comment above the table says), then the full check suite.

Reference lookups (commodities, countries, attributes) are tasks too, named
`list_<thing>`, so agents can form valid calls; one whose whole list an agent needs and
the default result cap (200 rows or 64 KB) would cut gets a cap of its own in `MCP_CAPS`
in `tasks.py`, which `mcp.py` passes through (ADR-0016). A task-shaped function that returns a
subset of an upstream record builds its model with `UpstreamModel.project`; nothing is
renamed or computed, parsing a value (`parse_decimal`) is the only override. Upstream's
documented error shapes go into `classify` in `_client.py`, the `ClientConfig.classify`
hook, once, and an error class of the package's own into `errors.py` (conventions §5,
§6); wrappers use `client.get_json` and never inspect status codes. An upstream that
reports an hourly or daily quota gets one `QuotaPolicy` installed on `config` there
(`config = QuotaPolicy(window=..., limit_header=..., remaining_header=...,
source=SOURCE).install(config)`, with the headers and window the upstream documents, as
core's README shows), and `classify` maps its answer to a spent quota to
`RateLimitError` with `retry_after` (ADR-0010, ADR-0015). A source behind api.data.gov
takes both from `xippios.core.data_gov`'s `Gateway(SOURCE)`: its `install` puts the one
policy per process for the shared key on `config`, and its `classify` comes first in the
source's (ADR-0009).

## How to record a fixture

Run `/record-fixture <endpoint> <case> <parameters>`. It performs one live request
through the real client with `xippios.core.testing.record_sync` and writes
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed. Grep the file for
key patterns, and for the personal identifiers the package keeps out of its projections
(ADR-0017), and stage it before `pre-commit run --all-files`, which scans only the files
in git's index. Fixtures are never typed in by hand. A fixture file stays under 256 KiB:
a large text or JSON array is recorded with `max_bytes=`, which marks it `truncated`,
and anything the recorder will not cut (a JSON object, XML, ZIP, gzip, XLS, XLSX) is a
small real answer or sample (ADR-0019 decision 5). A download's fixture is the recorded
exchange of the file's URL, which the plugin replays for the download call. A source
that parses files keeps beside it a sample of each file kind under
`tests/fixtures/files/<file_kind>/<case>.<ext>`, which its parser tests read, with one
provenance row per sample in `tests/fixtures/files/README.md`; a test on a sample or a
cut fixture asserts the parser's shape, never a size, and one live test per file kind
checks that the parser still reads the current release (ADR-0020).

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays fixtures
uv run pytest -m live --tb=short   # needs XIPPIOS_LIVE_TESTS=1, and the key where there is one

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
```

The offline run is core's plugin's (ADR-0013): in every test not marked `live` it refuses
the network and skips the rate limiter's waits, and a keyed package sends its placeholder
key (`CLAUDE.md`, Commands). A test that asserts a limiter wait or a quota pause is marked
`rate_limited`, one that must reach the network `network`.

`.github/workflows/live.yml` runs `uv run pytest -m live --tb=short` with
`XIPPIOS_LIVE_TESTS=1` nightly, at the time `CLAUDE.md` names, and on demand from the
Actions tab; pull requests never run live tests. Every live run takes `--tb=short`, which
keeps a failing test's frame arguments, a raw upstream payload among them, out of a log
that is public; pytest's assertion introspection still prints the values an `assert`
compares, so a live test asserts on shapes and counts, never on a raw payload.

## Workflow rules

- Branch from `main` as `feature/<topic>`, `fix/<topic>`, `chore/<topic>` or `docs/<topic>`.
  Never commit to `main`.
- Commit small, with Conventional Commits messages (`feat(tasks): add get_balance_sheet`).
- Open the PR with `gh pr create`; the body is the definition-of-done checklist from
  `.github/PULL_REQUEST_TEMPLATE.md`, ticked honestly, with assumptions and open
  questions listed, the live calls the PR spent counted (keyed calls by number; `none`
  is a count), and, after the checklist, a `## Decisions taken` block: one line per
  decision the session made, each backed by a convention, an ADR, a coordination rule, a
  dated decision of Johannes's or `gap, row N`. The reviewer judges the PR against
  sdk-core's `docs/review-checklist.md`.
- Every PR but a release or Dependabot's adds an entry under Unreleased in
  `CHANGELOG.md`, an adoption PR's naming the core, template and conventions versions it
  adopts (conventions §15 item 9); `ci.yml` fails without one (conventions §12).
- Releases follow the release train (conventions §12): `/release-prep` opens a release
  PR that changes no file but `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `README.md`,
  `CLAUDE.md` and `docs/handover.md`. In `CHANGELOG.md` it turns `## [Unreleased]`
  into `## [X.Y.Z] - <date>`; the section may gain a lead paragraph and says internal
  labels (decisions, queue rows, plan items) in plain words, since it becomes the tag's
  message. Its merge runs `publish.yml`, which tags the version on the merge commit, and
  Johannes approves the `pypi` run. A reference-data refresh or a core pin's removal is
  a PR of its own before it.
- `ruff` leaves `docs/` alone; never reformat the upstream snapshot.
- Template and core updates: a new sdk-template release, and the core minor it carries,
  arrive in one adoption PR, `chore/template-update-<tag>`, before the next release
  (conventions §15); `/adopt-release <tag>` walks it, and when its merge class is `auto`
  the session enables auto-merge after the reviewer's `ready` (ADR-0018, amendment (e)).
  `uvx copier update` re-renders the files the template owns (this file,
  `tests/conftest.py` and `tests/test_family.py` among them; answers are in
  `.copier-answers.yml`) and never overwrites the files this package fills:
  `__init__.py`, `_client.py`, `errors.py`, `models.py`, `api/`, `parse/`, `tasks.py`,
  `params.py`, `enums.py`, `reference/`, `scripts/`, `tests/test_tasks.py`,
  `tests/test_live.py`, `tests/fixtures/`, `docs/upstream/`, `README.md`, `CHANGELOG.md`
  and `CLAUDE.md`.
  Template changes to those are listed per release under "Hand-apply" in sdk-template's
  [CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md); port them
  by hand in the same PR.
- This file is the template's and the same in every source: what is this package's own
  goes into `CLAUDE.md`, never here; a change to a family rule is a PR against
  sdk-template.
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
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and
  the package (the provider level of a nested import path).
- Never tag, merge, release, force-push, or touch `gh secret`: a release PR's merge tags
  through `publish.yml`, and Johannes approves the `pypi` run. The one exception is
  enabling auto-merge on a `chore/template-update*` or `chore/release-*` PR whose merge
  class is `auto`, after the reviewer's `ready` (ADR-0018, amendment (e)).

## When something is unclear

Prefer the smallest change that satisfies the documents above, state the assumption in
the PR description, and stop rather than guess at upstream semantics or public API shape.

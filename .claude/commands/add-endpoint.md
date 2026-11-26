Add an endpoint wrapper and a task function for the USDA FAS Export Sales Reporting operation: $ARGUMENTS

Follow the three layers of conventions §2 (sdk-core ADR-0001). Each step names the section
of sdk-core's conventions that holds its rules and the name of xippios-core that serves it.
The change meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md: step 9
lists what they check in an endpoint.

1. **Read the upstream reference first.** Open `docs/upstream/FETCHED.md` and the file
   that documents this operation. If the snapshot does not cover it, stop and run
   `/refresh-upstream`; never write a wrapper from memory. Note the exact operation
   name, every parameter with its valid values, the response shape, pagination, and any
   publication date or release identifier the response carries.

2. **Models** in `src/xippios/usda/esr/models.py`: one `UpstreamModel` subclass per
   payload object, named and typed by conventions §3. A field takes upstream's name in
   snake case and accepts upstream's spelling with `Field(validation_alias=...)`, never
   `Field(alias=...)`, and a time upstream prints is read into the type that keeps
   everything it sends, with no text beside it. A code field marks where its codes' names
   come from with `NamedBy(...)` in its annotation (conventions §4):
   `Annotated[str, NamedBy(REGIONS)]` for the packaged list of step 5, whose names the
   answer puts in `meta.names`, or `Annotated[int, NamedBy("item")]` for the field in
   which upstream sends the name, which stands on the record beside its code and takes no
   entry there. An enumeration written by hand, for a value set upstream documents and no
   packaged list renders, lives here too, since `enums.py` is generated whole
   (`/refresh-reference-data`), and an offline test reads it against `docs/upstream/`.

3. **Endpoint wrapper** in `src/xippios/usda/esr/api/<wrapper>.py`, or in the
   service's module where operation ids repeat and `docs/layout.md` keeps one module per
   service: one async function, named from the operation's id by conventions §2, the
   verbatim id kept in the first line of its docstring and in the `endpoint=` it passes.
   Parameters as upstream names them, snake_cased; it calls
   `xippios.usda.esr._client.client`,
   reads JSON through `get_answer`, the one reader, and returns an `Answer`: the one
   `get_answer` gives, its models parsed by `parse=`, or
   `Answer(value, answer.retrieved_at)` for a value it derives from `answer.payload`
   (conventions §4, §6). No defaults beyond upstream's own, no composition, no
   status-code checks: upstream's error shapes go into `classify` in `_client.py`, an error
   class of the package's own into `errors.py` (conventions §5, §6).

   An operation that upstream serves from another host than `BASE_URL`'s follows the
   rule of one limiter per host (conventions §2, §6): a second base on the same host goes
   through `client` by its absolute URL, and `classify`'s path checks name both
   bases; a mirror the publisher runs takes its canonical host's pace, and
   `docs/upstream/` names both hosts; a host that a dependency sends to is reached through
   its tasks alone; any other host gets a client of its own in `_client.py`, with its
   `RateLimit`, and its row in the table of `CLAUDE.md`.

4. **Task function** in `src/xippios/usda/esr/tasks.py`, a task as conventions §2
   defines it: its operation's answer for the arguments given, the arguments that
   identify a record positional in the order of upstream's path and every filter
   keyword-only. It composes wrappers and returns `Result[T]` with full `ResultMeta`, its
   `retrieved_at` the one that its wrapper's `Answer` carries, the oldest of several
   (conventions §4). Then: `get_<thing> = sync(get_<thing>_async)`, add `"get_<thing>"`
   to `__all__`, and re-export it from `__init__.py`.
   A projection leaves out documented personal identifiers (conventions §3). A cap of its
   own over MCP is an entry of `MCP_CAPS` (conventions §8): for a list an agent needs
   whole, or one upstream page that returns whole with the `next_token` the caller needs;
   `ResultCap(paged=True)` where a second run costs upstream nothing, and
   `ResultCap(keep="last")` for a series ordered oldest first. A bulk task, which returns
   a file or a list read from one, is named in `BULK_TASKS`.

   Where a task meets one of these, it takes core's helper and writes none by hand:
   - an offset-paged list collected whole: the walk,
     `fetch_pages(fetch, page_size=..., most=..., paging=...)`, whose bound of `most`
     pages the task's docstring states (conventions §4);
   - a `since` that takes back the `meta.vintage` of an earlier call:
     `newer_than(since, items, released=..., read=...)`, `read` the source's own reader of
     its vintage's text (conventions §4);
   - an upstream that counts a query's records on request and serves at most a limit per
     call: `fetch_counted(count, fetch, limit=..., empty=..., narrow=...)`, which refuses
     with `QueryTooLarge` before the data request, as `classify` maps upstream's own
     refusal (conventions §5);
   - a series of one request per period: `Ceiling(most, unit=...)`, whose `check` runs
     before the first request, and `fetch_periods(periods, fetch, skip=...)`; a lower
     ceiling on the MCP server takes `mcp=` and `option=` (conventions §4);
   - a file it downloads: the client's `download`, and `check_dest(dest, source=...)`
     before the task's first request (conventions §6);
   - a code that its answer names: core's decorator `names_codes` with the list's
     declaration of step 5, `@names_codes(region_code=REGIONS)` (conventions §4).

5. **Docstring for agents** on the task, as conventions §8 has it: one sentence, then an
   `Args:` block with valid values for each parameter; the tool's description and the
   route's summary come from it. Errors come from the taxonomy of conventions §5,
   `NotFoundError` where upstream signals absence, and a refusal of the task's own before
   any request says `Nothing was sent.` after its first sentence, as core's do.
   A code the packaged list lacks is refused before the call by the list's declaration,
   `PackagedList.codes(code, name, fold_case=...)`, kept as a constant of the module,
   whose `check(param, value)` takes one code or a list of them and raises core's
   `UnknownCode`, so no task raises it itself (conventions §5).

6. **Tests.** Run `/record-fixture <wrapper> <case> <parameters>` for at least one
   realistic case, or `/record-fixture <task> <case> <parameters>` for a task that sends
   more than one request, add a replay test in `tests/test_tasks.py` using the
   `replay_fixture` fixture, and a `@pytest.mark.live` smoke test in `tests/test_live.py`
   (conventions §10). The replay tests of a family of tasks may live in a module of the
   source's own beside `tests/test_tasks.py`, which `copier update` never touches. What
   was sent is read with `sent_query`, `sent_urls` or `sent_bodies`, and a test that
   builds an answer marks it by its kind, `NOT RECORDED: <where it comes from>
   (conventions §10, kind 2)`, which core's check in `tests/test_built_answers.py` holds.
   A test of a task that answers from a packaged list reads the list's fetch date and
   counts from the packaged file, so a refresh of the list breaks no test.
   Grep the fixture for key patterns before committing.

7. **Docs.** A changelog fragment under `changelog/`, one file holding the change's
   bullet, as `changelog/README.md` lays it out. The README status table under
   `## Status` gets a row (upstream operation, task function, MCP tool name
   `usda_esr_<task>`, status), the task's name first in its `Task function`
   cell, in backticks, as core's family check reads it.

8. **Checks**, all of them:
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   `tests/test_family.py`, core's family check, proves the new task is served as a tool
   and a route, a bulk task as neither, returns `Result[T]` with an agent docstring, and
   stands in the README status table (conventions §10).

9. **Done** when the items of the definition of done's blocks Code, Tests and Docs hold
   for the endpoint, its wrapper matching `docs/upstream/` and its task with its replay
   test and its live smoke test,
   and the checks of step 8 pass.

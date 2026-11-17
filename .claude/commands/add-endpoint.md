Add an endpoint wrapper and a task function for the USDA FAS Export Sales Reporting operation: $ARGUMENTS

Follow the three layers (ADR-0001) exactly. The change meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md: step 9
lists what they check in an endpoint.

1. **Read the upstream reference first.** Open `docs/upstream/FETCHED.md` and the file
   that documents this operation. If the snapshot does not cover it, stop and run
   `/refresh-upstream`; never write a wrapper from memory. Note the exact operation
   name, every parameter with its valid values, the response shape, pagination, and any
   publication date or release identifier the response carries.

2. **Models** in `src/xippios/usda/esr/models.py`: one `UpstreamModel` subclass per
   payload object. Field names are the upstream names in snake_case; where upstream spells
   one differently, accept that spelling with `Field(validation_alias=...)`, never
   `Field(alias=...)`: the adapters serialise by alias, so `alias=` would hand agents
   upstream camelCase rows while tool arguments are snake_case. With `validation_alias`
   the upstream spelling is accepted on input and every output surface stays snake_case.
   Dates become `datetime.date`/`datetime`, numbers become `int`/`Decimal`/`float`,
   upstream enumerations become `StrEnum`, an enumeration of integer ids `IntEnum`
   (conventions §3). No renaming to match another source. An enumeration written by
   hand, for a value set upstream documents and no packaged list renders, lives here
   too, by the family's precedent: `enums.py` is generated whole
   (`/refresh-reference-data`).

3. **Endpoint wrapper** in `src/xippios/usda/esr/api/<wrapper>.py`, or in the
   service's module where operation ids repeat across services and the Layout in
   `CLAUDE.md` keeps one module per service: one async function. The module and the
   function carry the upstream operation name in snake case, from the operation's id in
   the snapshot (an OpenAPI `operationId`, a WADL method id), else from the path, minus a
   controller prefix that every operation of the API shares, so
   `PSDData_GetCommodityDataByYear` is `get_commodity_data_by_year` in
   `api/get_commodity_data_by_year.py`; conventions §2 gives the rule's cases, an id that
   restates the path and a name taken from the path among them. The verbatim id stays in
   the first line of the wrapper's docstring and in the `endpoint=` the wrapper passes, so
   `meta.endpoint` keeps upstream's exact name. Parameters as upstream names them,
   snake_cased; it calls `xippios.usda.esr._client.client` and returns models via
   `xippios.core.parse(...)`. It calls `get_json`, or `get_answer` where the answer may
   come from the cache, whose `retrieved_at` the task puts into its `ResultMeta`, or
   `get` and then `decode_json` where it needs more of the response, a header say
   (conventions §6). No defaults beyond upstream's own, no composition, no status-code
   checks: upstream's documented error shapes go into `classify` in `_client.py`, an
   error class of the package's own into `errors.py` (conventions §5, §6).

4. **Task function** in `src/xippios/usda/esr/tasks.py`: an async function shaped
   like what a person or agent wants (`get_<thing>(...)`, with the parameters a caller
   thinks in), composing wrappers, resolving pagination with `xippios.core.paginate_*`
   and reference lookups, and returning `Result[T]` with full `ResultMeta` (`source`,
   `endpoint`, `request`, and `published_at` / `vintage` when upstream provides them). Then:
   `get_<thing> = sync(get_<thing>_async)`, add `"get_<thing>"` to `__all__`, and
   re-export it from `__init__.py`. A projection the task returns leaves out documented
   personal identifiers (`ssn`, `iban` and their like) unless the task fetches them
   deliberately and says so in its docstring (ADR-0017). A list task whose whole list an
   agent needs, longer than the default result cap, gets a cap of its own in `MCP_CAPS`
   (ADR-0016). So does a task whose result is one upstream page that must return whole, a
   cursor-paged page with the `next_token` the caller needs for the next page or a
   bounded lookup: a byte bound of its own, the row bound unchanged, and where the
   upstream bills per result, the docstring states the price per result (conventions §8;
   ADR-0016, amendment 2026-10-30). A bulk task, one that returns a file or a list read
   from one, is named in `BULK_TASKS` beside it: Python-only, no tool and no route
   (ADR-0019 decision 4).

5. **Docstring for agents** on the task: first line one sentence; then an `Args:` block
   explaining every parameter with examples of valid values. The MCP tool description and
   the OpenAPI summary are generated from it. Errors must come from the taxonomy in
   `xippios.core.errors`; raise `NotFoundError` where upstream signals absence, and
   core's `UnknownCode` for a code the packaged list lacks where upstream answers one
   with an empty result (conventions §5).

6. **Tests.** Run `/record-fixture <wrapper> <case> <parameters>` for at least one
   realistic case, add a replay test in `tests/test_tasks.py` using the `replay_fixture`
   fixture, and a `@pytest.mark.live` smoke test in `tests/test_live.py`. The replay
   tests of a family of tasks may live in a module of the source's own beside
   `tests/test_tasks.py`: `copier update` never touches a file the template has never
   rendered, and `tests/test_tasks.py` itself is the source's once rendered. A replay
   test that checks what was sent compares `xippios.core.testing.sent_query(route)`, the
   scrubbed query of the last request, or `sent_urls(route)`, the URLs with credentials
   redacted, never a request kept from `route.calls`, which a failure or `pytest -l`
   would print. A test of a task that answers from a packaged list reads the list's
   fetch date and counts from the packaged file instead of pinning them, so a refresh of
   the list breaks no test. Grep the fixture for key patterns before committing.

7. **Docs.** A changelog fragment under `changelog/`, one file holding the change's
   bullet, as `changelog/README.md` lays it out. The README status table under
   `## Status` gets a row (upstream operation, task function, MCP tool name
   `usda_esr_<task>`, status), the task's name first in its `Task function`
   cell, in backticks, as core's family check reads it.

8. **Checks**, all of them:
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   `tests/test_family.py`, core's family check, proves the new task is exposed as a tool
   and a route, a bulk task as neither, without touching `mcp.py` or `http.py`, returns
   `Result[T]` with an agent docstring, and is in the README status table.

9. **Done** when each of these holds, the definition of done's checks of an endpoint:
   - the change sits in its layer, and `mcp.py` and `http.py` hold no logic (ADR-0001);
   - the wrapper matches `docs/upstream/`: its name, its parameters and their semantics;
   - the task returns `Result[T]` with full `ResultMeta`, raises only from the taxonomy
     of conventions §5, and has its agent docstring;
   - `__init__.py` exports the task and the README status table lists it;
   - the task has a replay test on a recorded fixture and a live smoke test, and each
     fixture this change adds is recorded, free of key patterns and of the values of the
     fields the source keeps out of its projections (ADR-0017), and under 256 KiB
     (ADR-0019);
   - the changelog fragment says what the change adds for a user of the package;
   - the README says what changed in install, usage or endpoint coverage;
   - the checks of step 8 pass.

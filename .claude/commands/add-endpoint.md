Add an endpoint wrapper and a task function for the USDA FAS Export Sales Reporting operation: $ARGUMENTS

Work on a branch `feature/<operation>`. Follow the three layers (ADR-0001) exactly. The
PR meets the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and the
reviewer judges it against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

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
   too, unexported: `enums.py` is generated whole (`/refresh-reference-data`).

3. **Endpoint wrapper** in `src/xippios/usda/esr/api/<operation>.py`, or in the
   service's module where operation ids repeat across services and the Layout in
   `CLAUDE.md` keeps one module per service: one async function named after the
   operation, parameters as upstream names them, calling
   `xippios.usda.esr._client.client` and returning models via
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
   (ADR-0016). A bulk task, one that returns a file or a list read from one, is named in
   `BULK_TASKS` beside it: Python-only, no tool and no route (ADR-0019 decision 4).

5. **Docstring for agents** on the task: first line one sentence; then an `Args:` block
   explaining every parameter with examples of valid values. The MCP tool description and
   the OpenAPI summary are generated from it. Errors must come from the taxonomy in
   `xippios.core.errors`; raise `NotFoundError` where upstream signals absence, and
   core's `UnknownCode` for a code the packaged list lacks where upstream answers one
   with an empty result (conventions §5).

6. **Tests.** Run `/record-fixture <operation> <case> <parameters>` for at least one
   realistic case, add a replay test in `tests/test_tasks.py` using the `replay_fixture`
   fixture, and a `@pytest.mark.live` smoke test in `tests/test_live.py`. A replay test
   that checks what was sent compares `xippios.core.testing.sent_query(route)`, the
   scrubbed query of the last request, or `sent_urls(route)`, the URLs with credentials
   redacted, never a request kept from `route.calls`, which a failure or `pytest -l`
   would print. A test of a task that answers from a packaged list reads the list's
   fetch date and counts from the packaged file instead of pinning them, so a refresh of
   the list breaks no test. Grep the fixture for key patterns before committing.

7. **Docs.** `CHANGELOG.md` under Unreleased; the README status table gets a row
   (upstream operation, task function, MCP tool name `usda_esr_<task>`, status),
   the task's name first in its cell, in backticks, as the comment above the table says.

8. **Checks**, all of them:
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   `tests/test_family.py`, core's family check, proves the new task is exposed as a tool
   and a route, a bulk task as neither, without touching `mcp.py` or `http.py`, returns
   `Result[T]` with an agent docstring, and is in the README status table.

9. Open the PR with `gh pr create`, its body as the definition of done says. Do not
   merge.

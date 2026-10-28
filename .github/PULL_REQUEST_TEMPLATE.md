## Summary

<!-- what and why, two or three sentences -->

## Definition of done

Tick honestly. An unticked item needs a one-line reason. CI enforces the first block;
the rest is checked in review against sdk-core's `docs/review-checklist.md`. Every PR
deletes the Adoption PR block, except an adoption PR (conventions §15), which keeps it
with the Enforced by CI and Process blocks and deletes Code, Tests and Docs.

### Enforced by CI
- [ ] `ruff check` and `ruff format --check` pass
- [ ] `mypy --strict` passes
- [ ] unit tests pass offline (no network in the default test run)
- [ ] `pre-commit run --all-files` passes (includes secret detection)

### Code
- [ ] change is in the right layer (ADR-0001); no logic in `mcp.py` / `http.py`
- [ ] every new task function returns `Result[T]` with full `ResultMeta`
- [ ] every new endpoint wrapper matches `docs/upstream/` — names, parameters, semantics
- [ ] errors raised are from the taxonomy in `docs/conventions.md` §5
- [ ] public surface changes are reflected in `__init__.py` exports and the README status table
- [ ] a core PR names the two consumers of what it adds (in its ADR, or in its description when it has none), or, in its ADR, the one-consumer reason of ADR-0023 decision 3

### Tests
- [ ] each new task function has a fixture-backed unit test (`tests/fixtures/...` recorded, not hand-written)
- [ ] each new task function has a `@pytest.mark.live` smoke test
- [ ] fixtures contain no credentials: grep `tests/fixtures/` for key patterns and for the values of fields the source keeps out of its projections (ADR-0017) before committing
- [ ] the fixture files this PR adds or changes stay under 256 KiB; a truncated one is marked `truncated: true` with the full count or byte size and sha256 (ADR-0019; binds from the source's 0.3.0 adoption, or from its first PR when it starts on a git pin of core 0.3.0)
- [ ] a file-distributed source: each file kind has a sample under `tests/fixtures/files/<file_kind>/` with its provenance line and one live parser test (ADR-0020)

### Docs
- [ ] docstrings written for agents: one-line summary, `Args:` with valid-value examples
- [ ] `CHANGELOG.md` has an entry under Unreleased
- [ ] README updated if install, usage, or endpoint coverage changed
- [ ] if `docs/upstream/` was refreshed: `FETCHED.md` updated and the diff summarised in the PR

### Adoption PR (conventions §15)
The reviewer judges an adoption PR against this list and nothing else: no new endpoints,
tasks or fixtures ride along, and it deletes only the fixtures, mounts and tests the
adoption itself makes dead (ADR-0018, amendment 2026-10-26). An adoption PR is a
`chore/template-update*` PR: when its merge class is `auto` the session enables
auto-merge after the reviewer's `ready`, and GitHub merges it once `ci` is green and
review threads are resolved; a `human` adoption (a source-owned workflow, a changed
template answer, a protected path, a build or install route) waits for Johannes
(ADR-0018, amendment (e); the merge classes are in the README of the organisation's
`.github` repository).
- [ ] core floor raised: `xippios-core~=X.Y.0`, or `~=X.Y.Z` when patch Z shipped what the source adopts (§12), and its extras likewise; a source package the source depends on bound to its own minor the same way (ADR-0021); from PyPI, no git pin, `uv.lock` updated
- [ ] `copier update` to the template release, conflicts resolved
- [ ] every local workaround a core change replaced is deleted, its tests with it, the core change named for each in the PR description
- [ ] logic duplicated across sources moved into core or dropped; what core lacks is carried by the source and named in a queue row, a second copy only when the row names both sources, never a third (ADR-0023)
- [ ] every test that asserted a limiter wait or a quota pause is marked `rate_limited`, and one that asserted key resolution has a module-level `placeholder_api_key` override that pins nothing (ADR-0013, ADR-0015)
- [ ] generated enum files re-rendered once through the template's refresh script and committed as formatted, after its `ruff format && ruff check --fix`
- [ ] `mypy --strict` covers `scripts/` too
- [ ] the current conventions version applied
- [ ] `CHANGELOG.md` line under Unreleased naming the core, template and conventions versions adopted

### Process
- [ ] branch named `feature/`, `fix/`, `chore/`, or `docs/`; Conventional Commits
- [ ] no tag, release, merge, or secret operation performed by the session; the one exception is enabling auto-merge on an adoption or `chore/release-*` PR when its merge class is `auto`, after the reviewer's `ready`, ADR-0018, amendment (e)
- [ ] assumptions and open questions listed in the PR description
- [ ] live calls spent by this PR are counted in the description (keyed calls by number; `none` is a count)
- [ ] the description carries, after this checklist, a `## Decisions taken` block: one line per decision the session made, each backed by a convention, an ADR, a coordination rule, a decision of Johannes's with its date, or `gap, row N`; a line backed by none of these is a blocking finding
- [ ] a release PR changes only the subset of conventions §12; the reference refresh is its own PR

## Assumptions

<!-- one per line, or "none" -->

## Open questions

<!-- one per line, or "none" -->

## Decisions taken

<!-- one line per decision the session made, each backed by a convention, an ADR, a
coordination rule, a decision of Johannes's with its date, or `gap, row N`; or
"none" -->

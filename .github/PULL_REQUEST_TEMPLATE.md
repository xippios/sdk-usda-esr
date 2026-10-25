## Summary

<!-- what and why, two or three sentences -->

## Definition of done

Tick honestly. An unticked item needs a one-line reason.

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

### Tests
- [ ] each new task function has a fixture-backed unit test (`tests/fixtures/...` recorded, not hand-written)
- [ ] each new task function has a `@pytest.mark.live` smoke test
- [ ] fixtures contain no credentials (grep for the key pattern before committing)

### Docs
- [ ] docstrings written for agents: one-line summary, `Args:` with valid-value examples
- [ ] `CHANGELOG.md` has an entry under Unreleased
- [ ] README updated if install, usage, or endpoint coverage changed
- [ ] if `docs/upstream/` was refreshed: `FETCHED.md` updated and the diff summarised in the PR

### Process
- [ ] branch named `feature/`, `fix/`, `chore/`, or `docs/`; Conventional Commits
- [ ] no tag, release, merge, or secret operation performed by the session
- [ ] assumptions and open questions listed in the PR description

## Assumptions and open questions

<!-- list them, or "none" -->

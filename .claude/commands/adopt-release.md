Adopt an sdk-template release, and the xippios-core minor it carries, in xippios-usda-esr: $ARGUMENTS

Expected argument: the template tag to adopt, e.g. `v0.3.0`; without one, the latest tag
(`git ls-remote --tags --refs https://github.com/xippios/sdk-template.git`). This is the
adoption PR of conventions §15 (ADR-0018): one PR, before the next release, that adopts
the release and changes nothing else; no new endpoints, tasks or fixtures ride along. It
may delete the fixtures, mounts and tests that the adoption itself makes dead, and
nothing more (ADR-0018, amendment (d)). Every step below is the session's: when the PR's
merge class is `auto`, the session enables auto-merge after the reviewer's `ready`; a
`human` adoption (a source-owned workflow, a changed template answer, a protected path, a
build or install route) waits for Johannes (ADR-0018, amendment (e); the merge classes
are in the README of the gates repository, https://github.com/xippios/sdk-gates). A
release tag is not part of an adoption. The PR meets the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and the
reviewer judges it against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **Where the repository stands.** Read `.copier-answers.yml`: `_commit` is the template
   tag the repository is on, `core_version` the core minor it depends on, `core_git_ref` a
   git pin of core, if any. Start from a clean `main` on a branch
   `chore/template-update-<tag>`.

2. **What the releases ask.** Read sdk-template's `CHANGELOG.md` at `<tag>`,
   `https://github.com/xippios/sdk-template/blob/<tag>/CHANGELOG.md` (or
   `git -C <workspace root>/sdk-template show <tag>:CHANGELOG.md` where the family
   workspace holds a clone, the workspace root being the directory that holds the
   workspace's own `CLAUDE.md`; a relative path does not resolve from a worktree), for
   every release after `_commit` up to `<tag>`: its entries, its **Hand-apply** list and
   its "Updating from" paragraph, which names the `-d` answers an update from an older
   tag needs. Then the core release it adopts, `X.Y.Z`, the one the template release
   names (`X.Y.0`, or the patch that shipped what the template needs: core 0.2.1 for
   template v0.2.1, whose `tests/test_family.py` imports what 0.2.0 lacks): sdk-core's
   `CHANGELOG.md` section, the ADRs it names, their Consequences, and
   `docs/handover.md`, section "Adopting core X.Y.Z", for what this
   source deletes and declares (`https://github.com/xippios/sdk-core/tree/vX.Y.Z`, or
   `git -C <workspace root>/sdk-core show vX.Y.Z:<path>`).

3. **Items 1 and 2: the core floor and the template.** First move the tests of the
   source's own out of every file the template release removes, into `tests/test_tasks.py`,
   as the release's CHANGELOG says, and commit: the update deletes such a file, a source's
   own lines in it included, with no conflict marker. If the update ran first, the deleted
   file is still in the last commit, and
   `git show HEAD:tests/test_adapters.py` brings its tests back to move (v0.2.1 removes it
   and `tests/test_layout.py`). Then run

   ```bash
   uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag> -d core_version=X.Y.Z -d core_git_ref=
   ```

   adding every `-d` answer the "Updating from" paragraphs name. Resolve the conflicts:
   `git grep -n '^<<<<<<< before updating'` finds them in the files the template manages
   (`.claude/family.md`, `tests/conftest.py` and `tests/test_family.py` among them). Keep
   the template's side and carry over what the source added on purpose, such as a fixture
   of its own in `conftest.py`; a line of its own in `.claude/family.md` moves to
   `CLAUDE.md`. The files the source fills, `__init__.py`, `_client.py`, `errors.py`,
   `models.py`, `api/`, `parse/`, `tasks.py`, `params.py`, `enums.py`, `reference/`,
   `scripts/`, `tests/test_tasks.py`, `tests/test_live.py`, `tests/fixtures/`,
   `docs/upstream/`, `README.md`, `CHANGELOG.md` and `CLAUDE.md`, are never touched by
   the update. Then `uv lock` and `uv sync --all-extras`. `pyproject.toml` depends on
   `xippios-core~=X.Y.Z`, its `mcp`, `http` and `testing` extras likewise, with no
   `[tool.uv.sources]` left: `~=X.Y.0`, or `~=X.Y.Z` when patch `Z` shipped what the
   source adopts (`~=0.2.1` for template v0.2.1), still one minor (conventions §12,
   ADR-0018 amendment (c)).

4. **Hand-apply.** Port every bullet of every Hand-apply list after `_commit` by hand:
   path, change, reason. A bullet whose file the source changed is ported in the
   source's form; a bullet that does not apply to this source says why in the PR.

5. **Items 3 and 4: workarounds.** Delete every local workaround a core change replaced,
   its tests with it: those the release's ADRs and `docs/handover.md` name for this
   source, and any other the CHANGELOG's breaking changes reach. The PR description names
   the core change for each (`placeholder_api_key` in `conftest.py` → the plugin's pin,
   ADR-0013). Logic duplicated across sources that core does not provide yet is carried
   by the source, named in the PR description and in a queue row; a second source may
   carry the same helper when the row names both, a third never: core takes it in that
   minor (ADR-0023). The fixtures, mounts and tests the adoption makes dead may go with
   it, nothing else.

6. **Item 5: tests that assert what the plugin turns off.** A test that asserts a limiter
   wait, a quota pause or a quota refusal is marked `rate_limited`; a module that tests key
   resolution defines a `placeholder_api_key` fixture that pins nothing; a test that must
   reach the network is marked `network` (ADR-0013, ADR-0015).
   `xippios_placeholder_key_envs` under `[tool.pytest.ini_options]` names
   `DATA_GOV_API_KEY`, and `tests/conftest.py` keeps no placeholder fixture of its own.

7. **Item 6: generated enums.** Re-render `enums.py` once with the release's renderer
   from the packaged lists, `uv run python scripts/refresh_reference.py --render-only`,
   which formats it with `ruff format` and `ruff check --fix` (step 4 ports the flag and
   the ruff step where the script lacks them; a script of the source's own shape gains
   both and passes `mypy --strict`, and need not take the template's shape), and commit
   it as formatted. An adoption fetches nothing: the packaged lists keep what was
   fetched, a file the Hand-apply list converts (a value list into records) changing
   its shape only, since the PR changes nothing else, and so does
   `docs/upstream/FETCHED.md`, left to the next `/refresh-upstream`; only the capture
   script's changes are ported (conventions §15, ADR-0003 amendment).

8. **Item 7: scripts.** `uv run mypy` covers `scripts/` too
   (`files = ["src", "tests", "scripts"]`); fix what `--strict` reports there.

9. **Item 8: conventions.** The release names a conventions version (the header of
   sdk-core's `docs/conventions.md`, e.g. 1.21); every rule changed since the version
   this repository last applied (its `CHANGELOG.md` says which) holds after this PR, or
   the PR says why not.

10. **Item 9: changelog.** One line under Unreleased in `CHANGELOG.md` naming the core,
    template and conventions versions adopted, e.g. "Adopted xippios-core 0.3.0,
    sdk-template v0.3.0 and conventions 1.21 (conventions §15)."

11. **Checks**, all of them:
    `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.

12. **The PR.** `gh pr create` from `chore/template-update-<tag>`, its body as the
    definition of done says for an adoption PR, with the core change named for each
    deleted workaround. After the reviewer's `ready`, if the `merge-class` check says
    `auto`, the session enables auto-merge here, as `.claude/settings.json` allows;
    every other `gh pr merge` meets the permission prompt:

    ```bash
    gh pr merge --auto --squash -R xippios/sdk-usda-esr <number>
    ```

    GitHub merges once `ci` is green and review threads are resolved. A `human`
    adoption waits for Johannes (ADR-0018, amendment (e)).

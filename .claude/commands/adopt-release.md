Adopt an sdk-template release, and the xippios-core minor it carries, in xippios-usda-esr: $ARGUMENTS

Expected argument: the template tag to adopt, e.g. `v0.2.0`; without one, the latest tag
(`git ls-remote --tags --refs https://github.com/xippios/sdk-template.git`). This is the
adoption PR of conventions §15 (ADR-0018): one PR, before the next release, that adopts
the release and changes nothing else; no new endpoints, tasks or fixtures ride along.
Every step below is the session's, none is a human's: the PR auto-merges after the
reviewer's `ready`, and a release tag is not part of an adoption.

1. **Where the repository stands.** Read `.copier-answers.yml`: `_commit` is the template
   tag the repository is on, `core_version` the core minor it depends on, `core_git_ref` a
   git pin of core, if any. Start from a clean `main` on a branch
   `chore/template-update-<tag>`.

2. **What the releases ask.** Read sdk-template's `CHANGELOG.md` at `<tag>`,
   `https://github.com/xippios/sdk-template/blob/<tag>/CHANGELOG.md` (or
   `git -C ../sdk-template show <tag>:CHANGELOG.md` when the family workspace is checked
   out beside this repository), for every release after `_commit` up to `<tag>`: its
   entries, its **Hand-apply** list and its "Updating from" paragraph, which names the
   `-d` answers an update from an older tag needs. Then the core release it adopts,
   `X.Y.0`: sdk-core's `CHANGELOG.md` section, the ADRs it names, their Consequences, and
   `docs/handover.md`, section "Adopting core X.Y.0", for what this source deletes and
   declares (`https://github.com/xippios/sdk-core/tree/vX.Y.0`, or
   `git -C ../sdk-core show vX.Y.0:<path>` in the same workspace).

3. **Items 1 and 2: the core floor and the template.** Run

   ```bash
   uvx copier update --defaults --vcs-ref=<tag> -d core_version=X.Y.0 -d core_git_ref=
   ```

   adding every `-d` answer the "Updating from" paragraphs name. Resolve the conflicts:
   `git grep -n '^<<<<<<< before updating'` finds them in the files the template manages
   (`tests/conftest.py`, `tests/test_layout.py` and `tests/test_adapters.py` among them).
   Keep the template's side and carry over what the source added on purpose, such as a
   fixture of its own in `conftest.py`. The files the source fills, `__init__.py`,
   `_client.py`, `models.py`, `api/`, `tasks.py`, `tasks_write.py`, `params.py`,
   `enums.py`, `reference/`, `scripts/`, `tests/test_tasks.py`,
   `tests/test_tasks_write.py`, `tests/test_live.py`, `tests/fixtures/`, `docs/upstream/`,
   `README.md` and `CHANGELOG.md`, are never touched by the update. Then `uv lock` and
   `uv sync --all-extras`. `pyproject.toml` depends on `xippios-core~=X.Y.0`, its `mcp`,
   `http` and `testing` extras likewise, with no `[tool.uv.sources]` left.

4. **Hand-apply.** Port every bullet of every Hand-apply list after `_commit` by hand:
   path, change, reason. A bullet whose file the source changed is ported in the
   source's form; a bullet that does not apply to this source says why in the PR.

5. **Items 3 and 4: workarounds.** Delete every local workaround a core change replaced,
   its tests with it: those the release's ADRs and `docs/handover.md` name for this
   source, and any other the CHANGELOG's breaking changes reach. The PR description names
   the core change for each (`placeholder_api_key` in `conftest.py` → the plugin's pin,
   ADR-0013). Logic duplicated across sources that core does not provide yet is proposed
   to sdk-core in the PR description, never copied further.

6. **Item 5: tests that assert what the plugin turns off.** A test that asserts a limiter
   wait, a quota pause or a quota refusal is marked `rate_limited`; a module that tests key
   resolution defines a `placeholder_api_key` fixture that pins nothing; a test that must
   reach the network is marked `network` (ADR-0013, ADR-0015).
   `xippios_placeholder_key_envs` under `[tool.pytest.ini_options]` names
   `DATA_GOV_API_KEY`, and `tests/conftest.py` keeps no placeholder fixture of its own.

7. **Item 6: generated enums.** Re-render `enums.py` once with the release's renderers
   from the packaged lists, `uv run python scripts/refresh_reference.py --render-only`
   (step 4 ports the flag where the script lacks it), and commit it as rendered: no
   formatting step after it. An adoption fetches nothing: the packaged lists stay as
   they are, since the PR changes nothing else (conventions §15).

8. **Item 7: scripts.** `uv run mypy` covers `scripts/` too
   (`files = ["src", "tests", "scripts"]`); fix what `--strict` reports there.

9. **Item 8: conventions.** The release names a conventions version (the header of
   sdk-core's `docs/conventions.md`); every rule changed since the version this
   repository last applied (its `CHANGELOG.md` says which) holds after this PR, or the
   PR says why not.

10. **Item 9: changelog.** One line under Unreleased in `CHANGELOG.md` naming the core,
    template and conventions versions adopted, e.g. "Adopted xippios-core 0.2.0,
    sdk-template v0.2.0 and conventions 1.13 (conventions §15)."

11. **Checks**, all of them:
    `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.

12. **The PR.** `gh pr create` from `chore/template-update-<tag>`; the body is the
    definition of done's **Enforced by CI**, **Adoption PR** and **Process** blocks only
    (sdk-core `docs/definition-of-done.md`; Code, Tests and Docs stay out), ticked, an
    unticked item with a one-line reason, the core change named for each deleted
    workaround, assumptions and open questions listed. After the reviewer's `ready`, the
    session enables auto-merge from the family workspace root, the directory that holds
    the family `CLAUDE.md`, because this repository's `.claude/settings.json` denies
    `gh pr merge`; `-R` names the repository, which `gh` cannot infer there:

    ```bash
    gh pr merge --auto --squash -R xippios/sdk-usda-esr <number>
    ```

    GitHub merges once `ci` is green and review threads are resolved (ADR-0018).

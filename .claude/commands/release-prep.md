Prepare the release of xippios-usda-esr: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. Tagging and publishing are human
actions; this command only prepares the PR.

1. Work on a branch `chore/release-<version>`.
2. SemVer check: pre-1.0, a breaking change bumps the minor. An upstream API change that
   changed our public surface is a breaking change. Read `CHANGELOG.md` Unreleased and
   confirm the version matches what is in it; say so in the PR if it does not.
3. No git-pinned core. If `pyproject.toml` has a `[tool.uv.sources]` block, the package
   depends on an unreleased xippios-core and cannot be released as it is. Find the core
   release that carries the pinned change (stop and report if there is none yet):
   `X.Y.Z` with `Z` the patch that shipped it, or `X.Y.0` when the minor itself did;
   still one minor. Then remove the pin and raise the bound to that release in one step,
   `xippios-core~=X.Y.Z`:
   `uvx copier update --defaults --vcs-ref=:current: -d core_git_ref= -d core_version=X.Y.Z`
   (`:current:` keeps the template version, so only these two answers change). Then
   `uv lock`, the checks, a line under Unreleased in `CHANGELOG.md` (the new core
   bound), and a commit of its own. `publish.yml` refuses a pinned release as well.
4. `pyproject.toml`: set `version`. The publish workflow refuses a tag that does not
   equal it.
5. `CHANGELOG.md`: move everything under Unreleased into a `## [<version>] - <today>`
   section, leave an empty Unreleased above it.
6. README: the status table reflects what this version covers; install snippets are
   current.
7. Run the full suite: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   If live tests can run (`XIPPIOS_LIVE_TESTS=1`), run them too and report the result.
8. Open the PR with the definition-of-done checklist. After the reviewer's `ready` the
   session enables auto-merge from the family workspace root, the directory that holds
   the family `CLAUDE.md`, because this repository's `.claude/settings.json` denies
   `gh pr merge`; `-R` names the repository, which `gh` cannot infer there:
   `gh pr merge --auto --squash -R xippios/sdk-usda-esr <number>`. GitHub
   merges once `ci` is green and review threads are resolved (ADR-0018). Then stop and
   print the human steps: `git tag v<version>` on `main` after the merge, push the tag,
   approve the `pypi` environment run in the Actions tab.

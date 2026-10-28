Prepare the release of xippios-usda-esr: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. This command prepares the release PR
and nothing else; its merge is the release (the release train, conventions §12). The
merge runs `publish.yml`, which tags `v<version>` on the merge commit, builds, and waits
at the `pypi` environment until Johannes approves the run. No session and no human pushes
the tag.

A release PR changes only `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `README.md`,
`CLAUDE.md` and `docs/handover.md`, the subset of conventions §12; the `merge-class` check
makes any other changed path `human`. The sibling check is the template's and installs
the siblings from PyPI, so a release no longer touches it. What a release needs beyond
the subset is a PR of its own, merged before this one: the removal of a core pin (step 1)
and the refresh of packaged reference data (step 2). The PR meets the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and the
reviewer judges it against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **No git-pinned core.** If `pyproject.toml` has a `[tool.uv.sources]` block, the
   package depends on an unreleased xippios-core and cannot be released as it is. Find
   the core release that carries the pinned change (stop and report if there is none
   yet): `X.Y.Z` with `Z` the patch that shipped it, or `X.Y.0` when the minor itself
   did; still one minor. On a `chore/` branch of its own, remove the pin and raise the
   bound to that release in one step, `xippios-core~=X.Y.Z`:
   `uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=:current: -d core_git_ref= -d core_version=X.Y.Z`
   (`:current:` keeps the template version, so only these two answers change). Then
   `uv lock`, the checks, a line under Unreleased in `CHANGELOG.md` (the new core
   bound), and its PR, merged before the release PR: it changes `.copier-answers.yml`,
   which a release PR does not. `publish.yml` refuses to tag a pinned release as well.
2. **Reference data.** Packaged lists that should be current in this release are
   refreshed in their own PR, `/refresh-reference-data`, merged before this one; the
   release PR fetches nothing.
3. Work on a branch `chore/release-<version>` from an up-to-date `main`. If `main` moves
   while the PR is open, merge `origin/main` into the branch, never force-push; the
   squash merge flattens the merge commit.
4. SemVer check: pre-1.0, a breaking change bumps the minor. An upstream API change that
   changed our public surface is a breaking change. Read `CHANGELOG.md` Unreleased and
   confirm the version matches what is in it; say so in the PR if it does not.
5. `pyproject.toml`: set `version`, the version `publish.yml` tags, then `uv lock`. A
   first release keeps the scaffold's `0.1.0`: its CHANGELOG section alone makes the
   merge a release.
6. `CHANGELOG.md`: move everything under Unreleased into a `## [<version>] - <today>`
   section, leave an empty Unreleased above it. `publish.yml` tags only a version whose
   section has this heading, and the section becomes the tag's message. The date is the
   merge's, which is the tag's: if the merge slips to a later day, re-date the heading in
   a commit of its own before it.
7. README: the status table reflects what this version covers; install snippets are
   current.
8. Run the full suite: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
   If live tests can run (`XIPPIOS_LIVE_TESTS=1`), run them too,
   `uv run pytest -m live --tb=short`, and report the result.
9. Open the PR, its body as the definition of done says. After the reviewer's `ready`,
   if the `merge-class` check says `auto`, the session enables auto-merge here, as
   `.claude/settings.json` allows; every other `gh pr merge` meets the permission
   prompt: `gh pr merge --auto --squash -R xippios/sdk-usda-esr <number>`. GitHub
   merges once `ci` is green and review threads are resolved; a `human` release waits
   for Johannes (ADR-0018, amendment (e)). Then stop and report: the merge tags
   `v<version>` through `publish.yml`, and Johannes approves the `pypi` run in the
   Actions tab. A first release needs the PyPI pending publisher (owner xippios,
   repository sdk-usda-esr, workflow `publish.yml`, environment `pypi`) before
   that approval; name it in the report if the release is `0.1.0`.

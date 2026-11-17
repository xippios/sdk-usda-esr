Prepare the release of xippios-usda-esr: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. This command prepares the release's
pull request and nothing else; that pull request is the release (the release train,
conventions §12). Once it is on `main`, `publish.yml` tags `v<version>` on the merge
commit, builds, and waits at the `pypi` environment until a maintainer approves the run;
then the trusted publisher uploads. The tag comes from that workflow alone.

The release's pull request changes only the files of conventions §12: `pyproject.toml`,
`uv.lock`, `CHANGELOG.md`, `README.md`, `CLAUDE.md` and the fragments under
`changelog/`, which it deletes. §12 also names `docs/handover.md`, which is sdk-core's
file and not one a source must have. What a release needs beyond these files comes in a
pull request of its own before it: the removal of a core pin (step 1) and a refresh of
the packaged reference data that changed a record (step 2). A template release is taken
in a pull request of its own as well, never in a release's:
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>`, with
`-d core_version=X.Y.Z` where it carries a new core minor, its conflicts resolved and the
Hand-apply entries of sdk-template's `CHANGELOG.md` since the tag `.copier-answers.yml`
names ported by hand (conventions §15). The release meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **No git-pinned core.** If `pyproject.toml` has a `[tool.uv.sources]` block, the
   package depends on an unreleased xippios-core and cannot be released as it is. Find
   the core release that carries the pinned change (stop and report if there is none
   yet): `X.Y.Z` with `Z` the patch that shipped it, or `X.Y.0` when the minor itself
   did; still one minor. In a change of its own, remove the pin and raise the bound to
   that release in one step, `xippios-core~=X.Y.Z`:
   `uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=:current: -d core_git_ref= -d core_version=X.Y.Z`
   (`:current:` keeps the template version, so only these two answers change). Then
   `uv lock`, the checks and a changelog fragment under `changelog/` that names the new
   core bound, in a pull request of its own before the release's: it changes
   `.copier-answers.yml`, which a release does not. `publish.yml` refuses to tag a pinned
   release as well.
2. **Reference data.** Where the source packages lists, run `/refresh-reference-data`
   before the release; the release's pull request fetches nothing. The refresh is a pull
   request of its own, before the release's, only when a record changed or `fetched`
   goes from a bare date to the full time; otherwise it gets none, and the release's pull
   request cites the run, "unchanged" meaning the records, not the files (conventions
   §12).
3. **Live evidence.** The release's pull request cites a green run of `live.yml` on the
   commit of `main` it starts from: the nightly run, or, where none ran after the last
   pull request before the release, one dispatch of `live.yml` on `main`. An adoption
   that landed late counts as such a pull request, since it changes what the live tests
   run through, and a task added since the last green run would otherwise reach its tag
   without a live test. Before a dispatch, where the live tests can run here
   (`XIPPIOS_LIVE_TESTS=1`), run them first,
   `uv run pytest -m live --tb=short --assert=plain`, so that a failure shows before the
   dispatch spends a run.
4. SemVer check: pre-1.0, a breaking change bumps the minor. An upstream API change that
   changed our public surface is a breaking change. Read the fragments under `changelog/`
   and what `## [Unreleased]` holds, and confirm that the version matches them; say so in
   the pull request if it does not.
5. `pyproject.toml`: set `version`, the version `publish.yml` tags, then `uv lock`. A
   first release keeps the scaffold's `0.1.0`: its CHANGELOG section alone makes it a
   release.
6. `CHANGELOG.md`: write `## [<version>] - <today>` in place of `## [Unreleased]`, or
   above the last release where there is none, and assemble its section from the
   fragments under `changelog/` and what `## [Unreleased]` held, as `changelog/README.md`
   lays it out. The repository keeps no script for it: copy each fragment's bullet into
   the section by hand, then delete the fragments it took; `changelog/README.md` stays.
   `publish.yml` tags only a version whose section has this heading, and the section
   becomes the tag's message. The date is the tag's, the day the pull request reaches
   `main`: if that slips to a later day, re-date the heading in a commit of its own
   before it.
7. README: the status table reflects what this version covers; install snippets are
   current.
8. Run the checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
9. **The report.** The release's pull request names the version and cites the
   reference-data run of step 2 and the live run of step 3. Then stop: once it is on
   `main`, `publish.yml` tags `v<version>` and waits for a maintainer's approval of the
   `pypi` run. A first release needs PyPI's pending publisher before that approval, with
   project name `xippios-usda-esr`, the distribution's name in `pyproject.toml`,
   owner `xippios`, repository `sdk-usda-esr`, workflow `publish.yml` and
   environment `pypi`: a publisher that names another project fails the upload for good,
   the tag stands without a release, and only a patch release recovers. Name the
   publisher in the report if the release is `0.1.0`.

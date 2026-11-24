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
names ported by hand (conventions §15). That pull request's fragment names the core
bound, the template's tag and the conventions' version as they stand after the update,
changed or not, and is `breaking` where the update brings a core minor and `changed` where
it brings none (conventions §15 item 9). The release meets sdk-core's definition of done,
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
   The source packages this one depends on, `xippios-usda-fas`, are
   released on PyPI before this release: each tags first, its bound in `pyproject.toml`
   names that published version, and no `[tool.uv.sources]` entry pins it, which
   `publish.yml` refuses too (sdk-core ADR-0021 decision 5, conventions §12).
2. **Reference data.** Run `/refresh-reference-data` before the release, whose pull
   request fetches nothing. The refresh is a pull request of its own only where a record
   changed or `fetched` went from a bare date to the full time, and the release's pull
   request cites the run otherwise (conventions §12).
3. **Live evidence.** The release's pull request cites a green run of `live.yml` on the
   commit of `main` it starts from: the nightly run, or one dispatch of `live.yml` on
   `main`. A run on an earlier commit of `main` is no such run, whatever the pull requests
   after it changed, so a release whose base moved after its run waits for the next
   nightly or one more dispatch. Before a dispatch, where the live tests can run here
   (`XIPPIOS_LIVE_TESTS=1`), run them first,
   `uv run pytest -m live --tb=short --assert=plain`, so that a failure shows before the
   dispatch spends a run. After the live tests, xippios-core's testing plugin prints the
   requests they sent in one line, `requests sent by the live run: <n>`, in the log of the
   pytest step of `live.yml` as in a run here. The release cites that count of the run it
   names, and counts as its live calls the requests of every run it dispatched or ran
   here, their lines added up.
4. **SemVer**, by conventions §12: an adoption of a core minor is a breaking
   change, whatever else the release brings, and its fragment is `breaking`. Read the
   fragments under `changelog/` and what `## [Unreleased]` holds, which
   `python3 -I scripts/changelog_assemble.py --notes` prints as the section will hold
   them, writing nothing, and confirm that the version matches them; say so in the pull
   request if it does not.
5. **The version.** `version` in `pyproject.toml` is the version `publish.yml` tags, and
   `uv.lock` holds it on this package's own entry. Step 6's script sets both and runs no
   `uv lock`, so the release builds nothing and reaches no index. A first release keeps
   the scaffold's `0.1.0`: its CHANGELOG section alone makes it a release.
6. **The section.** Run
   `python3 -I scripts/release_prepare.py <version> --date <YYYY-MM-DD>`, the date
   today's in UTC. It writes `## [<version>] - <date>` into `CHANGELOG.md` in place of
   `## [Unreleased]`, or above the last release where there is none, assembles its section
   from the fragments under `changelog/` and what `## [Unreleased]` held, as
   `changelog/README.md` lays it out, deletes the fragments it took, the README kept, and
   sets the version of step 5. The release rewords and regroups no entry: a wrong one
   is corrected in its fragment, by a pull request before the release's (conventions §12).
   `publish.yml` tags only a version whose section has this heading, and the section
   becomes the tag's message. The date is the tag's, the day the pull request reaches
   `main`: if that slips to a later day, the same command with that day's `--date`
   re-dates the heading alone, in a commit of its own before it.
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

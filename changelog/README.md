# Changelog fragments

Every change brings its changelog entry as a file of its own in this folder, a fragment, so
that two pull requests never edit the same lines of `CHANGELOG.md`. The release assembles the
fragments into its section of `CHANGELOG.md` and deletes them. This README stays.

## A fragment

- **Its name.** `changelog/<group>-<slug>.md`, one file per change. `<group>` is one of
  `added`, `changed`, `fixed`, `removed`, `security` and `breaking`, and `<slug>` names the
  change in lowercase letters and digits, its words joined by hyphens.
- **Its bullet.** The file holds one bullet, as it will stand in the release's section: its
  first line starts with `- `, and a line it continues is indented by two spaces. The lead
  sentence says what changed for a user of the package, and up to two more say how it is
  used or what it replaces. Its citations close it in parentheses: an `ADR-NNNN` it follows,
  and the URL of the issue it answers or of its pull request.
- **When.** Every pull request but a release's and Dependabot's adds one, and the `ci` check
  fails a pull request that adds neither a fragment nor a line under `## [Unreleased]` in
  `CHANGELOG.md`. A pull request that changes an entry not yet released edits its fragment.

`changelog/added-year-on-get-report.md`:

```markdown
- `get_report` takes `year`, which selects one marketing year.
  (https://github.com/<owner>/<repository>/issues/<n>)
```

## The release

The release's pull request writes `## [X.Y.Z] - YYYY-MM-DD` into `CHANGELOG.md` in place of
`## [Unreleased]`, or above the last release where there is none, and deletes the fragments
it took. The section holds:

- the groups in the order above, each under its heading, `### Added`, `### Changed` and so
  on, and only those with an entry;
- in each group the fragments newest first, by the commit that added each, then the entries
  that `## [Unreleased]` held under that heading;
- after them, any other group that `## [Unreleased]` held, as it stood.

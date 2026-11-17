# Architecture decision records

This folder holds the design decisions of this repository, one record per decision.
`scripts/adr_index.py` reads the records' headers and writes their index, `docs/adr.md` for
people and `docs/adr.json` for machines. This README stays.

## A record

- **Its name.** `docs/adr/NNNN-<slug>.md`, numbered from `0001` in the order the records are
  written, and cited as `ADR-NNNN`. `<slug>` names the decision in lowercase letters and
  digits, its words joined by hyphens. No two records take one number.
- **Its header.** The first line reads `# ADR-NNNN: <title>`, with the number of its name.
  The status paragraph follows after a blank line, its fields joined by ` · `:
  `Status: Accepted · Date: YYYY-MM-DD`, then `Decided by <URL>`, the issue or pull request
  that decided it, and any of `Amended YYYY-MM-DD by <URL>` and `Supersedes ADR-NNNN`.
- **Its sections.** `## Context`, `## Decision` and `## Consequences`, in that order.
- **Amended, then superseded.** An amendment adds `Amended YYYY-MM-DD by <URL>` to the status
  paragraph, twice at most. A third amendment, or a reversal, is a new record that supersedes
  this one, whose status then reads `Superseded by ADR-NNNN`.
- **Its evidence.** A finding the decision rests on is a dated report under `docs/reports/`,
  which the record cites.

## The index

The index is generated, never edited by hand. After a record is written or changed, and
after `copier update` brings a new version of the script, run it from the repository's root
and commit both files with the change:

```bash
python3 scripts/adr_index.py            # writes docs/adr.md and docs/adr.json
python3 scripts/adr_index.py --check    # writes nothing; exits 1 when either is stale
```

The script needs the standard library alone. It exits 1 and writes nothing on a record whose
first line does not read as above, or whose number another record takes.

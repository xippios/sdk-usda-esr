#!/usr/bin/env python3
"""Write the index of this repository's architecture decision records from their headers: `docs/adr.md` for people
and `docs/adr.json` for machines, beside the records `docs/adr/NNNN-<slug>.md` cited as `ADR-NNNN`, then the records
of a closed series of former entries where a repository keeps one, `docs/adr/CNNN-<slug>.md` cited as `ADR-CNNN`, each
with its `Formerly: C<n>` line.

    python3 -I scripts/adr_index.py            writes both files where they differ from the records
    python3 -I scripts/adr_index.py --check    writes nothing, and exits 1 when either file differs

`docs/adr.md` lists the records in force first and those that a later record superseded after them, and gives each
line the anchor of its record's number as a citation gives it, `0014` for ADR-0014 and `C047` for ADR-C047, so a link
to `docs/adr.md#0014` opens the index at that record. It exits 1 on a record whose title does not read
`# ADR-NNNN: <title>` with its file's number, on a number that two records take, and on a former entry's record without
its `Formerly: C<n>` line. It needs the standard library alone, so people and CI run the same script. A repository
carries it byte for byte as its template renders it and edits no copy: the template's next release brings the next
version.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RECORDS = "docs/adr"
INDEX_MD = "docs/adr.md"
INDEX_JSON = "docs/adr.json"
NAME = re.compile(r"^(C?)(\d{4}|\d{3})-.+\.md$")
TITLE = re.compile(r"^# ADR-(C?\d{3,4}): (.+)$")
FORMERLY = re.compile(r"^Formerly: (C\d+)$")
SEPARATOR = " · "
AMENDED = re.compile(r"^Amended (\d{4}-\d{2}-\d{2}) by (.+)$")
SUPERSEDED = re.compile(r"\bSuperseded by (ADR-\d{4})\b")
HEAD = """# Architecture decision records

The decisions of this repository, one line per record, written by `scripts/adr_index.py` from the headers of the
records in `docs/adr/`. A record changes, and this file follows when the script runs again.
"""
FORMER = """
The former entries follow, a closed series that no new record joins: the entry C60 reads as the record ADR-C060,
`docs/adr/C060-<slug>.md`, whose `Formerly: C60` line names it.
"""
LATER = """
The superseded records follow, kept as written: the record that each status names holds its decision now.
"""


def header(text: str) -> tuple[str, str, str | None]:
    """The record's title line, its status paragraph, the lines from `Status:` to the next blank line joined, and the
    entry its `Formerly: C<n>` line names above its first section, None without one."""
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    status: list[str] = []
    formerly = None
    ended = False
    for line in lines[1:]:
        if line.startswith("## "):
            break
        found = FORMERLY.match(line.strip())
        if found:
            formerly = found.group(1)
        elif status and not line.strip():
            ended = True
        elif not ended and (status or line.startswith("Status:")):
            status.append(line.strip())
    return title, " ".join(status), formerly


def fields(status: str) -> dict[str, object]:
    """The fields of a status paragraph: `Status: <status> · Date: <date> · Decided by <URL>`, then any of
    `Amended <date> by <URL>`, `Amends C<n>` and `Supersedes ADR-NNNN`; a field of another form is kept as written."""
    parts = [part.strip() for part in status[len("Status:") :].split(SEPARATOR)] if status else []
    out: dict[str, object] = {"status": parts[0] if parts else "", "date": "", "decided_by": ""}
    amended: list[dict[str, str]] = []
    amends: list[str] = []
    supersedes: list[str] = []
    other: list[str] = []
    for part in parts[1:]:
        found = AMENDED.match(part)
        if part.startswith("Date: "):
            out["date"] = part[len("Date: ") :]
        elif part.startswith("Decided by "):
            out["decided_by"] = part[len("Decided by ") :]
        elif found:
            amended.append({"date": found.group(1), "by": found.group(2)})
        elif part.startswith("Amends "):
            amends.append(part[len("Amends ") :])
        elif part.startswith("Supersedes "):
            supersedes.append(part[len("Supersedes ") :])
        else:
            other.append(part)
    superseded = SUPERSEDED.search(str(out["status"]))
    out.update(amended=amended, amends=amends, supersedes=supersedes, other=other)
    out["superseded_by"] = superseded.group(1) if superseded else None
    return out


def records(root: Path) -> tuple[list[dict[str, object]], list[str]]:
    """Every record under `docs/adr/` in the order of its number, the former entries' after the others, and the
    problems found, one per line."""
    found: list[dict[str, object]] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    folder = root / RECORDS
    names = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    for name in names:
        number = NAME.match(name)
        if not number or len(number.group(2)) != (3 if number.group(1) else 4):
            continue
        stem = number.group(1) + number.group(2)
        path = f"{RECORDS}/{name}"
        title, status, formerly = header((folder / name).read_text(encoding="utf-8"))
        heading = TITLE.match(title)
        if not heading or heading.group(1) != stem:
            problems.append(f"{path}: the first line is not `# ADR-{stem}: <title>`")
            continue
        n = int(number.group(2))
        if number.group(1) and formerly != f"C{n}":
            problems.append(f"{path}: no `Formerly: C{n}` line above its first section")
            continue
        if stem in seen:
            problems.append(f"{path}: ADR-{stem} again, after {seen[stem]}")
            continue
        seen[stem] = path
        record: dict[str, object] = {"id": f"ADR-{stem}", "number": n, "title": heading.group(2).strip()}
        record["path"] = path
        record.update(fields(status))
        if number.group(1):
            record["formerly"] = formerly
        found.append(record)
    return sorted(found, key=lambda r: ("formerly" in r, int(str(r["number"])))), problems


def markdown(found: list[dict[str, object]]) -> str:
    """The index for people: the records in force, then the superseded ones, each series in its order, and once before
    the first of a group the paragraph that says how it reads; each line opens with its record's anchor."""
    standing = [r for r in found if not r["superseded_by"]]
    superseded = [r for r in found if r["superseded_by"]]
    lines = []
    for r in standing + superseded:
        if r["superseded_by"] and LATER not in lines:
            lines.append(LATER)
        if "formerly" in r and FORMER not in lines:
            lines.append(FORMER)
        anchor = str(r["id"])[len("ADR-") :]
        line = f'- <a id="{anchor}"></a>[{r["id"]}](adr/{str(r["path"]).rsplit("/", 1)[-1]}): {r["title"]}'
        extra = [str(r["status"]), str(r["date"])]
        amended = r["amended"]
        if isinstance(amended, list) and amended:
            extra.append(f"amended {amended[-1]['date']}")
        line += "".join(f"{SEPARATOR}{part}" for part in extra if part)
        lines.append(line)
    return HEAD + "\n" + ("\n".join(lines) if lines else "No record yet.") + "\n"


def machine(found: list[dict[str, object]]) -> str:
    return json.dumps({"records": found}, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write docs/adr.md and docs/adr.json from the records in docs/adr/.")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when either file differs")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the repository")
    a = ap.parse_args(argv)
    root: Path = a.root
    found, problems = records(root)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    wanted = {INDEX_MD: markdown(found), INDEX_JSON: machine(found)}
    differ = [name for name, text in wanted.items() if read(root / name) != text]
    former = sum(1 for r in found if "formerly" in r)
    count = f"{len(found) - former} record{'' if len(found) - former == 1 else 's'}"
    count += f" and {former} former entr{'y' if former == 1 else 'ies'}" if former else ""
    if not differ:
        print(f"{INDEX_MD}, {INDEX_JSON}: {count}, up to date")
        return 0
    if a.check:
        print(f"{', '.join(differ)}: stale against {count}; `python3 -I scripts/adr_index.py` writes the index")
        return 1
    for name in differ:
        (root / name).write_text(wanted[name], encoding="utf-8")
    print(f"{', '.join(differ)}: {count}, written")
    return 0


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


if __name__ == "__main__":
    sys.exit(main())

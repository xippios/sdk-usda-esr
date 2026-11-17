#!/usr/bin/env python3
"""Write the index of this repository's architecture decision records from their headers.

The records are ``docs/adr/NNNN-<slug>.md``, laid out as ``docs/adr/README.md`` says, and
the index is ``docs/adr.md`` for people and ``docs/adr.json`` for machines::

    python3 scripts/adr_index.py            # writes both files where they differ
    python3 scripts/adr_index.py --check    # writes nothing; exits 1 when either differs

It exits 1 too on a record whose first line does not read ``# ADR-NNNN: <title>`` with its
file's number, and on a number that two records take, and then writes nothing. It needs the
standard library alone, so people and CI run the same script, CI with ``python3 -I``.
sdk-template keeps it and renders it into every repository it generates, and
``copier update`` brings its next version, so a repository does not edit its copy.
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
NAME = re.compile(r"^(\d{4})-.+\.md$")
TITLE = re.compile(r"^# ADR-(\d{4}): (.+)$")
SEPARATOR = " · "
AMENDED = re.compile(r"^Amended (\d{4}-\d{2}-\d{2}) by (.+)$")
SUPERSEDED = re.compile(r"\bSuperseded by (ADR-\d{4})\b")
HEAD = """# Architecture decision records

The decisions of this repository, one line per record, written by `scripts/adr_index.py`
from the headers of the records in `docs/adr/`. A record changes, and this file follows
when the script runs again.
"""


def header(text: str) -> tuple[str, str]:
    """The record's title line and its status paragraph, from `Status:` to a blank line."""
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    status: list[str] = []
    for line in lines[1:]:
        if line.startswith("## ") or (status and not line.strip()):
            break
        if status or line.startswith("Status:"):
            status.append(line.strip())
    return title, " ".join(status)


def fields(status: str) -> dict[str, object]:
    """The fields of a status paragraph.

    `Status: <status> · Date: <date> · Decided by <URL>`, then any of
    `Amended <date> by <URL>`, `Amends <entry>` and `Supersedes ADR-NNNN`; a field of
    another form is kept as written.
    """
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
    """Every record under `docs/adr/` in the order of its number, and the problems found."""
    found: list[dict[str, object]] = []
    problems: list[str] = []
    seen: dict[int, str] = {}
    folder = root / RECORDS
    names = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    for name in names:
        number = NAME.match(name)
        if not number:
            continue
        path = f"{RECORDS}/{name}"
        title, status = header((folder / name).read_text(encoding="utf-8"))
        heading = TITLE.match(title)
        if not heading or heading.group(1) != number.group(1):
            problems.append(f"{path}: the first line is not `# ADR-{number.group(1)}: <title>`")
            continue
        n = int(number.group(1))
        if n in seen:
            problems.append(f"{path}: ADR-{n:04d} again, after {seen[n]}")
            continue
        seen[n] = path
        record: dict[str, object] = {
            "id": f"ADR-{n:04d}",
            "number": n,
            "title": heading.group(2).strip(),
        }
        record["path"] = path
        record.update(fields(status))
        found.append(record)
    return sorted(found, key=lambda r: int(str(r["number"]))), problems


def markdown(found: list[dict[str, object]]) -> str:
    """The index for people: a line per record with its status, its date and its amendment."""
    lines = []
    for r in found:
        line = f"- [{r['id']}](adr/{str(r['path']).rsplit('/', 1)[-1]}): {r['title']}"
        extra = [str(r["status"]), str(r["date"])]
        amended = r["amended"]
        if isinstance(amended, list) and amended:
            extra.append(f"amended {amended[-1]['date']}")
        line += "".join(f"{SEPARATOR}{part}" for part in extra if part)
        lines.append(line)
    return HEAD + "\n" + ("\n".join(lines) if lines else "No record yet.") + "\n"


def machine(found: list[dict[str, object]]) -> str:
    """The index for machines: every field of every record."""
    return json.dumps({"records": found}, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write or check the index; 0 when it is current or written, 1 otherwise."""
    ap = argparse.ArgumentParser(
        description="Write docs/adr.md and docs/adr.json from the records in docs/adr/."
    )
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if either differs")
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="the repository",
    )
    a = ap.parse_args(argv)
    root: Path = a.root
    found, problems = records(root)
    for problem in problems:
        say(problem)
    if problems:
        return 1
    wanted = {INDEX_MD: markdown(found), INDEX_JSON: machine(found)}
    differ = [name for name, text in wanted.items() if read(root / name) != text]
    count = f"{len(found)} record{'' if len(found) == 1 else 's'}"
    if not differ:
        say(f"{INDEX_MD}, {INDEX_JSON}: {count}, up to date")
        return 0
    if a.check:
        command = "`python3 scripts/adr_index.py` writes the index"
        say(f"{', '.join(differ)}: stale against {count}; {command}")
        return 1
    for name in differ:
        (root / name).write_text(wanted[name], encoding="utf-8")
    say(f"{', '.join(differ)}: {count}, written")
    return 0


def read(path: Path) -> str | None:
    """The file's text, or None where there is none."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def say(line: str) -> None:
    """One line of the script's report on standard output."""
    sys.stdout.write(line + "\n")


if __name__ == "__main__":
    sys.exit(main())
